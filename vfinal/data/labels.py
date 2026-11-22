from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from ..config import COST_SPREAD_MULTIPLE, HORIZONS_SECONDS, MIN_STOP_USD, MIN_TARGET_USD, SLIPPAGE_USD, STOP_ATR, TARGET_ATR
from ..schema import Label


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def label_one(snapshot: dict[str, Any], future_ticks: pd.DataFrame, horizon_name: str) -> Label:
    direction = str(snapshot.get("direction", "WAIT")).upper()
    if direction not in {"BUY", "SELL"}:
        raise ValueError("A supervised label requires an explicit BUY or SELL direction.")
    seconds = int(HORIZONS_SECONDS[horizon_name])
    start = pd.Timestamp(snapshot["timestamp"])
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = start + pd.Timedelta(seconds=seconds)
    bid0 = float(snapshot.get("bid", 0.0))
    ask0 = float(snapshot.get("ask", 0.0))
    if not np.isfinite([bid0, ask0]).all() or bid0 <= 0 or ask0 < bid0:
        raise ValueError("A label requires a valid executable entry quote")

    ticks = future_ticks.copy()
    if ticks.empty:
        raise ValueError("No future ticks available for label.")
    if "timestamp" in ticks.columns:
        ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], utc=True, errors="coerce")
    elif "time_msc" in ticks.columns:
        ticks["timestamp"] = pd.to_datetime(pd.to_numeric(ticks.time_msc, errors="coerce"), unit="ms", utc=True)
    if not {"timestamp", "bid", "ask"}.issubset(ticks.columns):
        raise ValueError("Future ticks require timestamps and executable bid/ask")
    ticks = ticks.dropna(subset=["timestamp"]).sort_values("timestamp")
    complete_horizon = not ticks.empty and ticks.timestamp.max() >= end
    ticks = ticks[(ticks.timestamp > start) & (ticks.timestamp <= end)]
    if ticks.empty:
        return Label(str(start), str(snapshot.get("symbol", "XAUUSD")), direction, horizon_name, seconds, 0, 0, 0, False, False, True, 0, 0, 0, 0, 0, 0, 0, "NO_FUTURE_DATA")

    quotes = ticks[["bid", "ask"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(quotes.to_numpy()).all() or (quotes.bid <= 0).any() or (quotes.ask < quotes.bid).any():
        raise ValueError("Invalid executable quote in future label path")
    ticks[["bid", "ask"]] = quotes
    spread0 = ask0 - bid0
    entry = ask0 if direction == "BUY" else bid0
    atr = _num(snapshot.get("feature_payload", {}).get("m1_atr"), 0.0)
    target_distance = max(MIN_TARGET_USD, TARGET_ATR * atr, COST_SPREAD_MULTIPLE * spread0 + SLIPPAGE_USD)
    stop_distance = max(MIN_STOP_USD, STOP_ATR * atr, COST_SPREAD_MULTIPLE * spread0 + SLIPPAGE_USD)
    target = entry + target_distance if direction == "BUY" else entry - target_distance
    stop = entry - stop_distance if direction == "BUY" else entry + stop_distance

    target_time = stop_time = None
    pnl_path: list[float] = []
    for _, row in ticks.iterrows():
        bid = _num(row.bid); ask = _num(row.ask)
        executable = bid if direction == "BUY" else ask
        pnl = executable - entry if direction == "BUY" else entry - executable
        pnl_path.append(pnl)
        hit_t = bid >= target if direction == "BUY" else ask <= target
        hit_s = bid <= stop if direction == "BUY" else ask >= stop
        if hit_t and target_time is None:
            target_time = row.timestamp
        if hit_s and stop_time is None:
            stop_time = row.timestamp

    # Use the last tick in the complete horizon for the horizon-PnL metric; do
    # not truncate the path when a barrier is first touched.
    last = ticks.iloc[-1]
    horizon_executable = _num(last.bid if direction == "BUY" else last.ask)
    horizon_pnl = (horizon_executable - entry) if direction == "BUY" else (entry - horizon_executable)

    estimated_cost = spread0 * COST_SPREAD_MULTIPLE + SLIPPAGE_USD
    if target_time is not None and stop_time is not None and target_time == stop_time:
        # Same-timestamp touches are ambiguous at tick resolution. Do not
        # manufacture a winner; exclude the row from supervised training.
        outcome = 0
        barrier_outcome = -1
        exit_price = horizon_executable
        exit_time = last.timestamp
        label_quality = "AMBIGUOUS_BARRIER"
    elif target_time is not None and (stop_time is None or target_time < stop_time):
        outcome = 1
        barrier_outcome = 1
        exit_price = target
        exit_time = target_time
        label_quality = "VALID"
    elif stop_time is not None:
        outcome = 0
        barrier_outcome = 0
        exit_price = stop
        exit_time = stop_time
        label_quality = "VALID"
    else:
        outcome = 0
        barrier_outcome = 0
        exit_price = horizon_executable
        exit_time = last.timestamp
        label_quality = "TIME_BARRIER"

    pnl_if_exit = ((exit_price - entry) if direction == "BUY" else (entry - exit_price)) - estimated_cost
    if not complete_horizon:
        label_quality = "INCOMPLETE_HORIZON"
    elif ((ticks.timestamp.iloc[0] - start).total_seconds() > 5
          or (end - ticks.timestamp.iloc[-1]).total_seconds() > 5
          or ticks.timestamp.diff().dt.total_seconds().max() > 5):
        label_quality = "GAPPED_HORIZON"
    mfe = max(pnl_path) if pnl_path else 0.0
    mae = min(pnl_path) if pnl_path else 0.0
    hold = max(0.0, (exit_time - start).total_seconds())
    return Label(str(start), str(snapshot.get("symbol", "XAUUSD")), direction, horizon_name, seconds,
                 entry, target, stop, target_time is not None, stop_time is not None,
                 target_time is None and stop_time is None, int(outcome), int(barrier_outcome),
                 float(horizon_pnl), float(pnl_if_exit), float(mfe), float(mae), float(hold),
                 float(estimated_cost), label_quality)


def build_labels(snapshots: list[dict[str, Any]], ticks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for snap in snapshots:
        if str(snap.get("direction", "")).upper() not in {"BUY", "SELL"}:
            continue
        for horizon in HORIZONS_SECONDS:
            try:
                rows.append(asdict(label_one(snap, ticks, horizon)))
            except Exception:
                continue
    return pd.DataFrame(rows)
