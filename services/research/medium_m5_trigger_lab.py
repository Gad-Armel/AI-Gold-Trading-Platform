from __future__ import annotations

"""M5 entry-clock research with a reserved M1 chronological confirmation."""

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.research.medium_candidate_lab import _indicators, _htf_direction
from services.research.medium_ml_challenger import _outcomes, metrics_from_values


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    return frame.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def build_m5_features(dataset_folder: str) -> pd.DataFrame:
    folder = Path(dataset_folder)
    m5 = _indicators(_load(folder / "XAUUSD_M5.csv"))
    h1, h4 = _load(folder / "XAUUSD_H1.csv"), _load(folder / "XAUUSD_H4.csv")
    data = m5
    for name, source, delay in (
        ("H1", h1, pd.Timedelta(hours=1)),
        ("H4", h4, pd.Timedelta(hours=4)),
    ):
        data = pd.merge_asof(
            data.sort_values("time"),
            _htf_direction(source, delay, name).sort_values("available_at"),
            left_on="time", right_on="available_at", direction="backward",
        ).drop(columns="available_at")
    for lookback in (6, 12, 24, 48):
        data[f"prior_high_{lookback}"] = data["high"].rolling(lookback).max().shift()
        data[f"prior_low_{lookback}"] = data["low"].rolling(lookback).min().shift()
    typical = (data["high"]+data["low"]+data["close"])/3
    volume = data["tick_volume"].clip(lower=1)
    day = data["time"].dt.floor("D")
    data["day_vwap"] = (typical*volume).groupby(day).cumsum()/volume.groupby(day).cumsum()
    data["previous_close"] = data["close"].shift()
    data["previous_open"] = data["open"].shift()
    data["previous_high"] = data["high"].shift()
    data["previous_low"] = data["low"].shift()
    data["previous_rsi"] = data["rsi"].shift()
    data["hour"] = data["time"].dt.hour
    data["next_open"] = data["open"].shift(-1)
    data["entry_time"] = data["time"].shift(-1)
    return data.dropna().reset_index(drop=True)


def _configs() -> list[dict[str, Any]]:
    configs = []
    sessions = ("ALL", "LONDON_NY", "OVERLAP")
    for kind, threshold, session in itertools.product(
        ("PULLBACK_RECLAIM", "TWO_BAR_REVERSAL"), (0.15, 0.3, 0.5), sessions
    ):
        configs.append({"kind": kind, "threshold": threshold, "session": session})
    for lookback, wick, context, session in itertools.product(
        (6, 12, 24, 48), (0.15, 0.3, 0.5), ("TREND", "NON_OPPOSED", "ANY"), sessions
    ):
        configs.append({"kind": "LIQUIDITY_SWEEP", "lookback": lookback, "wick": wick, "context": context, "session": session})
    for lookback, body, context, session in itertools.product(
        (6, 12, 24, 48), (0.2, 0.4, 0.7), ("TREND", "NON_OPPOSED"), sessions
    ):
        configs.append({"kind": "BREAKOUT", "lookback": lookback, "body": body, "context": context, "session": session})
    for rsi, context, session in itertools.product((25, 30, 35), ("TREND", "ANY"), sessions):
        configs.append({"kind": "RSI_CROSS", "rsi": rsi, "context": context, "session": session})
    return configs


def _context(data: pd.DataFrame, direction: int, mode: str) -> pd.Series:
    h1, h4 = data["H1_direction"], data["H4_direction"]
    if mode == "TREND":
        return (h1 == direction) & (h4 == direction)
    if mode == "NON_OPPOSED":
        return (h1 == direction) & (h4 != -direction)
    return pd.Series(True, index=data.index)


def _signal(data: pd.DataFrame, config: dict[str, Any]) -> np.ndarray:
    kind = config["kind"]
    bullish = data["close"] > data["open"]
    bearish = data["close"] < data["open"]
    if kind == "PULLBACK_RECLAIM":
        buy = _context(data, 1, "TREND") & (data["low"] <= data["ema12"]) & (data["close"] > data["ema12"]) & bullish & (data["body_atr"] >= config["threshold"])
        sell = _context(data, -1, "TREND") & (data["high"] >= data["ema12"]) & (data["close"] < data["ema12"]) & bearish & (data["body_atr"] >= config["threshold"])
    elif kind == "TWO_BAR_REVERSAL":
        buy = _context(data, 1, "NON_OPPOSED") & (data["previous_close"] < data["previous_open"]) & bullish & (data["close"] > data["previous_high"]) & (data["body_atr"] >= config["threshold"])
        sell = _context(data, -1, "NON_OPPOSED") & (data["previous_close"] > data["previous_open"]) & bearish & (data["close"] < data["previous_low"]) & (data["body_atr"] >= config["threshold"])
    elif kind == "LIQUIDITY_SWEEP":
        n = config["lookback"]
        buy = _context(data, 1, config["context"]) & (data["low"] < data[f"prior_low_{n}"]) & (data["close"] > data[f"prior_low_{n}"]) & (data["lower_wick_atr"] >= config["wick"])
        sell = _context(data, -1, config["context"]) & (data["high"] > data[f"prior_high_{n}"]) & (data["close"] < data[f"prior_high_{n}"]) & (data["upper_wick_atr"] >= config["wick"])
    elif kind == "BREAKOUT":
        n = config["lookback"]
        buy = _context(data, 1, config["context"]) & (data["close"] > data[f"prior_high_{n}"]) & (data["body_atr"] >= config["body"])
        sell = _context(data, -1, config["context"]) & (data["close"] < data[f"prior_low_{n}"]) & (data["body_atr"] >= config["body"])
    else:
        level = config["rsi"]
        buy = _context(data, 1, config["context"]) & (data["previous_rsi"] <= level) & (data["rsi"] > level)
        sell_level = 100-level
        sell = _context(data, -1, config["context"]) & (data["previous_rsi"] >= sell_level) & (data["rsi"] < sell_level)
    signal = np.where(buy, 1, np.where(sell, -1, 0)).astype(np.int8)
    if config["session"] == "LONDON_NY":
        signal = np.where(data["hour"].between(7, 20), signal, 0)
    elif config["session"] == "OVERLAP":
        signal = np.where(data["hour"].between(12, 17), signal, 0)
    return signal


def _fast_outcomes(data: pd.DataFrame, direction: int, target: float, stop: float, max_bars: int, spread: float) -> tuple[np.ndarray, np.ndarray]:
    length = len(data)
    entry_mid = data["next_open"].to_numpy(float)
    entry = entry_mid+spread/2 if direction == 1 else entry_mid-spread/2
    high, low, close = data["high"].to_numpy(float), data["low"].to_numpy(float), data["close"].to_numpy(float)
    pnl = np.full(length, np.nan)
    exits = np.arange(length)
    unresolved = np.ones(length, dtype=bool)
    for offset in range(1, max_bars+1):
        valid = np.arange(length)+offset < length
        future_high = np.full(length, np.nan)
        future_low = np.full(length, np.nan)
        future_high[valid] = high[offset:]
        future_low[valid] = low[offset:]
        if direction == 1:
            hit_stop = valid & unresolved & (future_low <= entry-stop+spread/2)
            hit_target = valid & unresolved & ~hit_stop & (future_high >= entry+target+spread/2)
        else:
            hit_stop = valid & unresolved & (future_high >= entry+stop-spread/2)
            hit_target = valid & unresolved & ~hit_stop & (future_low <= entry-target-spread/2)
        pnl[hit_stop], exits[hit_stop], unresolved[hit_stop] = -stop, np.flatnonzero(hit_stop)+offset, False
        pnl[hit_target], exits[hit_target], unresolved[hit_target] = target, np.flatnonzero(hit_target)+offset, False
    valid_time = unresolved & (np.arange(length)+max_bars < length)
    future_close = np.full(length, np.nan)
    future_close[:length-max_bars] = close[max_bars:]
    quote = future_close-spread/2 if direction == 1 else future_close+spread/2
    pnl[valid_time] = quote[valid_time]-entry[valid_time] if direction == 1 else entry[valid_time]-quote[valid_time]
    exits[valid_time] = np.flatnonzero(valid_time)+max_bars
    return pnl, exits


def _select(months: np.ndarray, signal: np.ndarray, buy: tuple[np.ndarray, np.ndarray], sell: tuple[np.ndarray, np.ndarray], mask: np.ndarray) -> list[tuple[str, float]]:
    values = []
    next_free = -1
    for index in np.flatnonzero((signal != 0) & mask):
        if index < next_free:
            continue
        pnl, exit_index = (buy[0][index], buy[1][index]) if signal[index] == 1 else (sell[0][index], sell[1][index])
        if not np.isfinite(pnl):
            continue
        values.append((str(months[index]), float(pnl)))
        next_free = int(exit_index)+1
    return values


def _metrics(trades: list[tuple[str, float]]) -> dict[str, Any]:
    result = metrics_from_values([item[1] for item in trades])
    folds = []
    if trades:
        by_month: dict[str, list[float]] = {}
        for month, pnl in trades:
            by_month.setdefault(month, []).append(pnl)
        for month, values in sorted(by_month.items()):
            item = metrics_from_values(values)
            item["month"] = month
            folds.append(item)
    result["folds"] = folds
    result["negative_folds"] = sum(item["expectancy"] <= 0 for item in folds)
    return result


def search_m5_triggers(
    dataset_folder: str,
    *,
    development_end: str = "2026-04-09",
    spread: float = 0.26,
) -> dict[str, Any]:
    data = build_m5_features(dataset_folder)
    cutoff = pd.Timestamp(development_end, tz="UTC")
    data = data[data["time"] < cutoff].reset_index(drop=True)
    start, end = data["time"].min(), data["time"].max()
    split = start+(end-start)*0.60
    train_mask = (data["time"] <= split).to_numpy()
    validation_mask = (data["time"] > split).to_numpy()
    months = pd.to_datetime(data["entry_time"], utc=True).dt.strftime("%Y-%m").to_numpy()
    results = []
    for stop, max_bars in ((0.75, 12), (1.0, 24), (1.25, 24), (1.5, 36), (1.8, 36), (2.25, 48), (3.0, 48)):
        buy = _fast_outcomes(data, 1, 1.50, stop, max_bars, spread)
        sell = _fast_outcomes(data, -1, 1.50, stop, max_bars, spread)
        for config in _configs():
            signal = _signal(data, config)
            train = _metrics(_select(months, signal, buy, sell, train_mask))
            validation = _metrics(_select(months, signal, buy, sell, validation_mask))
            if train["trades"] < 100 or validation["trades"] < 40:
                continue
            qualifies = (
                train["expectancy"] > 0 and train["profit_factor"] > 1.0
                and validation["win_rate"] >= 0.59
                and validation["expectancy"] >= 0.03
                and validation["profit_factor"] >= 1.15
                and len(validation["folds"]) >= 3
                and validation["negative_folds"] <= 1
            )
            results.append({
                "config": config, "stop": stop, "max_bars": max_bars,
                "train": train, "validation": validation, "qualifies": qualifies,
                "score": round(min(train["expectancy"], validation["expectancy"]), 6),
            })
    results.sort(key=lambda item: (item["qualifies"], item["score"], item["validation"]["trades"]), reverse=True)
    qualifying = [item for item in results if item["qualifies"]]
    return {
        "development_start": start.isoformat(), "train_end": split.isoformat(),
        "development_end": end.isoformat(), "m1_confirmation_reserved_from": development_end,
        "m1_confirmation_inspected": False, "candidates_evaluated": len(results),
        "qualifying_candidates": len(qualifying), "best_candidates": (qualifying or results)[:25],
    }


def write_m5_trigger_report(report: dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
