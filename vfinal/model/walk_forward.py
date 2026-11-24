from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .calibration import apply_calibrator, fit_logistic_calibrator
from .metrics import metrics
from ..config import (
    CALIBRATION_FRACTION, HOLDOUT_FRACTION, MAX_HOLDOUT_BRIER,
    MAX_HOLDOUT_ECE, MIN_FOLDS, MIN_HOLDOUT_PF, MIN_HOLDOUT_TRADES,
    MIN_HOLDOUT_WIN_RATE, MIN_PROBABILITY, MIN_TRAIN_ROWS_PER_FOLD,
    PURGE_SECONDS,
    HORIZONS_SECONDS,
)

NUMERIC = [
    "spread", "spread_atr", "m1_atr", "m1_rsi", "m1_adx", "m1_ema12_slope_atr", "m1_ema26_slope_atr", "m1_ema_gap_atr",
    "m5_atr", "m5_rsi", "m5_adx", "m5_ema_gap_atr", "m15_atr", "m15_rsi", "m15_adx", "h1_atr", "h1_rsi", "h1_adx", "h4_atr", "h4_rsi", "h4_adx",
    "tick_imbalance_1s", "tick_imbalance_5s", "quote_pressure_1s", "quote_pressure_5s", "velocity_1s", "velocity_5s", "efficiency_1s", "efficiency_5s",
    "reversal_1s", "reversal_5s", "spread_mean_1s", "spread_mean_5s", "spread_std_5s", "spread_expansion_5s", "tick_rate_5s", "realized_move_5s",
    "vwap_distance_atr", "verified_data_quality", "structure_confidence", "structure_votes", "structure_room_usd", "structure_location_safe",
    "news_bias_value", "news_provider_quality", "news_provider_conflict", "news_relevant_count", "macro_us10y_change_5", "macro_us10y_real_change_5", "macro_us2y_change_5", "macro_usd_broad_change_5", "macro_vix_change_5",
    "macro_gold_pressure_raw", "macro_available", "macro_training_safe", "hour_sin", "hour_cos",
]
CATEGORICAL = [
    "session", "source_lane", "direction", "verified_trend_direction", "verified_liquidity_regime", "structure_direction", "htf_direction", "level_direction", "order_block_direction",
    "news_directional_bias", "news_data_mode", "macro_gold_bias",
]
ALL_FEATURES = NUMERIC + CATEGORICAL


@dataclass
class FittedModel:
    estimator: object
    calibrator: object | None
    features: list[str]

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        raw = self.estimator.predict_proba(frame[self.features])[:, 1]
        calibrated = apply_calibrator(self.calibrator, raw)
        return np.column_stack([1-calibrated, calibrated])


def _pipeline(kind: str) -> Pipeline:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    pre = ColumnTransformer([("num", numeric, NUMERIC), ("cat", categorical, CATEGORICAL)], remainder="drop")
    if kind == "LOGISTIC":
        model = LogisticRegression(C=0.35, max_iter=3000, class_weight="balanced", solver="liblinear", random_state=2026)
    elif kind == "RF":
        model = RandomForestClassifier(n_estimators=400, max_depth=7, min_samples_leaf=6, class_weight="balanced_subsample", n_jobs=-1, random_state=2026)
    else:
        model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.04, max_leaf_nodes=15, l2_regularization=1.0, random_state=2026)
    return Pipeline([("pre", pre), ("model", model)])


def chronological_folds(n: int, min_train: int, folds: int, holdout_fraction: float, purge: int) -> list[tuple[int,int,int,int]]:
    holdout_start = int(n * (1 - holdout_fraction))
    dev_n = holdout_start
    if dev_n < min_train + folds * 5: return []
    test_size = max(10, (dev_n - min_train) // folds)
    result = []
    for i in range(folds):
        test_start = min_train + i * test_size
        test_end = min(dev_n, test_start + test_size)
        train_end = max(0, test_start - purge)
        if train_end < min_train or test_end <= test_start: continue
        result.append((0, train_end, test_start, test_end))
    return result


def _time_purged_train_end(data: pd.DataFrame, test_start: int, purge_seconds: int) -> int:
    """Return the exclusive train boundary using elapsed time, not row count."""
    if test_start <= 0 or purge_seconds <= 0:
        return max(0, test_start)
    timestamps = pd.to_datetime(data["snapshot_timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("snapshot_timestamp contains missing or invalid timestamps")
    cutoff = timestamps.iloc[test_start] - pd.Timedelta(seconds=int(purge_seconds))
    return int(timestamps.searchsorted(cutoff, side="right"))


def purged_history(data: pd.DataFrame, boundary: int, purge_seconds: int) -> pd.DataFrame:
    if boundary <= 0:
        return data.iloc[:0].copy()
    if boundary >= len(data):
        raise ValueError("A purge boundary requires a later observation")
    timestamps = pd.to_datetime(data["snapshot_timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("snapshot_timestamp must be valid and chronological")
    if "horizon_seconds" in data:
        horizons = pd.to_numeric(data["horizon_seconds"], errors="coerce")
    elif "horizon" in data:
        horizons = data["horizon"].map(HORIZONS_SECONDS)
    else:
        raise ValueError("horizon_seconds or a known horizon is required to purge future labels")
    if not np.isfinite(horizons).all() or (horizons <= 0).any():
        raise ValueError("Every label needs a finite positive horizon_seconds")
    history_end = _time_purged_train_end(data, boundary, max(0, purge_seconds))
    history = data.iloc[:min(boundary, history_end)].copy()
    label_ends = timestamps.iloc[:len(history)] + pd.to_timedelta(horizons.iloc[:len(history)], unit="s")
    return history.loc[label_ends < timestamps.iloc[boundary]]


def calibration_split(data: pd.DataFrame, min_train: int, purge_seconds: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    cal_rows = max(20, int(len(data) * CALIBRATION_FRACTION))
    cal_start = len(data) - cal_rows
    if cal_start <= 0:
        return data.iloc[:0].copy(), data.iloc[:0].copy()
    fit = purged_history(data, cal_start, purge_seconds)
    cal = data.iloc[cal_start:].copy()
    if len(fit) < min_train:
        return data.iloc[:0].copy(), cal
    return fit, cal


def non_overlapping_selection(data: pd.DataFrame, eligible: np.ndarray) -> np.ndarray:
    timestamps = pd.to_datetime(data["snapshot_timestamp"], utc=True)
    horizons = (pd.to_numeric(data["horizon_seconds"]) if "horizon_seconds" in data
                else data["horizon"].map(HORIZONS_SECONDS))
    selected = np.zeros(len(data), dtype=bool)
    available = None
    for index, (stamp, horizon, allowed) in enumerate(zip(timestamps, horizons, eligible)):
        if allowed and (available is None or stamp >= available):
            selected[index] = True
            available = stamp + pd.Timedelta(seconds=float(horizon))
    return selected


def walk_forward_evaluate(frame: pd.DataFrame, target_col: str, pnl_col: str, *,
                          purge: int = PURGE_SECONDS, folds: int = MIN_FOLDS,
                          min_train: int = MIN_TRAIN_ROWS_PER_FOLD) -> dict:
    if "snapshot_timestamp" not in frame.columns:
        return {"approved": False, "reason": "snapshot_timestamp is required for chronological validation."}
    data = frame.dropna(subset=[target_col, pnl_col]).copy()
    data["snapshot_timestamp"] = pd.to_datetime(data["snapshot_timestamp"], utc=True, errors="coerce")
    if data["snapshot_timestamp"].isna().any():
        return {"approved": False, "reason": "Invalid snapshot_timestamp in chronological validation."}
    data = data.sort_values("snapshot_timestamp", kind="stable").reset_index(drop=True)
    if data[target_col].nunique() < 2:
        return {"approved": False, "reason": "Training data contains only one target class."}
    holdout_start = int(len(data) * (1.0 - HOLDOUT_FRACTION))
    try:
        development = purged_history(data, holdout_start, purge)
    except ValueError as error:
        return {"approved": False, "reason": str(error)}
    holdout = data.iloc[holdout_start:].copy()
    # Generate row boundaries without a row-based gap, then enforce the configured
    # elapsed-time purge against each fold's first test timestamp.
    initial_train = max(min_train + 40, int(holdout_start * 0.4))
    raw_folds = chronological_folds(len(data), initial_train, folds, HOLDOUT_FRACTION, 0)
    fold_defs = [(start, _time_purged_train_end(data, test_start, purge), test_start, test_end)
                 for start, _, test_start, test_end in raw_folds]
    fold_defs = [item for item in fold_defs if item[1] >= min_train]
    reports = {}
    for kind in ("LOGISTIC", "RF", "HGB"):
        probabilities = np.full(holdout_start, np.nan)
        completed_folds = 0
        for _, train_end, test_start, test_end in fold_defs:
            train = purged_history(data, test_start, purge)
            test = data.iloc[test_start:test_end]
            if train[target_col].nunique() < 2: continue
            fit, cal = calibration_split(train, min_train, purge)
            if fit.empty or fit[target_col].nunique() < 2 or cal[target_col].nunique() < 2:
                continue
            est = _pipeline(kind)
            est.fit(fit[ALL_FEATURES], fit[target_col].astype(int))
            raw = est.predict_proba(test[ALL_FEATURES])[:,1]
            calibrator = fit_logistic_calibrator(est.predict_proba(cal[ALL_FEATURES])[:,1], cal[target_col].astype(int).to_numpy()) if len(cal) >= 20 and cal[target_col].nunique() == 2 else None
            probabilities[test_start:test_end] = apply_calibrator(calibrator, raw)
            completed_folds += 1
        valid = np.isfinite(probabilities)
        valid &= np.isin(np.arange(holdout_start), development.index)
        if valid.sum() == 0 or completed_folds < folds: continue
        # Threshold is deliberately chosen on development OOS only; the final
        # holdout remains untouched until the model is fully specified.
        y = data.iloc[:holdout_start].loc[valid, target_col].astype(int).to_numpy()
        pnl = data.iloc[:holdout_start].loc[valid, pnl_col].astype(float).to_numpy()
        p = probabilities[valid]
        threshold = 0.55
        best = None
        for t in np.arange(MIN_PROBABILITY, 0.901, 0.01):
            sel = non_overlapping_selection(data.iloc[:holdout_start].loc[valid], p >= t)
            m = metrics(y, p, pnl, sel)
            if m["trades"] < 10: continue
            utility = m["total_pnl"] - 0.5 * max(0.0, 0.52 - m["win_rate"]) * m["trades"]
            if best is None or utility > best["utility"]:
                best = {"threshold": float(t), "utility": float(utility), "metrics": m}
        reports[kind] = {"development": best, "oos_rows": int(valid.sum()), "folds_completed": completed_folds}

    # Final candidate selection uses development OOS only.
    candidates = [(k,v) for k,v in reports.items() if v.get("development")]
    if not candidates: return {"approved": False, "reason": "No valid walk-forward candidate.", "models": reports}
    best_kind, best_report = max(candidates, key=lambda kv: kv[1]["development"]["utility"])
    fit_part, cal = calibration_split(development, min_train, purge)
    if (fit_part.empty or cal.empty or holdout.empty or
            fit_part[target_col].nunique() < 2 or cal[target_col].nunique() < 2):
        return {
            "approved": False,
            "reason": "Insufficient class diversity in final fit, calibration, or holdout split.",
            "selected_model": best_kind,
            "development": best_report["development"],
            "models": reports,
            "purge_seconds": int(purge),
            "folds_used": len(fold_defs),
            "holdout_start": holdout_start,
        }
    final_est = _pipeline(best_kind)
    final_est.fit(fit_part[ALL_FEATURES], fit_part[target_col].astype(int))
    raw_cal = final_est.predict_proba(cal[ALL_FEATURES])[:,1]
    calibrator = fit_logistic_calibrator(raw_cal, cal[target_col].astype(int).to_numpy())
    fitted = FittedModel(final_est, calibrator, ALL_FEATURES)
    holdout_p = fitted.predict_proba(holdout[ALL_FEATURES])[:,1] if not holdout.empty else np.array([])
    holdout_selected = non_overlapping_selection(holdout, holdout_p >= best_report["development"]["threshold"]) if len(holdout_p) else np.array([], dtype=bool)
    holdout_metrics = metrics(holdout[target_col].astype(int), holdout_p, holdout[pnl_col].astype(float), holdout_selected) if len(holdout_p) else {}
    approved = bool(
        holdout_metrics.get("trades", 0) >= MIN_HOLDOUT_TRADES and
        holdout_metrics.get("win_rate", 0) >= MIN_HOLDOUT_WIN_RATE and
        holdout_metrics.get("profit_factor", 0) >= MIN_HOLDOUT_PF and
        holdout_metrics.get("brier", 1) <= MAX_HOLDOUT_BRIER and
        holdout_metrics.get("ece", 1) <= MAX_HOLDOUT_ECE and
        holdout_metrics.get("expectancy", -1) > 0
    )
    return {
        "approved": approved, "selected_model": best_kind, "threshold": best_report["development"]["threshold"],
        "development": best_report["development"], "holdout": holdout_metrics, "models": reports,
        "fitted_model": fitted, "purge_seconds": int(purge),
        "folds_used": len(fold_defs), "holdout_start": holdout_start,
    }
