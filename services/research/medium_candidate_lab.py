from __future__ import annotations

"""Leakage-controlled candidate search for XAUUSD medium-horizon research."""

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _load(folder: Path, timeframe: str) -> pd.DataFrame:
    frame = pd.read_csv(folder / f"XAUUSD_{timeframe}.csv")
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    return frame.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def _indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    close, high, low = out["close"].astype(float), out["high"].astype(float), out["low"].astype(float)
    previous = close.shift()
    tr = pd.concat([(high-low).abs(), (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(14).mean()
    out["ema12"] = close.ewm(span=12, adjust=False).mean()
    out["ema26"] = close.ewm(span=26, adjust=False).mean()
    out["ema50"] = close.ewm(span=50, adjust=False).mean()
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    out["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    plus_dm = high.diff().clip(lower=0).where(high.diff() > -low.diff(), 0.0)
    minus_dm = (-low.diff()).clip(lower=0).where(-low.diff() > high.diff(), 0.0)
    atr_wilder = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr_wilder
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr_wilder
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    out["adx"] = dx.ewm(alpha=1/14, adjust=False).mean()
    out["body_atr"] = (close-out["open"].astype(float)).abs() / out["atr"]
    out["upper_wick_atr"] = (high-np.maximum(close, out["open"].astype(float))) / out["atr"]
    out["lower_wick_atr"] = (np.minimum(close, out["open"].astype(float))-low) / out["atr"]
    return out


def _htf_direction(frame: pd.DataFrame, delay: pd.Timedelta, name: str) -> pd.DataFrame:
    item = _indicators(frame)
    separation = (item["ema12"] - item["ema26"]) / item["atr"]
    item[f"{name}_direction"] = np.where(
        (separation >= 0.04) & (item["ema12"].diff(3) > 0), 1,
        np.where((separation <= -0.04) & (item["ema12"].diff(3) < 0), -1, 0),
    )
    item["available_at"] = item["time"] + delay
    return item[["available_at", f"{name}_direction"]].dropna()


def _attach_intermarket(data: pd.DataFrame, intermarket_folder: str) -> pd.DataFrame:
    folder = Path(intermarket_folder)
    files = {
        "silver": "silver_XAGUSD_H1.csv",
        "eurusd": "eurusd_EURUSD_H1.csv",
        "gbpusd": "gbpusd_GBPUSD_H1.csv",
        "usdjpy": "usdjpy_USDJPY_H1.csv",
        "usdchf": "usdchf_USDCHF_H1.csv",
        "sp500": "sp500_US500_H1.csv",
        "nasdaq": "nasdaq_USTEC_H1.csv",
    }
    merged = data.sort_values("time")
    role_frames: dict[str, pd.DataFrame] = {}
    for role, filename in files.items():
        frame = pd.read_csv(folder / filename)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        close = frame["close"].astype(float)
        features = pd.DataFrame({
            "available_at": frame["time"] + pd.Timedelta(hours=1),
            f"{role}_ret1": close.pct_change(1),
            f"{role}_ret4": close.pct_change(4),
            f"{role}_ret24": close.pct_change(24),
            f"{role}_vol24": close.pct_change().rolling(24).std(),
        }).dropna()
        role_frames[role] = features
        merged = pd.merge_asof(
            merged.sort_values("time"), features.sort_values("available_at"),
            left_on="time", right_on="available_at", direction="backward",
        ).drop(columns="available_at")
    for window in (1, 4, 24):
        merged[f"usd_pressure_ret{window}"] = (
            -merged[f"eurusd_ret{window}"] - merged[f"gbpusd_ret{window}"]
            + merged[f"usdjpy_ret{window}"] + merged[f"usdchf_ret{window}"]
        ) / 4.0
        merged[f"silver_gold_relative_ret{window}"] = (
            merged[f"silver_ret{window}"] - merged["close"].pct_change(window*4)
        )
        merged[f"equity_risk_ret{window}"] = (
            merged[f"sp500_ret{window}"] + merged[f"nasdaq_ret{window}"]
        ) / 2.0
    return merged


def _attach_macro(data: pd.DataFrame, macro_folder: str) -> pd.DataFrame:
    folder = Path(macro_folder)
    series = {"dgs10": "DGS10.csv", "broad_usd": "DTWEXBGS.csv", "vix": "VIXCLS.csv", "fed_funds": "DFF.csv"}
    merged = data.sort_values("time")
    for role, filename in series.items():
        frame = pd.read_csv(folder / filename)
        date_column, value_column = frame.columns[0], frame.columns[-1]
        values = pd.to_numeric(frame[value_column], errors="coerce")
        dates = pd.to_datetime(frame[date_column], utc=True, errors="coerce")
        features = pd.DataFrame({
            "available_at": dates + pd.Timedelta(days=2),
            f"macro_{role}_level": values,
            f"macro_{role}_change1": values.diff(1),
            f"macro_{role}_change5": values.diff(5),
            f"macro_{role}_change20": values.diff(20),
        }).dropna()
        merged = pd.merge_asof(
            merged.sort_values("time"), features.sort_values("available_at"),
            left_on="time", right_on="available_at", direction="backward",
        ).drop(columns="available_at")
    return merged


def build_feature_frame(
    dataset_folder: str,
    *,
    intermarket_folder: str | None = None,
    macro_folder: str | None = None,
) -> pd.DataFrame:
    folder = Path(dataset_folder)
    m15, h1, h4 = (_load(folder, name) for name in ("M15", "H1", "H4"))
    data = _indicators(m15)
    for name, source, delay in (
        ("H1", h1, pd.Timedelta(hours=1)),
        ("H4", h4, pd.Timedelta(hours=4)),
    ):
        data = pd.merge_asof(
            data.sort_values("time"),
            _htf_direction(source, delay, name).sort_values("available_at"),
            left_on="time", right_on="available_at", direction="backward",
        ).drop(columns="available_at")
    for lookback in (8, 12, 20, 32):
        data[f"prior_high_{lookback}"] = data["high"].rolling(lookback).max().shift()
        data[f"prior_low_{lookback}"] = data["low"].rolling(lookback).min().shift()
    data["hour"] = data["time"].dt.hour
    data["next_open"] = data["open"].shift(-1)
    data["entry_time"] = data["time"].shift(-1)
    if intermarket_folder:
        data = _attach_intermarket(data, intermarket_folder)
    if macro_folder:
        data = _attach_macro(data, macro_folder)
    return data.dropna().reset_index(drop=True)


def _signal(data: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    kind = config["kind"]
    close, opened = data["close"], data["open"]
    htf_buy = (data["H1_direction"] == 1) & (data["H4_direction"] == 1)
    htf_sell = (data["H1_direction"] == -1) & (data["H4_direction"] == -1)
    if kind == "BREAKOUT":
        n = config["lookback"]
        buy = htf_buy & (close > data[f"prior_high_{n}"]) & (data["body_atr"] >= config["body"])
        sell = htf_sell & (close < data[f"prior_low_{n}"]) & (data["body_atr"] >= config["body"])
    elif kind == "PULLBACK":
        buy = (
            htf_buy & (data["low"] <= data["ema12"]) & (close > data["ema12"])
            & (close > opened) & (data["rsi"].between(config["rsi_low"], 65))
        )
        sell = (
            htf_sell & (data["high"] >= data["ema12"]) & (close < data["ema12"])
            & (close < opened) & (data["rsi"].between(35, config["rsi_high"]))
        )
    elif kind == "MOMENTUM":
        buy = htf_buy & (data["adx"] >= config["adx"]) & (close > data["ema12"]) & (close > opened)
        sell = htf_sell & (data["adx"] >= config["adx"]) & (close < data["ema12"]) & (close < opened)
    else:  # RANGE_FADE: only when both higher views are neutral
        neutral = (data["H1_direction"] == 0) & (data["H4_direction"] == 0) & (data["adx"] <= config["adx"])
        buy = neutral & (data["rsi"] <= config["rsi_low"]) & (data["lower_wick_atr"] >= config["wick"])
        sell = neutral & (data["rsi"] >= config["rsi_high"]) & (data["upper_wick_atr"] >= config["wick"])
    signal = pd.Series(np.where(buy, 1, np.where(sell, -1, 0)), index=data.index)
    session = config["session"]
    if session == "LONDON_NY":
        signal = signal.where(data["hour"].between(7, 20), 0)
    elif session == "OVERLAP":
        signal = signal.where(data["hour"].between(12, 17), 0)
    return signal


def _simulate(
    data: pd.DataFrame,
    signal: pd.Series,
    *,
    stop: float,
    max_bars: int,
    spread: float,
) -> list[dict[str, Any]]:
    target = 1.50
    trades: list[dict[str, Any]] = []
    next_free = 0
    high = data["high"].to_numpy(dtype=float)
    low = data["low"].to_numpy(dtype=float)
    close = data["close"].to_numpy(dtype=float)
    next_open = data["next_open"].to_numpy(dtype=float)
    times = data["time"].to_numpy()
    entry_times = data["entry_time"].to_numpy()
    signal_values = signal.to_numpy(dtype=np.int8)
    length = len(data)
    for index in np.flatnonzero(signal_values):
        if index < next_free or index + 1 >= len(data):
            continue
        direction = int(signal_values[index])
        entry_mid = next_open[index]
        entry = entry_mid + spread/2 if direction == 1 else entry_mid - spread/2
        final_index = min(index + max_bars, length-1)
        pnl, reason, exit_index = None, "TIME", final_index
        for future in range(index+1, final_index+1):
            if direction == 1:
                hit_target = high[future] >= entry + target + spread/2
                hit_stop = low[future] <= entry - stop + spread/2
            else:
                hit_target = low[future] <= entry - target - spread/2
                hit_stop = high[future] >= entry + stop - spread/2
            if hit_stop:
                pnl, reason, exit_index = -stop, "STOP", future
                break
            if hit_target:
                pnl, reason, exit_index = target, "TARGET", future
                break
        if pnl is None:
            exit_close = close[final_index]
            quote = exit_close-spread/2 if direction == 1 else exit_close+spread/2
            pnl = quote-entry if direction == 1 else entry-quote
        trades.append({
            "entry_time": entry_times[index],
            "exit_time": times[exit_index],
            "direction": direction,
            "pnl": float(pnl),
            "reason": reason,
        })
        next_free = exit_index + 1
    return trades


def _metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = np.array([row["pnl"] for row in trades], dtype=float)
    if not len(values):
        return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0}
    profit, loss = values[values > 0].sum(), -values[values < 0].sum()
    return {
        "trades": int(len(values)),
        "win_rate": round(float((values > 0).mean()), 6),
        "expectancy": round(float(values.mean()), 6),
        "profit_factor": round(float(profit/loss), 6) if loss else 999.0,
        "net_profit": round(float(values.sum()), 4),
    }


def candidate_configs() -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    sessions = ("ALL", "LONDON_NY", "OVERLAP")
    for lookback, body, session in itertools.product((8, 12, 20, 32), (0.25, 0.5, 0.8), sessions):
        configs.append({"kind": "BREAKOUT", "lookback": lookback, "body": body, "session": session})
    for low, high, session in itertools.product((38, 42, 46), (54, 58, 62), sessions):
        configs.append({"kind": "PULLBACK", "rsi_low": low, "rsi_high": high, "session": session})
    for adx, session in itertools.product((18, 22, 26, 30), sessions):
        configs.append({"kind": "MOMENTUM", "adx": adx, "session": session})
    for adx, low, high, wick, session in itertools.product((18, 22), (25, 30), (70, 75), (0.15, 0.3), sessions):
        configs.append({"kind": "RANGE_FADE", "adx": adx, "rsi_low": low, "rsi_high": high, "wick": wick, "session": session})
    return configs


def search_candidates(dataset_folder: str, *, spread: float = 0.30) -> dict[str, Any]:
    data = build_feature_frame(dataset_folder)
    start, end = data["time"].min(), data["time"].max()
    train_end = start + (end-start)*0.60
    validation_end = start + (end-start)*0.80
    train_mask = data["time"] <= train_end
    validation_mask = (data["time"] > train_end) & (data["time"] <= validation_end)
    screened = []
    for config in candidate_configs():
        full_signal = _signal(data, config)
        train = _metrics(_simulate(data.loc[train_mask].reset_index(drop=True), full_signal.loc[train_mask].reset_index(drop=True), stop=1.8, max_bars=16, spread=spread))
        validation = _metrics(_simulate(data.loc[validation_mask].reset_index(drop=True), full_signal.loc[validation_mask].reset_index(drop=True), stop=1.8, max_bars=16, spread=spread))
        if train["trades"] < 80 or validation["trades"] < 25:
            continue
        score = min(train["expectancy"], validation["expectancy"]) + 0.15 * min(train["profit_factor"], validation["profit_factor"])
        screened.append({"config": config, "train": train, "validation": validation, "score": round(score, 6)})
    screened.sort(key=lambda row: row["score"], reverse=True)

    # Tune exits only after entry hypotheses have survived a common-exit
    # comparison. This reduces computation and multiple-testing pressure.
    results = []
    for candidate in screened[:20]:
        config = candidate["config"]
        full_signal = _signal(data, config)
        for stop, max_bars in itertools.product((1.0, 1.25, 1.5, 1.8, 2.25, 3.0), (8, 16, 24, 32)):
            train = _metrics(_simulate(data.loc[train_mask].reset_index(drop=True), full_signal.loc[train_mask].reset_index(drop=True), stop=stop, max_bars=max_bars, spread=spread))
            validation = _metrics(_simulate(data.loc[validation_mask].reset_index(drop=True), full_signal.loc[validation_mask].reset_index(drop=True), stop=stop, max_bars=max_bars, spread=spread))
            score = min(train["expectancy"], validation["expectancy"]) + 0.15 * min(train["profit_factor"], validation["profit_factor"])
            results.append({"config": config, "stop": stop, "max_bars": max_bars, "train": train, "validation": validation, "score": round(score, 6)})
    results.sort(key=lambda row: row["score"], reverse=True)
    qualifying = [
        row for row in results
        if row["validation"]["win_rate"] >= 0.59
        and row["validation"]["expectancy"] >= 0.03
        and row["validation"]["profit_factor"] >= 1.15
        and row["train"]["expectancy"] > 0
        and row["train"]["profit_factor"] > 1.0
    ]
    return {
        "dataset_start": start.isoformat(),
        "dataset_end": end.isoformat(),
        "train_end": train_end.isoformat(),
        "validation_end": validation_end.isoformat(),
        "holdout_start": validation_end.isoformat(),
        "holdout_inspected": False,
        "entry_configs_screened": len(screened),
        "tuned_combinations_tested": len(results),
        "qualifying_candidates": len(qualifying),
        "best_candidates": (qualifying or results)[:20],
    }


def write_search_report(report: dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
