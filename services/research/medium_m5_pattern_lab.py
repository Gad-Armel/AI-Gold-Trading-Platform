from __future__ import annotations

"""Transparent M5-path pattern research with chronological stability gates."""

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.research.medium_candidate_lab import build_feature_frame
from services.research.medium_ml_challenger import _outcomes, metrics_from_values


def _configs() -> list[dict[str, Any]]:
    result = []
    for kind, threshold, session in itertools.product(
        ("IMPULSE_CONTINUE", "IMPULSE_FADE"), (0.5, 0.8, 1.1, 1.5), ("ALL", "LONDON_NY", "OVERLAP")
    ):
        result.append({"kind": kind, "body_atr": threshold, "session": session})
    for lookback, wick, session in itertools.product((8, 12, 20, 32), (0.1, 0.25, 0.4), ("ALL", "LONDON_NY", "OVERLAP")):
        result.append({"kind": "FAILED_BREAKOUT", "lookback": lookback, "wick_atr": wick, "session": session})
    for lookback, body, session in itertools.product((8, 12, 20, 32), (0.3, 0.6, 0.9), ("ALL", "LONDON_NY", "OVERLAP")):
        result.append({"kind": "BREAKOUT_CONTINUE", "lookback": lookback, "body_atr": body, "session": session})
    return result


def _pattern(data: pd.DataFrame, config: dict[str, Any]) -> np.ndarray:
    kind = config["kind"]
    bullish = data["close"] > data["open"]
    bearish = data["close"] < data["open"]
    if kind == "IMPULSE_CONTINUE":
        buy = bullish & (data["body_atr"] >= config["body_atr"])
        sell = bearish & (data["body_atr"] >= config["body_atr"])
    elif kind == "IMPULSE_FADE":
        buy = bearish & (data["body_atr"] >= config["body_atr"])
        sell = bullish & (data["body_atr"] >= config["body_atr"])
    elif kind == "FAILED_BREAKOUT":
        n = config["lookback"]
        buy = (
            (data["low"] < data[f"prior_low_{n}"]) & (data["close"] > data[f"prior_low_{n}"])
            & (data["lower_wick_atr"] >= config["wick_atr"])
        )
        sell = (
            (data["high"] > data[f"prior_high_{n}"]) & (data["close"] < data[f"prior_high_{n}"])
            & (data["upper_wick_atr"] >= config["wick_atr"])
        )
    else:
        n = config["lookback"]
        buy = (data["close"] > data[f"prior_high_{n}"]) & (data["body_atr"] >= config["body_atr"])
        sell = (data["close"] < data[f"prior_low_{n}"]) & (data["body_atr"] >= config["body_atr"])
    signal = np.where(buy, 1, np.where(sell, -1, 0)).astype(np.int8)
    if config["session"] == "LONDON_NY":
        signal = np.where(data["hour"].between(7, 20), signal, 0)
    elif config["session"] == "OVERLAP":
        signal = np.where(data["hour"].between(12, 17), signal, 0)
    return signal


def _select(
    data: pd.DataFrame,
    signal: np.ndarray,
    buy_pnl: np.ndarray,
    buy_exit: np.ndarray,
    sell_pnl: np.ndarray,
    sell_exit: np.ndarray,
    mask: np.ndarray,
) -> list[dict[str, Any]]:
    selected = []
    next_free = -1
    for index in np.flatnonzero((signal != 0) & mask):
        if index < next_free:
            continue
        pnl = buy_pnl[index] if signal[index] == 1 else sell_pnl[index]
        exit_index = buy_exit[index] if signal[index] == 1 else sell_exit[index]
        if not np.isfinite(pnl):
            continue
        selected.append({"time": data.iloc[index]["entry_time"], "pnl": float(pnl)})
        next_free = int(exit_index)+1
    return selected


def _stable_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = metrics_from_values([item["pnl"] for item in trades])
    folds = []
    if trades:
        frame = pd.DataFrame(trades)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        for month, group in frame.groupby(frame["time"].dt.tz_localize(None).dt.to_period("M")):
            item = metrics_from_values(group["pnl"].astype(float).tolist())
            item["month"] = str(month)
            folds.append(item)
    positive = sum(item["expectancy"] > 0 for item in folds)
    metrics.update({"folds": folds, "positive_folds": positive, "negative_folds": len(folds)-positive})
    return metrics


def search_m5_patterns(
    dataset_folder: str,
    fine_bars_path: str,
    *,
    spread: float = 0.26,
    data_end: str = "2026-04-09",
) -> dict[str, Any]:
    data = build_feature_frame(dataset_folder)
    fine = pd.read_csv(fine_bars_path)
    cutoff = pd.Timestamp(data_end, tz="UTC")
    development_mask = data["time"] < cutoff
    start = max(data.loc[development_mask, "time"].min(), pd.to_datetime(fine["time"], utc=True).min())
    data = data[(data["time"] >= start) & (data["time"] < cutoff)].reset_index(drop=True)
    end = data["time"].max()
    split = start+(end-start)*0.60
    train_mask = (data["time"] <= split).to_numpy()
    validation_mask = (data["time"] > split).to_numpy()
    results = []
    for stop, max_bars in (
        (0.75, 4), (1.0, 8), (1.25, 8), (1.5, 16),
        (1.8, 16), (2.25, 24), (3.0, 32), (4.0, 32),
    ):
        buy_pnl, buy_exit = _outcomes(data, 1, target=1.50, stop=stop, max_bars=max_bars, spread=spread, fine_bars=fine)
        sell_pnl, sell_exit = _outcomes(data, -1, target=1.50, stop=stop, max_bars=max_bars, spread=spread, fine_bars=fine)
        for config in _configs():
            signal = _pattern(data, config)
            train = _stable_metrics(_select(data, signal, buy_pnl, buy_exit, sell_pnl, sell_exit, train_mask))
            validation = _stable_metrics(_select(data, signal, buy_pnl, buy_exit, sell_pnl, sell_exit, validation_mask))
            if train["trades"] < 80 or validation["trades"] < 30:
                continue
            qualifies = (
                train["expectancy"] > 0 and train["profit_factor"] > 1.0
                and validation["win_rate"] >= 0.59 and validation["expectancy"] >= 0.03
                and validation["profit_factor"] >= 1.15
                and len(validation["folds"]) >= 2
                and validation["negative_folds"] <= 1
            )
            score = min(train["expectancy"], validation["expectancy"])
            results.append({
                "config": config, "stop": stop, "max_bars": max_bars,
                "train": train, "validation": validation,
                "qualifies": qualifies, "score": round(score, 6),
            })
    results.sort(key=lambda item: (item["qualifies"], item["score"], item["validation"]["trades"]), reverse=True)
    qualifying = [item for item in results if item["qualifies"]]
    return {
        "development_start": start.isoformat(), "train_end": split.isoformat(),
        "development_end": end.isoformat(), "final_m1_period_reserved_from": data_end,
        "holdout_inspected": False, "candidates_evaluated": len(results),
        "qualifying_candidates": len(qualifying),
        "best_candidates": (qualifying or results)[:20],
    }


def write_pattern_report(report: dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
