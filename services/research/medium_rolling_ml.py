from __future__ import annotations

"""Monthly rolling ML evaluation with prior-window threshold calibration."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from services.research.medium_candidate_lab import build_feature_frame
from services.research.medium_ml_challenger import (
    FEATURES, INTERMARKET_FEATURES, MACRO_FEATURES,
    _feature_rows,
    _outcomes,
    _selected_pnls,
    _selection_metrics,
    metrics_from_values,
)


def _rows(
    dataset_folder: str,
    spread: float,
    stop: float,
    max_bars: int,
    intermarket_folder: str | None,
    macro_folder: str | None,
    fine_bars_path: str | None,
) -> pd.DataFrame:
    data = build_feature_frame(
        dataset_folder,
        intermarket_folder=intermarket_folder,
        macro_folder=macro_folder,
    )
    parts = []
    fine_bars = pd.read_csv(fine_bars_path) if fine_bars_path else None
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
    rows = pd.concat(parts, ignore_index=True).dropna(subset=["pnl"])
    rows["time"] = pd.to_datetime(rows["time"], utc=True)
    return rows.sort_values(["time", "direction"]).reset_index(drop=True)


def _evaluate_period(
    rows: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    active_features: list[str],
    *,
    calibration_days: int,
    training_days: int,
) -> tuple[dict[str, Any], list[float]]:
    folds, all_pnls = [], []
    cursor = start
    while cursor < end:
        test_end = min(cursor + pd.Timedelta(days=30), end)
        calibration_start = cursor - pd.Timedelta(days=calibration_days)
        training_start = calibration_start - pd.Timedelta(days=training_days)
        train = rows[(rows["time"] >= training_start) & (rows["time"] < calibration_start)]
        calibration = rows[(rows["time"] >= calibration_start) & (rows["time"] < cursor)]
        test = rows[(rows["time"] >= cursor) & (rows["time"] < test_end)]
        if len(train) < 5000 or len(calibration) < 1000 or len(test) < 500:
            cursor = test_end
            continue
        model = HistGradientBoostingClassifier(
            max_iter=140, max_leaf_nodes=11, learning_rate=0.04,
            l2_regularization=4.0, random_state=42,
        )
        model.fit(train[active_features], train["label"])
        calibration_p = model.predict_proba(calibration[active_features])[:, 1]
        threshold_candidates = []
        for threshold in np.arange(0.55, 0.86, 0.02):
            metrics = _selection_metrics(calibration, calibration_p, float(threshold))
            if metrics["trades"] >= 20:
                threshold_candidates.append((metrics["expectancy"], metrics["profit_factor"], float(threshold), metrics))
        threshold_candidates.sort(reverse=True)
        selected = next(
            (item for item in threshold_candidates if item[3]["win_rate"] >= 0.59 and item[3]["expectancy"] >= 0.03 and item[3]["profit_factor"] >= 1.15),
            None,
        )
        if selected is None:
            folds.append({"start": cursor.isoformat(), "end": test_end.isoformat(), "action": "ABSTAIN", "calibration_candidates": len(threshold_candidates)})
            cursor = test_end
            continue
        threshold = selected[2]
        test_p = model.predict_proba(test[active_features])[:, 1]
        pnls = _selected_pnls(test, test_p, threshold)
        metrics = metrics_from_values(pnls)
        all_pnls.extend(pnls)
        folds.append({
            "start": cursor.isoformat(), "end": test_end.isoformat(),
            "action": "TRADE", "threshold": round(threshold, 4),
            "calibration": selected[3], "test": metrics,
        })
        cursor = test_end
    return {"metrics": metrics_from_values(all_pnls), "folds": folds}, all_pnls


def run_rolling_ml(
    dataset_folder: str,
    *,
    spread: float = 0.30,
    stop: float = 3.0,
    max_bars: int = 32,
    intermarket_folder: str | None = None,
    macro_folder: str | None = None,
    fine_bars_path: str | None = None,
    calibration_days: int = 30,
    training_days: int = 240,
    data_end: str | None = None,
    development_only: bool = False,
) -> dict[str, Any]:
    rows = _rows(
        dataset_folder, spread, stop, max_bars, intermarket_folder,
        macro_folder, fine_bars_path,
    )
    active_features = (
        FEATURES
        + (INTERMARKET_FEATURES if intermarket_folder else [])
        + (MACRO_FEATURES if macro_folder else [])
    )
    if data_end:
        cutoff = pd.Timestamp(data_end)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        rows = rows[rows["time"] < cutoff].copy()
    start, end = rows["time"].min(), rows["time"].max()
    validation_start = start+(end-start)*(0.45 if development_only else 0.60)
    holdout_start = end if development_only else start+(end-start)*0.80
    validation, _ = _evaluate_period(
        rows, validation_start, holdout_start, active_features,
        calibration_days=calibration_days, training_days=training_days,
    )
    vm = validation["metrics"]
    traded_folds = [fold for fold in validation["folds"] if fold.get("action") == "TRADE"]
    positive_folds = sum(float(fold.get("test", {}).get("expectancy", 0.0)) > 0 for fold in traded_folds)
    validation_pass = (
        vm["trades"] >= 30 and vm["win_rate"] >= 0.59
        and vm["expectancy"] >= 0.03 and vm["profit_factor"] >= 1.15
        and len(traded_folds) >= 2 and positive_folds >= len(traded_folds)-1
    )
    report: dict[str, Any] = {
        "target_usd": 1.50, "stop_usd": stop, "max_bars": max_bars,
        "intermarket_features": bool(intermarket_folder),
        "macro_features": bool(macro_folder),
        "outcome_timeframe": "M5" if fine_bars_path else "M15",
        "calibration_days": calibration_days,
        "training_days": training_days,
        "data_end": data_end or "",
        "development_only": development_only,
        "validation_start": validation_start.isoformat(),
        "holdout_start": holdout_start.isoformat(),
        "holdout_inspected": False,
        "validation": validation,
        "validation_pass": validation_pass,
        "approved": False,
    }
    if validation_pass and not development_only:
        holdout, _ = _evaluate_period(
            rows, holdout_start, end, active_features,
            calibration_days=calibration_days, training_days=training_days,
        )
        hm = holdout["metrics"]
        holdout_traded = [fold for fold in holdout["folds"] if fold.get("action") == "TRADE"]
        holdout_positive = sum(float(fold.get("test", {}).get("expectancy", 0.0)) > 0 for fold in holdout_traded)
        report.update({
            "holdout_inspected": True,
            "holdout": holdout,
            "approved": (
                hm["trades"] >= 30 and hm["win_rate"] >= 0.59
                and hm["expectancy"] >= 0.03 and hm["profit_factor"] >= 1.15
                and len(holdout_traded) >= 2 and holdout_positive >= len(holdout_traded)-1
            ),
        })
    return report


def write_rolling_report(report: dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
