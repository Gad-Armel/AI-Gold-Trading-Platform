from __future__ import annotations

"""V6.3 calibrated champion/challenger learner for shadow trade selection.

The learner is deliberately conservative:
- it trains only on real closed shadow outcomes;
- all evaluation is chronological;
- probability calibration uses a trailing calibration slice;
- a model is deployable only when selected out-of-sample trades meet the
  configured win-rate, expectancy, profit-factor, coverage and calibration
  requirements;
- the model can only filter an already-safe research candidate. It cannot
  bypass spread, quote freshness, news, account or structure protections.
"""

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd

from config import scalping_settings
from services.research.v6_outcome_quality import research_outcome_eligible
from services.utils.atomic_json import atomic_write_json


NUMERIC_FEATURES = [
    "winner_score",
    "score_margin",
    "spread_usd",
    "spread_atr",
    "abs_vwap_distance_atr",
    "relative_volume",
    "micro_confidence",
    "directional_micro_windows",
    "micro_data_quality",
    "micro_regime_confidence",
    "micro_quote_flow_imbalance",
    "micro_efficiency_ratio",
    "micro_stall_ratio",
    "micro_spread_expansion_atr",
    "micro_arrival_acceleration",
    "micro_velocity_atr_s",
    "micro_reversal_ratio",
    "persistence_cycles",
    "persistence_seconds",
    "m1_atr",
    "m1_rsi",
    "m1_momentum",
    "adx",
    "structure_votes",
    "structure_confidence",
    "structure_room_usd",
    "micro_aligned",
    "htf_aligned",
    "level_aligned",
    "order_block_aligned",
    "structure_aligned",
    "cross_market_pressure_score",
    "cross_market_available_symbols",
    "direct_intermarket_pressure_score",
    "direct_intermarket_resolved_symbols",
    "cross_market_aligned",
    "direct_intermarket_aligned",
    "hour_sin",
    "hour_cos",
]

CATEGORICAL_FEATURES = [
    "source_lane",
    "session",
    "direction",
    "micro_direction",
    "micro_regime",
    "regime",
    "pattern",
    "structure_direction",
    "htf_direction",
    "level_direction",
    "level_event",
    "order_block_direction",
    "cross_market_status",
    "cross_market_gold_bias",
    "direct_intermarket_status",
    "direct_intermarket_gold_bias",
]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass
class ChronologicallyCalibratedModel:
    base_model: Any
    calibrator: Any | None = None

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        raw = np.asarray(self.base_model.predict_proba(frame)[:, 1], dtype=float)
        if self.calibrator is not None:
            calibrated = np.asarray(self.calibrator.predict_proba(raw.reshape(-1, 1))[:, 1], dtype=float)
        else:
            calibrated = raw
        calibrated = np.clip(calibrated, 1e-6, 1 - 1e-6)
        return np.column_stack([1.0 - calibrated, calibrated])


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str = "UNKNOWN") -> str:
    text = str(value or default).strip().upper()
    return text or default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _history_paths() -> list[Path]:
    paths = [Path(scalping_settings.SCALPING_V6_SHADOW_HISTORY_PATH)]
    folder = Path(scalping_settings.SCALPING_V6_SHADOW_LANE_HISTORY_FOLDER)
    for lane in ("BALANCED", "EXPLORATORY", "LEARNED"):
        paths.append(folder / f"{lane.lower()}_history.jsonl")
    return paths


def _iter_closed_rows() -> Iterable[dict[str, Any]]:
    for path in _history_paths():
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(row, dict)
                and str(row.get("status", "")).upper() == "CLOSED"
                and research_outcome_eligible(row)
            ):
                yield row


def _aligned(direction: str, other: Any) -> float:
    return 1.0 if _text(direction, "NEUTRAL") == _text(other, "NEUTRAL") and direction in {"BUY", "SELL"} else 0.0


def _entry_hour(profile: dict[str, Any], row: dict[str, Any]) -> float:
    value = profile.get("entry_hour_utc")
    if value is not None:
        return _float(value) % 24.0
    stamp = row.get("opened_at") or row.get("decision_timestamp_utc")
    parsed = pd.to_datetime(stamp, utc=True, errors="coerce")
    if pd.isna(parsed):
        return 0.0
    return float(parsed.hour + parsed.minute / 60.0 + parsed.second / 3600.0)


def feature_row_from_profile(
    profile: dict[str, Any],
    *,
    source_lane: str | None = None,
    opened_at: Any = None,
) -> dict[str, Any]:
    direction = _text(profile.get("direction"), "NEUTRAL")
    hour = _entry_hour(profile, {"opened_at": opened_at})
    angle = 2.0 * math.pi * hour / 24.0
    row = {
        "winner_score": _float(profile.get("winner_score")),
        "score_margin": _float(profile.get("score_margin")),
        "spread_usd": _float(profile.get("spread_usd")),
        "spread_atr": _float(profile.get("spread_atr")),
        "abs_vwap_distance_atr": abs(_float(profile.get("vwap_distance_atr"), 999.0)),
        "relative_volume": _float(profile.get("relative_volume")),
        "micro_confidence": _float(profile.get("micro_confidence")),
        "directional_micro_windows": _float(profile.get("directional_micro_windows")),
        "micro_data_quality": _float(profile.get("micro_data_quality")),
        "micro_regime_confidence": _float(profile.get("micro_regime_confidence")),
        "micro_quote_flow_imbalance": _float(profile.get("micro_quote_flow_imbalance")),
        "micro_efficiency_ratio": _float(profile.get("micro_efficiency_ratio")),
        "micro_stall_ratio": _float(profile.get("micro_stall_ratio"), 1.0),
        "micro_spread_expansion_atr": _float(profile.get("micro_spread_expansion_atr")),
        "micro_arrival_acceleration": _float(profile.get("micro_arrival_acceleration")),
        "micro_velocity_atr_s": _float(profile.get("micro_velocity_atr_s")),
        "micro_reversal_ratio": _float(profile.get("micro_reversal_ratio")),
        "persistence_cycles": _float(profile.get("persistence_cycles")),
        "persistence_seconds": _float(profile.get("persistence_seconds")),
        "m1_atr": _float(profile.get("m1_atr")),
        "m1_rsi": _float(profile.get("m1_rsi")),
        "m1_momentum": _float(profile.get("m1_momentum")),
        "adx": _float(profile.get("adx")),
        "structure_votes": _float(profile.get("structure_votes")),
        "structure_confidence": _float(profile.get("structure_confidence")),
        "structure_room_usd": _float(profile.get("structure_room_usd")),
        "micro_aligned": _aligned(direction, profile.get("micro_direction")),
        "htf_aligned": _aligned(direction, profile.get("htf_direction")),
        "level_aligned": _aligned(direction, profile.get("level_direction")),
        "order_block_aligned": _aligned(direction, profile.get("order_block_direction")),
        "structure_aligned": _aligned(direction, profile.get("structure_direction")),
        "cross_market_pressure_score": _float(profile.get("cross_market_pressure_score")),
        "cross_market_available_symbols": _float(profile.get("cross_market_available_symbols")),
        "direct_intermarket_pressure_score": _float(profile.get("direct_intermarket_pressure_score")),
        "direct_intermarket_resolved_symbols": _float(profile.get("direct_intermarket_resolved_symbols")),
        "cross_market_aligned": _aligned(direction, profile.get("cross_market_gold_bias")),
        "direct_intermarket_aligned": _aligned(direction, profile.get("direct_intermarket_gold_bias")),
        "hour_sin": math.sin(angle),
        "hour_cos": math.cos(angle),
        "source_lane": _text(source_lane or profile.get("shadow_lane"), "UNKNOWN"),
        "session": _text(profile.get("session"), "UNKNOWN"),
        "direction": direction,
        "micro_direction": _text(profile.get("micro_direction"), "NEUTRAL"),
        "micro_regime": _text(profile.get("micro_regime"), "UNKNOWN"),
        "regime": _text(profile.get("regime"), "UNKNOWN"),
        "pattern": _text(profile.get("pattern"), "UNKNOWN"),
        "structure_direction": _text(profile.get("structure_direction"), "NEUTRAL"),
        "htf_direction": _text(profile.get("htf_direction"), "NEUTRAL"),
        "level_direction": _text(profile.get("level_direction"), "NEUTRAL"),
        "level_event": _text(profile.get("level_event"), "NONE"),
        "order_block_direction": _text(profile.get("order_block_direction"), "NEUTRAL"),
        "cross_market_status": _text(profile.get("cross_market_status"), "UNKNOWN"),
        "cross_market_gold_bias": _text(profile.get("cross_market_gold_bias"), "NEUTRAL"),
        "direct_intermarket_status": _text(profile.get("direct_intermarket_status"), "UNKNOWN"),
        "direct_intermarket_gold_bias": _text(profile.get("direct_intermarket_gold_bias"), "NEUTRAL"),
    }
    return row


def load_v63_training_frame() -> pd.DataFrame:
    """Load de-correlated, label-safe shadow outcomes for model training.

    LEARNED-lane trades are deliberately excluded: allowing a model to retrain on
    outcomes it selected itself creates a feedback loop and hides selection bias.
    When STRICT/BALANCED/EXPLORATORY simulate the same market episode, only the
    strictest available observation is retained so one impulse cannot masquerade
    as several independent samples.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_closed_rows = 0
    for trade in _iter_closed_rows():
        profile = trade.get("entry_profile") if isinstance(trade.get("entry_profile"), dict) else {}
        if not profile:
            continue
        row_strategy = str(trade.get("strategy_id") or profile.get("strategy_id") or "")
        if row_strategy != str(scalping_settings.SCALPING_STRATEGY_ID):
            # Entry/rearm policy changes alter the sampled population. Never
            # train a champion on outcomes generated by a different strategy.
            continue
        pnl = _float(trade.get("final_profit_usd"), float("nan"))
        if not math.isfinite(pnl):
            continue
        lane = _text(trade.get("shadow_lane") or profile.get("shadow_lane"), "UNKNOWN").upper()
        if lane == "LEARNED":
            continue
        raw_closed_rows += 1
        key = str(trade.get("id") or trade.get("candidate_key") or "") + "|" + str(trade.get("opened_at")) + "|" + lane
        if key in seen:
            continue
        seen.add(key)
        opened_at = pd.to_datetime(trade.get("opened_at"), utc=True, errors="coerce")
        closed_at = pd.to_datetime(trade.get("closed_at"), utc=True, errors="coerce")
        entry_price = _float(trade.get("entry_price"), _float(profile.get("entry_price"), 0.0))
        direction = _text(trade.get("direction") or profile.get("direction"), "WAIT").upper()
        record = feature_row_from_profile(profile, source_lane=lane, opened_at=trade.get("opened_at"))
        record.update(
            {
                "opened_at": opened_at,
                "closed_at": closed_at,
                "entry_price": entry_price,
                "pnl": pnl,
                "target": int(pnl > 0.0),
                "close_reason": _text(trade.get("close_reason"), "UNKNOWN"),
                "direction": direction,
                "source_lane": lane,
            }
        )
        rows.append(record)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame[frame["opened_at"].notna() & frame["closed_at"].notna()].copy()
    if frame.empty:
        return frame

    # Cross-lane simulations opened in the same short impulse are not independent.
    # Use a 15-second time bucket and a $0.25 XAUUSD entry-price bucket, then retain
    # the strictest lane available for that episode.
    lane_priority = {"STRICT": 0, "BALANCED": 1, "EXPLORATORY": 2}
    frame["lane_priority"] = frame["source_lane"].map(lane_priority).fillna(9).astype(int)
    frame["episode_time_bucket"] = frame["opened_at"].dt.floor("15s")
    frame["episode_price_bucket"] = (pd.to_numeric(frame["entry_price"], errors="coerce") / 0.25).round().fillna(-1).astype(int)
    frame["episode_key"] = (
        frame["direction"].astype(str)
        + "|"
        + frame["episode_time_bucket"].astype(str)
        + "|"
        + frame["episode_price_bucket"].astype(str)
    )
    pre_dedup_rows = int(len(frame))
    frame = (
        frame.sort_values(["episode_key", "lane_priority", "closed_at"])
        .drop_duplicates(subset=["episode_key"], keep="first")
        .sort_values("closed_at")
        .reset_index(drop=True)
    )
    frame.attrs["raw_closed_rows"] = int(raw_closed_rows)
    frame.attrs["pre_dedup_rows"] = pre_dedup_rows
    frame.attrs["decorrelated_rows"] = int(len(frame))
    frame.attrs["excluded_learned_lane"] = True
    for name in NUMERIC_FEATURES:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    for name in CATEGORICAL_FEATURES:
        frame[name] = frame[name].fillna("UNKNOWN").astype(str)
    return frame


def _make_base_model(name: str) -> Any:
    fast_test_mode = os.environ.get("SCALPING_FAST_TEST_MODE", "0") == "1"
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    pre = ColumnTransformer(
        transformers=[
            ("numeric", numeric, NUMERIC_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    if name == "LOGISTIC_BALANCED":
        estimator = LogisticRegression(
            C=0.35,
            class_weight="balanced",
            max_iter=3000,
            solver="liblinear",
            random_state=20260720,
        )
    elif name == "RANDOM_FOREST":
        estimator = RandomForestClassifier(
            n_estimators=60 if fast_test_mode else 350,
            max_depth=6,
            min_samples_leaf=5,
            max_features="sqrt",
            class_weight="balanced_subsample",
            random_state=20260720,
            n_jobs=-1,
        )
    elif name == "GRADIENT_BOOSTING":
        # Conservative shallow boosting captures non-linear interactions while
        # limiting variance on the still-small shadow dataset. It remains a
        # challenger and must pass the same purged OOS calibration tests.
        estimator = GradientBoostingClassifier(
            n_estimators=45 if fast_test_mode else 140,
            learning_rate=0.035,
            max_depth=2,
            min_samples_leaf=8,
            subsample=0.80,
            random_state=20260720,
        )
    else:
        estimator = LogisticRegression(
            C=0.35,
            class_weight=None,
            max_iter=3000,
            solver="liblinear",
            random_state=20260720,
        )
    return Pipeline(steps=[("features", pre), ("classifier", estimator)])


def _fit_calibrated(name: str, train: pd.DataFrame) -> ChronologicallyCalibratedModel:
    from sklearn.linear_model import LogisticRegression

    minimum_calibration = max(12, int(len(train) * 0.20))
    split = max(20, len(train) - minimum_calibration)
    fit_frame = train.iloc[:split]
    calibration_frame = train.iloc[split:]
    if fit_frame["target"].nunique() < 2:
        fit_frame = train
        calibration_frame = train.iloc[0:0]
    base = _make_base_model(name)
    base.fit(fit_frame[ALL_FEATURES], fit_frame["target"].astype(int))
    calibrator = None
    if len(calibration_frame) >= 10 and calibration_frame["target"].nunique() == 2:
        raw = np.asarray(base.predict_proba(calibration_frame[ALL_FEATURES])[:, 1], dtype=float)
        calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=20260720)
        calibrator.fit(raw.reshape(-1, 1), calibration_frame["target"].astype(int))
    return ChronologicallyCalibratedModel(base_model=base, calibrator=calibrator)


def _metrics(pnl: np.ndarray, target: np.ndarray, selected: np.ndarray) -> dict[str, Any]:
    mask = np.asarray(selected, dtype=bool)
    chosen_pnl = np.asarray(pnl, dtype=float)[mask]
    chosen_target = np.asarray(target, dtype=int)[mask]
    gross_profit = float(chosen_pnl[chosen_pnl > 0].sum()) if chosen_pnl.size else 0.0
    gross_loss = float(-chosen_pnl[chosen_pnl < 0].sum()) if chosen_pnl.size else 0.0
    return {
        "trades": int(mask.sum()),
        "coverage": float(mask.mean()) if mask.size else 0.0,
        "win_rate": float(chosen_target.mean()) if chosen_target.size else 0.0,
        "net_profit": float(chosen_pnl.sum()) if chosen_pnl.size else 0.0,
        "expectancy": float(chosen_pnl.mean()) if chosen_pnl.size else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "average_win": float(chosen_pnl[chosen_pnl > 0].mean()) if (chosen_pnl > 0).any() else 0.0,
        "average_loss": float(chosen_pnl[chosen_pnl < 0].mean()) if (chosen_pnl < 0).any() else 0.0,
    }


def _brier(target: np.ndarray, probability: np.ndarray) -> float:
    if not len(target):
        return 1.0
    return float(np.mean((np.asarray(probability) - np.asarray(target)) ** 2))


def _ece(target: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    if not len(target):
        return 1.0
    target = np.asarray(target, dtype=float)
    probability = np.asarray(probability, dtype=float)
    total = len(target)
    error = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (probability >= lower) & (probability < upper if index < bins - 1 else probability <= upper)
        if not mask.any():
            continue
        error += float(mask.mean()) * abs(float(target[mask].mean()) - float(probability[mask].mean()))
    return float(error)


def _fold_boundaries(total: int) -> list[tuple[int, int]]:
    folds = int(scalping_settings.SCALPING_V63_MIN_WALK_FORWARD_FOLDS)
    min_train = int(scalping_settings.SCALPING_V63_MIN_TRAIN_TRADES_PER_FOLD)
    if total < min_train + folds * 10:
        return []
    test_size = max(10, (total - min_train) // folds)
    boundaries: list[tuple[int, int]] = []
    start = min_train
    for index in range(folds):
        end = total if index == folds - 1 else min(total, start + test_size)
        if end <= start:
            break
        boundaries.append((start, end))
        start = end
    return boundaries


def _wilson_lower_bound(wins: int, total: int, z: float) -> float:
    if total <= 0:
        return 0.0
    p = wins / total
    denominator = 1.0 + (z * z) / total
    centre = p + (z * z) / (2.0 * total)
    margin = z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * total)) / total)
    return max(0.0, (centre - margin) / denominator)


def _select_threshold(probability: np.ndarray, target: np.ndarray, pnl: np.ndarray) -> dict[str, Any]:
    minimum = float(scalping_settings.SCALPING_V63_MIN_PROBABILITY_THRESHOLD)
    maximum = float(scalping_settings.SCALPING_V63_MAX_PROBABILITY_THRESHOLD)
    minimum_trades = int(scalping_settings.SCALPING_V63_MIN_OOS_SELECTED_TRADES)
    minimum_coverage = float(scalping_settings.SCALPING_V63_MIN_OOS_COVERAGE)
    candidates: list[dict[str, Any]] = []
    for threshold in np.arange(minimum, maximum + 0.0001, 0.01):
        selected = probability >= threshold
        metrics = _metrics(pnl, target, selected)
        if metrics["trades"] < minimum_trades:
            continue
        metrics["threshold"] = round(float(threshold), 4)
        wins = int(np.asarray(target, dtype=int)[selected].sum())
        metrics["win_rate_lower_bound"] = _wilson_lower_bound(
            wins, metrics["trades"], float(scalping_settings.SCALPING_V632_WIN_RATE_CONFIDENCE_Z)
        )
        metrics["passes"] = bool(
            metrics["coverage"] >= minimum_coverage
            and metrics["win_rate"] >= float(scalping_settings.SCALPING_V63_MIN_OOS_WIN_RATE)
            and metrics["win_rate_lower_bound"] >= float(scalping_settings.SCALPING_V632_MIN_OOS_WIN_RATE_LOWER_BOUND)
            and metrics["expectancy"] >= float(scalping_settings.SCALPING_V63_MIN_OOS_EXPECTANCY_USD)
            and metrics["profit_factor"] >= float(scalping_settings.SCALPING_V63_MIN_OOS_PROFIT_FACTOR)
        )
        metrics["utility"] = float(
            metrics["expectancy"] * math.sqrt(max(metrics["trades"], 1))
            + 0.05 * min(metrics["profit_factor"], 3.0)
            + 0.10 * metrics["win_rate"]
        )
        candidates.append(metrics)
    passing = [item for item in candidates if item["passes"]]
    pool = passing or candidates
    if not pool:
        return {
            "threshold": maximum,
            "trades": 0,
            "coverage": 0.0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "passes": False,
            "utility": -999.0,
        }
    return max(pool, key=lambda item: (bool(item["passes"]), item["utility"], item["trades"]))


def _permutation_brier_importance(
    model: ChronologicallyCalibratedModel, test: pd.DataFrame, *, repeats: int
) -> list[dict[str, Any]]:
    if test.empty or test["target"].nunique() < 2:
        return []
    if os.environ.get("SCALPING_FAST_TEST_MODE", "0") == "1":
        test = test.tail(min(len(test), 80)).copy()
        repeats = 1
    baseline_probability = np.asarray(model.predict_proba(test[ALL_FEATURES])[:, 1], dtype=float)
    baseline = _brier(test["target"].to_numpy(int), baseline_probability)
    rng = np.random.default_rng(20260720)
    results: list[dict[str, Any]] = []
    for name in ALL_FEATURES:
        deltas: list[float] = []
        for _ in range(max(1, repeats)):
            shuffled = test[ALL_FEATURES].copy()
            shuffled[name] = rng.permutation(shuffled[name].to_numpy())
            probability = np.asarray(model.predict_proba(shuffled)[:, 1], dtype=float)
            deltas.append(_brier(test["target"].to_numpy(int), probability) - baseline)
        results.append({
            "feature": name,
            "mean_brier_degradation": round(float(np.mean(deltas)), 8),
            "std_brier_degradation": round(float(np.std(deltas)), 8),
        })
    return sorted(results, key=lambda item: item["mean_brier_degradation"], reverse=True)


def _reference_distribution(frame: pd.DataFrame) -> dict[str, Any]:
    reference: dict[str, Any] = {}
    for name in NUMERIC_FEATURES:
        values = pd.to_numeric(frame[name], errors="coerce").dropna().to_numpy(float)
        if values.size < 10:
            continue
        edges = np.unique(np.quantile(values, np.linspace(0.0, 1.0, 11)))
        if len(edges) < 3:
            continue
        edges[0] = -np.inf
        edges[-1] = np.inf
        counts, _ = np.histogram(values, bins=edges)
        proportions = (counts + 0.5) / (counts.sum() + 0.5 * len(counts))
        reference[name] = {"edges": edges.tolist(), "proportions": proportions.tolist()}
    return reference


def _atomic_joblib(path_value: str, payload: Any) -> str:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent), delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        joblib.dump(payload, temp_path)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return str(path)


def _load_json(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_report(report: dict[str, Any]) -> str:
    return atomic_write_json(str(scalping_settings.SCALPING_V63_MODEL_REPORT_PATH), report, indent=2)


def train_v63_self_learner(*, force: bool = False, promote: bool = True) -> dict[str, Any]:
    frame = load_v63_training_frame()
    minimum = int(scalping_settings.SCALPING_V63_MIN_CLOSED_TRADES_TO_TRAIN)
    base_report: dict[str, Any] = {
        "generated_at": _now_iso(),
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "training_rows": int(len(frame)),
        "raw_closed_rows": int(frame.attrs.get("raw_closed_rows", len(frame))),
        "pre_dedup_rows": int(frame.attrs.get("pre_dedup_rows", len(frame))),
        "decorrelated_episode_rows": int(frame.attrs.get("decorrelated_rows", len(frame))),
        "learned_lane_excluded_from_training": bool(frame.attrs.get("excluded_learned_lane", True)),
        "minimum_training_rows": minimum,
        "synthetic_data_used": False,
        "chronological_validation": True,
        "purged_overlapping_folds": True,
        "untouched_final_holdout": bool(
            getattr(scalping_settings, "SCALPING_V632_UNTOUCHED_HOLDOUT_ENABLED", True)
        ),
        "target_win_rate": float(scalping_settings.SCALPING_V63_TARGET_WIN_RATE),
    }
    if len(frame) < minimum:
        report = {
            **base_report,
            "status": "INSUFFICIENT_DATA",
            "approved": False,
            "promoted": False,
            "reason": f"Need at least {minimum} closed shadow trades; found {len(frame)}.",
        }
        report["report_path"] = _write_report(report)
        return report
    boundaries = _fold_boundaries(len(frame))
    if len(boundaries) < int(scalping_settings.SCALPING_V63_MIN_WALK_FORWARD_FOLDS):
        report = {
            **base_report,
            "status": "INSUFFICIENT_WALK_FORWARD_DATA",
            "approved": False,
            "promoted": False,
            "walk_forward_folds": len(boundaries),
        }
        report["report_path"] = _write_report(report)
        return report

    candidates: list[dict[str, Any]] = []
    for model_name in ("LOGISTIC", "LOGISTIC_BALANCED", "RANDOM_FOREST", "GRADIENT_BOOSTING"):
        probabilities: list[float] = []
        targets: list[int] = []
        pnls: list[float] = []
        regimes: list[str] = []
        fold_reports: list[dict[str, Any]] = []
        last_successful_model: ChronologicallyCalibratedModel | None = None
        last_successful_test = pd.DataFrame()
        for fold_index, (start, end) in enumerate(boundaries, start=1):
            test = frame.iloc[start:end].copy()
            train = frame.iloc[:start].copy()
            if test.empty:
                continue
            # Purged walk-forward validation: a training outcome may not overlap the
            # first opening time in the test fold. This prevents a still-open market
            # episode from leaking future path information into validation.
            first_test_open = test["opened_at"].min()
            unpurged_train_rows = int(len(train))
            if pd.notna(first_test_open):
                train = train[train["closed_at"] < first_test_open].copy()
            purged_rows = unpurged_train_rows - int(len(train))
            if train["target"].nunique() < 2 or len(train) < 20:
                fold_reports.append(
                    {
                        "fold": fold_index,
                        "skipped": True,
                        "reason": "insufficient_purged_training_classes_or_rows",
                        "train_rows_before_purge": unpurged_train_rows,
                        "train_rows_after_purge": int(len(train)),
                        "purged_overlap_rows": purged_rows,
                    }
                )
                continue
            try:
                model = _fit_calibrated(model_name, train)
                probability = np.asarray(model.predict_proba(test[ALL_FEATURES])[:, 1], dtype=float)
            except Exception as exc:
                fold_reports.append({"fold": fold_index, "error": str(exc)})
                continue
            oos_start = len(probabilities)
            probabilities.extend(probability.tolist())
            targets.extend(test["target"].astype(int).tolist())
            pnls.extend(test["pnl"].astype(float).tolist())
            regimes.extend(test["regime"].astype(str).tolist())
            oos_end = len(probabilities)
            last_successful_model = model
            last_successful_test = test.copy()
            fold_reports.append(
                {
                    "fold": fold_index,
                    "train_rows": int(len(train)),
                    "train_rows_before_purge": unpurged_train_rows,
                    "purged_overlap_rows": purged_rows,
                    "test_rows": int(len(test)),
                    "test_start": test["closed_at"].min().isoformat(),
                    "test_end": test["closed_at"].max().isoformat(),
                    "oos_start": oos_start,
                    "oos_end": oos_end,
                }
            )
        probability_array = np.asarray(probabilities, dtype=float)
        target_array = np.asarray(targets, dtype=int)
        pnl_array = np.asarray(pnls, dtype=float)
        if not len(probability_array):
            continue
        valid_folds = [
            fold for fold in fold_reports
            if not fold.get("skipped") and not fold.get("error") and "oos_start" in fold
        ]
        holdout_enabled = bool(
            getattr(scalping_settings, "SCALPING_V632_UNTOUCHED_HOLDOUT_ENABLED", True)
        )
        holdout_fold = valid_folds[-1] if holdout_enabled and len(valid_folds) >= 2 else None
        development_end = (
            int(holdout_fold["oos_start"]) if holdout_fold is not None else len(probability_array)
        )
        # Select the deployable cutoff without looking at the final chronological
        # fold. Reusing the same OOS observations for cutoff optimization and
        # approval is a subtle form of backtest selection bias.
        threshold = _select_threshold(
            probability_array[:development_end],
            target_array[:development_end],
            pnl_array[:development_end],
        )
        selected_threshold = float(threshold.get("threshold", scalping_settings.SCALPING_V63_MAX_PROBABILITY_THRESHOLD))
        holdout_metrics: dict[str, Any] = {
            "enabled": holdout_enabled,
            "available": holdout_fold is not None,
            "passes": not holdout_enabled,
            "reason": "disabled" if not holdout_enabled else "unavailable",
        }
        if holdout_fold is not None:
            holdout_start = int(holdout_fold["oos_start"])
            holdout_end = int(holdout_fold["oos_end"])
            holdout_selected = probability_array[holdout_start:holdout_end] >= selected_threshold
            holdout_metrics = _metrics(
                pnl_array[holdout_start:holdout_end],
                target_array[holdout_start:holdout_end],
                holdout_selected,
            )
            holdout_wins = int(target_array[holdout_start:holdout_end][holdout_selected].sum())
            holdout_metrics.update(
                {
                    "enabled": True,
                    "available": True,
                    "fold": holdout_fold.get("fold"),
                    "test_start": holdout_fold.get("test_start"),
                    "test_end": holdout_fold.get("test_end"),
                    "win_rate_lower_bound": _wilson_lower_bound(
                        holdout_wins,
                        int(holdout_metrics["trades"]),
                        float(scalping_settings.SCALPING_V632_WIN_RATE_CONFIDENCE_Z),
                    ),
                }
            )
            holdout_metrics["passes"] = bool(
                int(holdout_metrics["trades"])
                >= int(getattr(scalping_settings, "SCALPING_V632_MIN_HOLDOUT_SELECTED_TRADES", 5))
                and float(holdout_metrics["win_rate"])
                >= float(scalping_settings.SCALPING_V63_MIN_OOS_WIN_RATE)
                and float(holdout_metrics["win_rate_lower_bound"])
                >= float(scalping_settings.SCALPING_V632_MIN_OOS_WIN_RATE_LOWER_BOUND)
                and float(holdout_metrics["expectancy"])
                >= float(scalping_settings.SCALPING_V63_MIN_OOS_EXPECTANCY_USD)
                and float(holdout_metrics["profit_factor"])
                >= float(scalping_settings.SCALPING_V63_MIN_OOS_PROFIT_FACTOR)
            )
            holdout_metrics["reason"] = (
                "untouched_holdout_passed"
                if holdout_metrics["passes"]
                else "untouched_holdout_failed"
            )
        selected_fold_metrics: list[dict[str, Any]] = []
        for fold in fold_reports:
            if fold.get("skipped") or fold.get("error") or "oos_start" not in fold:
                continue
            fold_start = int(fold["oos_start"])
            fold_end = int(fold["oos_end"])
            fold_selected = probability_array[fold_start:fold_end] >= selected_threshold
            fold_metrics = _metrics(
                pnl_array[fold_start:fold_end], target_array[fold_start:fold_end], fold_selected
            )
            fold_metrics.update({"fold": fold.get("fold"), "test_start": fold.get("test_start"), "test_end": fold.get("test_end")})
            selected_fold_metrics.append(fold_metrics)
        eligible_fold_metrics = [
            item for item in selected_fold_metrics
            if int(item.get("trades", 0)) >= int(scalping_settings.SCALPING_V632_MIN_SELECTED_TRADES_PER_FOLD)
        ]
        negative_selected_folds = sum(
            1 for item in eligible_fold_metrics
            if float(item.get("expectancy", 0.0)) < 0.0 or float(item.get("profit_factor", 0.0)) < 1.0
        )
        fold_stability_passed = bool(
            len(eligible_fold_metrics) >= int(scalping_settings.SCALPING_V632_MIN_SELECTED_FOLDS)
            and negative_selected_folds <= int(scalping_settings.SCALPING_V632_MAX_NEGATIVE_SELECTED_FOLDS)
        )
        regime_array = np.asarray(regimes, dtype=object)
        regime_thresholds: dict[str, Any] = {}
        development_regimes = regime_array[:development_end]
        for regime_name in sorted(set(development_regimes.tolist())):
            regime_mask = development_regimes == regime_name
            if int(regime_mask.sum()) < int(scalping_settings.SCALPING_V63_MIN_REGIME_SAMPLES):
                continue
            result = _select_threshold(
                probability_array[:development_end][regime_mask],
                target_array[:development_end][regime_mask],
                pnl_array[:development_end][regime_mask],
            )
            if bool(result.get("passes", False)):
                regime_thresholds[str(regime_name)] = result
        brier = _brier(target_array, probability_array)
        ece = _ece(target_array, probability_array)
        approved = bool(
            threshold.get("passes", False)
            and brier <= float(scalping_settings.SCALPING_V63_MAX_OOS_BRIER_SCORE)
            and ece <= float(scalping_settings.SCALPING_V63_MAX_OOS_CALIBRATION_ERROR)
            and len(fold_reports) >= int(scalping_settings.SCALPING_V63_MIN_WALK_FORWARD_FOLDS)
            and fold_stability_passed
            and bool(holdout_metrics.get("passes", False))
        )
        permutation_importance = (
            _permutation_brier_importance(
                last_successful_model,
                last_successful_test,
                repeats=int(scalping_settings.SCALPING_V632_PERMUTATION_IMPORTANCE_REPEATS),
            )[:15]
            if last_successful_model is not None and not last_successful_test.empty
            else []
        )
        candidates.append(
            {
                "model_name": model_name,
                "approved": approved,
                "oos_rows": int(len(probability_array)),
                "brier_score": round(brier, 6),
                "expected_calibration_error": round(ece, 6),
                "selection": threshold,
                "threshold_selection_rows": int(development_end),
                "untouched_holdout": holdout_metrics,
                "regime_thresholds": regime_thresholds,
                "folds": fold_reports,
                "selected_fold_metrics": selected_fold_metrics,
                "eligible_selected_folds": len(eligible_fold_metrics),
                "negative_selected_folds": negative_selected_folds,
                "fold_stability_passed": fold_stability_passed,
                "permutation_brier_importance": permutation_importance,
                "rank_score": float(threshold.get("utility", -999.0)) - brier - ece,
            }
        )
    if not candidates:
        report = {**base_report, "status": "MODEL_TRAINING_FAILED", "approved": False, "promoted": False}
        report["report_path"] = _write_report(report)
        return report

    approved_candidates = [item for item in candidates if item["approved"]]
    best = max(approved_candidates or candidates, key=lambda item: item["rank_score"])
    final_model = _fit_calibrated(best["model_name"], frame)
    artifact = {
        # Format 3 requires an untouched final chronological holdout. Older
        # artifacts were allowed to tune and assess their cutoff on the same
        # pooled OOS predictions and are intentionally incompatible.
        "format_version": 3,
        "created_at": _now_iso(),
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "approved": bool(best["approved"]),
        "model_name": best["model_name"],
        "model": final_model,
        "threshold": float(best["selection"]["threshold"]),
        "regime_thresholds": best.get("regime_thresholds", {}),
        "target_win_rate": float(scalping_settings.SCALPING_V63_TARGET_WIN_RATE),
        "training_rows": int(len(frame)),
        "training_last_closed_at": frame["closed_at"].max().isoformat(),
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "reference_distribution": _reference_distribution(frame),
        "regime_counts": frame["regime"].value_counts().to_dict(),
        "validation": best,
    }
    challenger_path = _atomic_joblib(str(scalping_settings.SCALPING_V63_CHALLENGER_MODEL_PATH), artifact)

    registry = _load_json(str(scalping_settings.SCALPING_V63_MODEL_REGISTRY_PATH))
    champion_path = Path(scalping_settings.SCALPING_V63_CHAMPION_MODEL_PATH)
    old_utility = -999.0
    if champion_path.exists():
        try:
            old_artifact = joblib.load(champion_path)
            old_utility = float(old_artifact.get("validation", {}).get("rank_score", -999.0))
        except Exception:
            old_utility = -999.0
    promote_model = bool(best["approved"] and promote and (not champion_path.exists() or best["rank_score"] > old_utility + 0.01))
    if promote_model:
        _atomic_joblib(str(champion_path), artifact)
    registry.update(
        {
            "updated_at": _now_iso(),
            "last_training_rows": int(len(frame)),
            "last_training_attempt_at": _now_iso(),
            "last_challenger_approved": bool(best["approved"]),
            "last_challenger_model": best["model_name"],
            "champion_present": champion_path.exists(),
            "champion_promoted_this_run": promote_model,
            "challenger_path": challenger_path,
            "champion_path": str(champion_path),
        }
    )
    atomic_write_json(str(scalping_settings.SCALPING_V63_MODEL_REGISTRY_PATH), registry, indent=2)
    report = {
        **base_report,
        "status": "APPROVED_CHALLENGER" if best["approved"] else "RESEARCH_ONLY_CHALLENGER",
        "approved": bool(best["approved"]),
        "promoted": promote_model,
        "best_model": best,
        "all_models": candidates,
        "champion_path": str(champion_path),
        "challenger_path": challenger_path,
    }
    report["report_path"] = _write_report(report)
    if champion_path.exists():
        build_v63_drift_report()
    return report


def _psi(reference: dict[str, Any], values: np.ndarray) -> float:
    edges = np.asarray(reference.get("edges", []), dtype=float)
    expected = np.asarray(reference.get("proportions", []), dtype=float)
    if len(edges) < 3 or len(expected) != len(edges) - 1 or not len(values):
        return 0.0
    counts, _ = np.histogram(values, bins=edges)
    actual = (counts + 0.5) / (counts.sum() + 0.5 * len(counts))
    expected = np.clip(expected, 1e-6, None)
    actual = np.clip(actual, 1e-6, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def build_v63_drift_report() -> dict[str, Any]:
    champion_path = Path(scalping_settings.SCALPING_V63_CHAMPION_MODEL_PATH)
    frame = load_v63_training_frame()
    if not champion_path.exists() or frame.empty:
        report = {
            "generated_at": _now_iso(),
            "status": "NO_CHAMPION_OR_DATA",
            "blocked": True,
            "maximum_psi": 999.0,
        }
        atomic_write_json(str(scalping_settings.SCALPING_V63_DRIFT_REPORT_PATH), report, indent=2)
        return report
    try:
        artifact = joblib.load(champion_path)
    except Exception as exc:
        report = {"generated_at": _now_iso(), "status": "CHAMPION_UNREADABLE", "blocked": True, "error": str(exc)}
        atomic_write_json(str(scalping_settings.SCALPING_V63_DRIFT_REPORT_PATH), report, indent=2)
        return report
    recent_n = int(scalping_settings.SCALPING_V63_DRIFT_RECENT_TRADES)
    recent = frame.tail(recent_n)
    features: dict[str, float] = {}
    for name, reference in dict(artifact.get("reference_distribution", {})).items():
        # Cyclical clock features naturally shift across a session and should
        # not independently disable the model. Session remains a categorical
        # feature, while drift focuses on tradability/evidence variables.
        if name in {"hour_sin", "hour_cos"}:
            continue
        values = pd.to_numeric(recent.get(name), errors="coerce").dropna().to_numpy(float)
        features[name] = round(_psi(reference, values), 6)
    maximum = max(features.values(), default=0.0)
    mean = float(np.mean(list(features.values()))) if features else 0.0
    block_level = float(scalping_settings.SCALPING_V63_DRIFT_PSI_BLOCK)
    warning_level = float(scalping_settings.SCALPING_V63_DRIFT_PSI_WARNING)
    blocking_features = [name for name, value in features.items() if value >= block_level]
    minimum_blocking_features = max(3, int(math.ceil(max(len(features), 1) * 0.20)))
    blocked = bool(len(blocking_features) >= minimum_blocking_features or mean >= block_level)
    warning = bool(blocked or maximum >= warning_level or mean >= warning_level * 0.75)
    report = {
        "generated_at": _now_iso(),
        "status": "BLOCK" if blocked else "WARNING" if warning else "OK",
        "blocked": blocked,
        "blocking_features": blocking_features,
        "minimum_blocking_features": minimum_blocking_features,
        "recent_trades": int(len(recent)),
        "maximum_psi": round(maximum, 6),
        "mean_psi": round(mean, 6),
        "feature_psi": features,
    }
    atomic_write_json(str(scalping_settings.SCALPING_V63_DRIFT_REPORT_PATH), report, indent=2)
    return report


def load_v63_champion_status() -> dict[str, Any]:
    path = Path(scalping_settings.SCALPING_V63_CHAMPION_MODEL_PATH)
    if not path.exists():
        return {"available": False, "approved": False, "reason": "No approved V6.3 champion model exists."}
    try:
        artifact = joblib.load(path)
    except Exception as exc:
        return {"available": False, "approved": False, "reason": f"Champion model unreadable: {exc}"}
    created = pd.to_datetime(artifact.get("created_at"), utc=True, errors="coerce")
    age_days = float((pd.Timestamp.now(tz="UTC") - created).total_seconds() / 86400.0) if not pd.isna(created) else 999.0
    drift = _load_json(str(scalping_settings.SCALPING_V63_DRIFT_REPORT_PATH))
    strategy_compatible = str(artifact.get("strategy_id", "")) == str(scalping_settings.SCALPING_STRATEGY_ID)
    feature_schema_compatible = bool(
        list(artifact.get("numeric_features", [])) == list(NUMERIC_FEATURES)
        and list(artifact.get("categorical_features", [])) == list(CATEGORICAL_FEATURES)
    )
    format_compatible = int(artifact.get("format_version", 0) or 0) >= 3
    approved = bool(
        artifact.get("approved", False)
        and age_days <= float(scalping_settings.SCALPING_V63_MODEL_MAX_AGE_DAYS)
        and not bool(drift.get("blocked", False))
        and strategy_compatible
        and feature_schema_compatible
        and format_compatible
    )
    incompatibilities = []
    if not strategy_compatible:
        incompatibilities.append("strategy_id")
    if not feature_schema_compatible:
        incompatibilities.append("feature_schema")
    if not format_compatible:
        incompatibilities.append("artifact_format")
    return {
        "available": True,
        "approved": approved,
        "model_name": artifact.get("model_name"),
        "threshold": artifact.get("threshold"),
        "training_rows": artifact.get("training_rows"),
        "created_at": artifact.get("created_at"),
        "age_days": round(age_days, 4),
        "drift": drift,
        "strategy_compatible": strategy_compatible,
        "feature_schema_compatible": feature_schema_compatible,
        "format_compatible": format_compatible,
        "incompatibilities": incompatibilities,
        "reason": (
            "Champion ready."
            if approved
            else "Champion is stale, unapproved, drift-blocked, or incompatible with the current strategy schema."
        ),
    }


def score_v63_profile(profile: dict[str, Any], *, source_lane: str = "EXPLORATORY") -> dict[str, Any]:
    path = Path(scalping_settings.SCALPING_V63_CHAMPION_MODEL_PATH)
    status = load_v63_champion_status()
    if not status.get("approved", False) or not path.exists():
        return {
            "available": bool(status.get("available", False)),
            "approved_model": False,
            "allowed": False,
            "probability_win": 0.0,
            "threshold": status.get("threshold"),
            "reason": status.get("reason", "No approved champion."),
            "status": status,
        }
    artifact = joblib.load(path)
    frame = pd.DataFrame([feature_row_from_profile(profile, source_lane=source_lane, opened_at=_now_iso())])
    probability = float(artifact["model"].predict_proba(frame[ALL_FEATURES])[:, 1][0])
    global_threshold = float(artifact.get("threshold", scalping_settings.SCALPING_V63_TARGET_WIN_RATE))
    regime = _text(profile.get("regime"), "UNKNOWN")
    regime_result = dict(artifact.get("regime_thresholds", {})).get(regime, {})
    threshold = float(regime_result.get("threshold", global_threshold))
    regime_count = int(dict(artifact.get("regime_counts", {})).get(regime, 0))
    regime_supported = regime_count >= int(scalping_settings.SCALPING_V63_MIN_REGIME_SAMPLES)
    allowed = probability >= threshold and regime_supported
    return {
        "available": True,
        "approved_model": True,
        "allowed": allowed,
        "probability_win": round(probability, 6),
        "threshold": round(threshold, 6),
        "global_threshold": round(global_threshold, 6),
        "regime_specific_threshold": bool(regime_result),
        "model_name": artifact.get("model_name"),
        "training_rows": artifact.get("training_rows"),
        "regime": regime,
        "regime_samples": regime_count,
        "regime_supported": regime_supported,
        "reason": (
            "Calibrated probability and regime support passed."
            if allowed
            else "Calibrated probability below threshold or regime sample is insufficient."
        ),
    }


def maybe_retrain_v63_model(*, force: bool = False) -> dict[str, Any]:
    if not bool(getattr(scalping_settings, "SCALPING_V63_SELF_LEARNING_ENABLED", True)):
        return {"attempted": False, "reason": "V6.3 self-learning disabled."}
    frame = load_v63_training_frame()
    registry = _load_json(str(scalping_settings.SCALPING_V63_MODEL_REGISTRY_PATH))
    last_rows = int(registry.get("last_training_rows", 0) or 0)
    increment = int(scalping_settings.SCALPING_V63_RETRAIN_EVERY_CLOSED_TRADES)
    if not force and len(frame) - last_rows < increment:
        return {
            "attempted": False,
            "closed_trades": int(len(frame)),
            "last_training_rows": last_rows,
            "next_retrain_at": last_rows + increment,
            "reason": "Waiting for additional closed trades.",
        }
    report = train_v63_self_learner(force=force, promote=True)
    return {"attempted": True, "report": report}


def print_v63_self_learning_report(report: dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print("V6.3 CALIBRATED SELF-LEARNING REVIEW")
    print("=" * 78)
    print(f"Status: {report.get('status')} | rows={report.get('training_rows', 0)}")
    best = report.get("best_model") if isinstance(report.get("best_model"), dict) else None
    if best:
        selection = best.get("selection", {})
        print(
            f"Model={best.get('model_name')} approved={'YES' if best.get('approved') else 'NO'} "
            f"threshold={selection.get('threshold')} selected={selection.get('trades')} "
            f"WR={float(selection.get('win_rate',0))*100:.1f}% "
            f"expectancy=${float(selection.get('expectancy',0)):.3f} "
            f"PF={float(selection.get('profit_factor',0)):.2f} "
            f"coverage={float(selection.get('coverage',0))*100:.1f}% "
            f"Brier={float(best.get('brier_score',0)):.3f} ECE={float(best.get('expected_calibration_error',0)):.3f}"
        )
    print(f"Promoted champion: {'YES' if report.get('promoted') else 'NO'}")
    print("Synthetic data: NO | Validation: chronological walk-forward")
    print("=" * 78)
