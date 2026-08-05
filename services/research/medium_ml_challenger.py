from __future__ import annotations

"""Selective cost-aware ML challenger with a sealed chronological holdout."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from services.research.medium_candidate_lab import build_feature_frame


FEATURES = [
    "ret1_atr", "ret3_atr", "ret8_atr", "ema12_26_atr", "ema12_50_atr",
    "rsi_aligned", "adx", "body_signed_atr", "favorable_wick_atr",
    "adverse_wick_atr", "h1_aligned", "h4_aligned", "atr_pct",
    "hour_sin", "hour_cos",
]
INTERMARKET_FEATURES = [
    "usd_pressure_ret1", "usd_pressure_ret4", "usd_pressure_ret24",
    "silver_ret1", "silver_ret4", "silver_ret24",
    "silver_gold_relative_ret1", "silver_gold_relative_ret4", "silver_gold_relative_ret24",
    "equity_risk_ret1", "equity_risk_ret4", "equity_risk_ret24",
    "silver_vol24", "sp500_vol24", "nasdaq_vol24",
]
MACRO_FEATURES = [
    f"macro_{role}_{field}"
    for role in ("dgs10", "broad_usd", "vix", "fed_funds")
    for field in ("level", "change1", "change5", "change20")
]


def _outcomes(
    data: pd.DataFrame,
    direction: int,
    *,
    target: float,
    stop: float,
    max_bars: int,
    spread: float,
    fine_bars: pd.DataFrame | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    high = data["high"].to_numpy(float)
    low = data["low"].to_numpy(float)
    close = data["close"].to_numpy(float)
    entry_mid = data["next_open"].to_numpy(float)
    pnl = np.full(len(data), np.nan if fine_bars is not None else 0.0, dtype=float)
    exit_index = np.arange(len(data), dtype=int)
    if fine_bars is not None:
        fine = fine_bars.copy()
        fine["time"] = pd.to_datetime(fine["time"], utc=True)
        fine = fine.sort_values("time").drop_duplicates("time")
        fine_times = fine["time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        fine_high = fine["high"].to_numpy(float)
        fine_low = fine["low"].to_numpy(float)
        fine_close = fine["close"].to_numpy(float)
        data_times = pd.to_datetime(data["time"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        entry_times = pd.to_datetime(data["entry_time"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        horizon_ns = int(max_bars * 15 * 60 * 1_000_000_000)
        for index in range(len(data)-1):
            start = int(np.searchsorted(fine_times, entry_times[index], side="left"))
            end = int(np.searchsorted(fine_times, entry_times[index]+horizon_ns, side="right"))
            if (
                start >= len(fine_times)
                or end <= start
                or entry_times[index] < fine_times[0]
                or entry_times[index]+horizon_ns > fine_times[-1]
            ):
                continue
            entry = entry_mid[index]+spread/2 if direction == 1 else entry_mid[index]-spread/2
            resolved_at = min(end-1, len(fine_times)-1)
            resolved = False
            for future in range(start, min(end, len(fine_times))):
                if direction == 1:
                    hit_target = fine_high[future] >= entry+target+spread/2
                    hit_stop = fine_low[future] <= entry-stop+spread/2
                else:
                    hit_target = fine_low[future] <= entry-target-spread/2
                    hit_stop = fine_high[future] >= entry+stop-spread/2
                if hit_stop:
                    pnl[index], resolved_at, resolved = -stop, future, True
                    break
                if hit_target:
                    pnl[index], resolved_at, resolved = target, future, True
                    break
            if not resolved:
                quote = fine_close[resolved_at]-spread/2 if direction == 1 else fine_close[resolved_at]+spread/2
                pnl[index] = quote-entry if direction == 1 else entry-quote
            exit_index[index] = int(np.searchsorted(data_times, fine_times[resolved_at], side="right")-1)
        return pnl, exit_index
    for index in range(len(data)-1):
        entry = entry_mid[index] + spread/2 if direction == 1 else entry_mid[index] - spread/2
        final = min(index+max_bars, len(data)-1)
        resolved = False
        for future in range(index+1, final+1):
            if direction == 1:
                hit_target = high[future] >= entry+target+spread/2
                hit_stop = low[future] <= entry-stop+spread/2
            else:
                hit_target = low[future] <= entry-target-spread/2
                hit_stop = high[future] >= entry+stop-spread/2
            if hit_stop:
                pnl[index], exit_index[index], resolved = -stop, future, True
                break
            if hit_target:
                pnl[index], exit_index[index], resolved = target, future, True
                break
        if not resolved:
            quote = close[final]-spread/2 if direction == 1 else close[final]+spread/2
            pnl[index] = quote-entry if direction == 1 else entry-quote
            exit_index[index] = final
    return pnl, exit_index


def _feature_rows(data: pd.DataFrame, direction: int) -> pd.DataFrame:
    atr = data["atr"].clip(lower=0.01)
    result = pd.DataFrame(index=data.index)
    result["ret1_atr"] = data["close"].diff().fillna(0) / atr * direction
    result["ret3_atr"] = data["close"].diff(3).fillna(0) / atr * direction
    result["ret8_atr"] = data["close"].diff(8).fillna(0) / atr * direction
    result["ema12_26_atr"] = (data["ema12"]-data["ema26"]) / atr * direction
    result["ema12_50_atr"] = (data["ema12"]-data["ema50"]) / atr * direction
    result["rsi_aligned"] = 50 + (data["rsi"]-50)*direction
    result["adx"] = data["adx"]
    result["body_signed_atr"] = (data["close"]-data["open"]) / atr * direction
    result["favorable_wick_atr"] = data["lower_wick_atr"] if direction == 1 else data["upper_wick_atr"]
    result["adverse_wick_atr"] = data["upper_wick_atr"] if direction == 1 else data["lower_wick_atr"]
    result["h1_aligned"] = data["H1_direction"]*direction
    result["h4_aligned"] = data["H4_direction"]*direction
    result["atr_pct"] = atr/data["close"]*100
    result["hour_sin"] = np.sin(2*np.pi*data["hour"]/24)
    result["hour_cos"] = np.cos(2*np.pi*data["hour"]/24)
    for name in INTERMARKET_FEATURES:
        if name in data:
            # Directional returns are aligned to the proposed gold side;
            # volatility remains unsigned.
            result[name] = data[name] if name.endswith("vol24") else data[name]*direction
    for name in MACRO_FEATURES:
        if name in data:
            result[name] = data[name] if name.endswith("_level") else data[name]*direction
    return result.replace([np.inf, -np.inf], np.nan).fillna(0)


def _selected_pnls(rows: pd.DataFrame, probabilities: np.ndarray, threshold: float) -> list[float]:
    work = rows.copy()
    work["probability"] = probabilities
    chosen: list[float] = []
    next_free = -1
    for _, group in work[work["probability"] >= threshold].groupby("bar_index", sort=True):
        best = group.sort_values("probability", ascending=False).iloc[0]
        index = int(best["bar_index"])
        if index < next_free:
            continue
        chosen.append(float(best["pnl"]))
        next_free = int(best["exit_index"])+1
    return chosen


def _selection_metrics(rows: pd.DataFrame, probabilities: np.ndarray, threshold: float) -> dict[str, Any]:
    chosen = _selected_pnls(rows, probabilities, threshold)
    values = np.asarray(chosen, dtype=float)
    if not len(values):
        return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "net_profit": 0.0}
    profit, loss = values[values > 0].sum(), -values[values < 0].sum()
    return {
        "trades": int(len(values)),
        "win_rate": round(float((values > 0).mean()), 6),
        "expectancy": round(float(values.mean()), 6),
        "profit_factor": round(float(profit/loss), 6) if loss else 999.0,
        "net_profit": round(float(values.sum()), 4),
    }


def metrics_from_values(chosen: list[float]) -> dict[str, Any]:
    values = np.asarray(chosen, dtype=float)
    if not len(values):
        return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "net_profit": 0.0}
    profit, loss = values[values > 0].sum(), -values[values < 0].sum()
    return {
        "trades": int(len(values)),
        "win_rate": round(float((values > 0).mean()), 6),
        "expectancy": round(float(values.mean()), 6),
        "profit_factor": round(float(profit/loss), 6) if loss else 999.0,
        "net_profit": round(float(values.sum()), 4),
    }


def run_ml_challenger(
    dataset_folder: str,
    *,
    spread: float = 0.30,
    stop: float = 1.80,
    max_bars: int = 16,
    intermarket_folder: str | None = None,
    macro_folder: str | None = None,
    fine_bars_path: str | None = None,
) -> dict[str, Any]:
    data = build_feature_frame(
        dataset_folder,
        intermarket_folder=intermarket_folder,
        macro_folder=macro_folder,
    )
    active_features = (
        FEATURES
        + (INTERMARKET_FEATURES if intermarket_folder else [])
        + (MACRO_FEATURES if macro_folder else [])
    )
    fine_bars = pd.read_csv(fine_bars_path) if fine_bars_path else None
    parts = []
    for direction in (1, -1):
        features = _feature_rows(data, direction)
        pnl, exits = _outcomes(
            data, direction, target=1.50, stop=stop, max_bars=max_bars,
            spread=spread, fine_bars=fine_bars,
        )
        features["time"] = pd.to_datetime(data["time"], utc=True).reset_index(drop=True)
        features["bar_index"] = np.arange(len(data))
        features["exit_index"] = exits
        features["direction"] = direction
        features["pnl"] = pnl
        features["label"] = (pnl > 0).astype(int)
        parts.append(features)
    rows = pd.concat(parts, ignore_index=True).dropna(subset=["pnl"]).sort_values(["time", "direction"]).reset_index(drop=True)
    rows["time"] = pd.to_datetime(rows["time"], utc=True)
    start, end = rows["time"].min(), rows["time"].max()
    train_end = start+(end-start)*0.60
    validation_end = start+(end-start)*0.80
    train = rows[rows["time"] <= train_end]
    validation = rows[(rows["time"] > train_end) & (rows["time"] <= validation_end)]
    holdout = rows[rows["time"] > validation_end]
    models = {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced", C=0.3)),
        "hist_gradient": HistGradientBoostingClassifier(max_iter=180, max_leaf_nodes=15, learning_rate=0.05, l2_regularization=2.0, random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=250, max_depth=8, min_samples_leaf=30, class_weight="balanced_subsample", n_jobs=-1, random_state=42),
    }
    candidates = []
    for name, model in models.items():
        model.fit(train[active_features], train["label"])
        train_p = model.predict_proba(train[active_features])[:, 1]
        validation_p = model.predict_proba(validation[active_features])[:, 1]
        for threshold in np.arange(0.55, 0.91, 0.02):
            train_metrics = _selection_metrics(train, train_p, float(threshold))
            validation_metrics = _selection_metrics(validation, validation_p, float(threshold))
            if train_metrics["trades"] < 100 or validation_metrics["trades"] < 30:
                continue
            qualifies = (
                train_metrics["expectancy"] > 0
                and train_metrics["profit_factor"] > 1.0
                and validation_metrics["win_rate"] >= 0.59
                and validation_metrics["expectancy"] >= 0.03
                and validation_metrics["profit_factor"] >= 1.15
            )
            score = min(train_metrics["expectancy"], validation_metrics["expectancy"])
            candidates.append({
                "model": name, "threshold": round(float(threshold), 4),
                "train": train_metrics, "validation": validation_metrics,
                "qualifies": qualifies, "score": round(score, 6),
            })
    candidates.sort(key=lambda item: (item["qualifies"], item["score"], item["validation"]["trades"]), reverse=True)
    qualifying = [item for item in candidates if item["qualifies"]]
    result: dict[str, Any] = {
        "target_usd": 1.50,
        "stop_usd": stop,
        "max_bars": max_bars,
        "intermarket_features": bool(intermarket_folder),
        "macro_features": bool(macro_folder),
        "outcome_timeframe": "M5" if fine_bars_path else "M15",
        "train_end": train_end.isoformat(),
        "validation_end": validation_end.isoformat(),
        "holdout_start": validation_end.isoformat(),
        "holdout_inspected": False,
        "qualifying_candidates": len(qualifying),
        "best_validation_candidates": candidates[:20],
        "approved": False,
    }
    if qualifying:
        winner = qualifying[0]
        model = models[winner["model"]]
        holdout_p = model.predict_proba(holdout[active_features])[:, 1]
        holdout_metrics = _selection_metrics(holdout, holdout_p, winner["threshold"])
        result.update({
            "holdout_inspected": True,
            "selected_candidate": winner,
            "holdout": holdout_metrics,
            "approved": (
                holdout_metrics["trades"] >= 30
                and holdout_metrics["win_rate"] >= 0.59
                and holdout_metrics["expectancy"] >= 0.03
                and holdout_metrics["profit_factor"] >= 1.15
            ),
        })
    return result


def write_ml_report(report: dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
