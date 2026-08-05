from __future__ import annotations

"""Closed-candle XAUUSD scalp playbook detection.

The module deliberately separates *market direction* from *entry timing*.
The 20-candle trend and higher-timeframe context decide which side may be
considered; these playbooks decide whether price is at a sensible entry point.
Only completed M1 candles are used so an early tick in a new minute cannot
create a false three-candle pattern.
"""

from typing import Any

import numpy as np
import pandas as pd

_REQUIRED = {"open", "high", "low", "close"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if not np.isfinite(number) else number
    except (TypeError, ValueError):
        return default


def analyze_scalp_playbooks(
    frame: pd.DataFrame,
    *,
    atr: float,
    micro_break_lookback: int = 5,
) -> dict[str, Any]:
    """Return transparent entry-timing diagnostics from closed M1 candles.

    Playbooks:
    - ``TREND_PULLBACK``: a shallow EMA pullback followed by a reclaim.
    - ``BREAKOUT_RETEST``: a closed breakout followed by a level retest.
    - ``RANGE_REJECTION``: a wick rejection at an externally verified zone.
    - ``MICRO_BREAK`` diagnostics: the live M1 candle relative to the latest
      five completed candles. Directional authorization remains in the unified
      quality gate where context, spread and risk are available.

    The range playbook reports candle rejection only; support/resistance and
    regime validation remain in the unified quality gate where those inputs are
    available.
    """

    if frame is None or len(frame) < 24 or not _REQUIRED.issubset(frame.columns):
        return {
            "status": "ERROR",
            "error": "At least 24 valid M1 candles are required.",
            "three_closed_direction": "NEUTRAL",
            "three_closed_pressure_direction": "NEUTRAL",
            "trend_pullback_direction": "NEUTRAL",
            "breakout_retest_direction": "NEUTRAL",
            "range_rejection_direction": "NEUTRAL",
        }

    usable_atr = max(abs(_safe_float(atr)), 1e-9)
    closed = frame.iloc[:-1].copy()
    if len(closed) < 23:
        return {
            "status": "ERROR",
            "error": "At least 23 closed M1 candles are required.",
            "three_closed_direction": "NEUTRAL",
            "three_closed_pressure_direction": "NEUTRAL",
            "trend_pullback_direction": "NEUTRAL",
            "breakout_retest_direction": "NEUTRAL",
            "range_rejection_direction": "NEUTRAL",
        }

    for column in ("open", "high", "low", "close"):
        closed[column] = pd.to_numeric(closed[column], errors="coerce")
    closed = closed.dropna(subset=["open", "high", "low", "close"])
    if len(closed) < 23:
        return {
            "status": "ERROR",
            "error": "Closed M1 candle values are incomplete.",
            "three_closed_direction": "NEUTRAL",
            "three_closed_pressure_direction": "NEUTRAL",
            "trend_pullback_direction": "NEUTRAL",
            "breakout_retest_direction": "NEUTRAL",
            "range_rejection_direction": "NEUTRAL",
        }

    close = closed["close"].astype(float)
    ema5 = close.ewm(span=5, adjust=False).mean()
    ema13 = close.ewm(span=13, adjust=False).mean()

    last3 = closed.tail(3)
    last3_open = last3["open"].to_numpy(dtype=float)
    last3_close = last3["close"].to_numpy(dtype=float)
    last3_bodies = last3_close - last3_open
    bull_count = int(np.sum(last3_bodies > 0.0))
    bear_count = int(np.sum(last3_bodies < 0.0))
    net3_atr = float((last3_close[-1] - last3_open[0]) / usable_atr)
    latest_body_atr = float(last3_bodies[-1] / usable_atr)

    buy3 = bool(
        bull_count >= 2
        and net3_atr >= 0.10
        and latest_body_atr >= 0.04
        and last3_close[-1] > last3_close[0]
    )
    sell3 = bool(
        bear_count >= 2
        and net3_atr <= -0.10
        and latest_body_atr <= -0.04
        and last3_close[-1] < last3_close[0]
    )
    three_closed_direction = "BUY" if buy3 else "SELL" if sell3 else "NEUTRAL"

    # A slightly broader closed-candle pressure signal supports the balanced
    # continuation path. It still requires two of three candles and meaningful
    # net movement, but a small latest pause candle does not erase the move.
    buy_pressure = bool(
        bull_count >= 2
        and net3_atr >= 0.20
        and latest_body_atr >= -0.08
        and last3_close[-1] > last3_open[0]
    )
    sell_pressure = bool(
        bear_count >= 2
        and net3_atr <= -0.20
        and latest_body_atr <= 0.08
        and last3_close[-1] < last3_open[0]
    )
    three_closed_pressure_direction = (
        "BUY" if buy_pressure else "SELL" if sell_pressure else "NEUTRAL"
    )
    pressure_strength = min(
        1.0,
        (
            max(bull_count, bear_count) / 3.0
            + min(abs(net3_atr) / 1.0, 1.0)
        ) / 2.0,
    )

    # The latest row is the developing M1 candle patched from the current MT5
    # tick. It is not used to establish trend or context; it is used only as a
    # precise break trigger against levels from completed candles.
    live = frame.iloc[-1]
    live_open = _safe_float(live.get("open"))
    live_close = _safe_float(live.get("close"))
    live_body_atr = (live_close - live_open) / usable_atr
    micro_base = closed.tail(max(3, int(micro_break_lookback)))
    micro_break_high = float(micro_base["high"].max())
    micro_break_low = float(micro_base["low"].min())

    latest = closed.iloc[-1]
    latest_ema5 = float(ema5.iloc[-1])
    latest_ema13 = float(ema13.iloc[-1])
    prior3 = closed.iloc[-4:-1]
    prior3_ema5 = ema5.iloc[-4:-1]

    buy_pullback_seen = bool(
        ((prior3["low"].to_numpy(dtype=float) - prior3_ema5.to_numpy(dtype=float)) <= 0.18 * usable_atr).any()
        and float(prior3["low"].min()) >= latest_ema13 - 0.45 * usable_atr
    )
    sell_pullback_seen = bool(
        ((prior3_ema5.to_numpy(dtype=float) - prior3["high"].to_numpy(dtype=float)) <= 0.18 * usable_atr).any()
        and float(prior3["high"].max()) <= latest_ema13 + 0.45 * usable_atr
    )
    latest_range = max(float(latest["high"] - latest["low"]), 1e-9)
    latest_body = float(latest["close"] - latest["open"])
    latest_close_location = float((latest["close"] - latest["low"]) / latest_range)

    buy_reclaim = bool(
        buy_pullback_seen
        and latest_body >= 0.06 * usable_atr
        and float(latest["close"]) > latest_ema5
        and latest_ema5 > latest_ema13
        and latest_close_location >= 0.58
        and buy3
    )
    sell_reclaim = bool(
        sell_pullback_seen
        and latest_body <= -0.06 * usable_atr
        and float(latest["close"]) < latest_ema5
        and latest_ema5 < latest_ema13
        and latest_close_location <= 0.42
        and sell3
    )
    trend_pullback_direction = "BUY" if buy_reclaim else "SELL" if sell_reclaim else "NEUTRAL"

    # Breakout base excludes the latest five closed candles. A breakout must be
    # completed first; the most recent closed candle then retests the level.
    base = closed.iloc[-18:-5]
    breakout_window = closed.iloc[-5:-1]
    range_high = float(base["high"].max())
    range_low = float(base["low"].min())
    buy_break_seen = bool((breakout_window["close"] > range_high + 0.05 * usable_atr).any())
    sell_break_seen = bool((breakout_window["close"] < range_low - 0.05 * usable_atr).any())
    buy_retest = bool(
        buy_break_seen
        and float(latest["low"]) <= range_high + 0.18 * usable_atr
        and float(latest["close"]) >= range_high
        and latest_body >= 0.04 * usable_atr
        and latest_close_location >= 0.55
    )
    sell_retest = bool(
        sell_break_seen
        and float(latest["high"]) >= range_low - 0.18 * usable_atr
        and float(latest["close"]) <= range_low
        and latest_body <= -0.04 * usable_atr
        and latest_close_location <= 0.45
    )
    breakout_retest_direction = "BUY" if buy_retest else "SELL" if sell_retest else "NEUTRAL"

    body_abs = abs(latest_body)
    upper_wick = float(latest["high"] - max(latest["open"], latest["close"]))
    lower_wick = float(min(latest["open"], latest["close"]) - latest["low"])
    buy_rejection = bool(
        latest_body > 0.0
        and lower_wick >= max(body_abs * 1.4, 0.10 * usable_atr)
        and latest_close_location >= 0.60
    )
    sell_rejection = bool(
        latest_body < 0.0
        and upper_wick >= max(body_abs * 1.4, 0.10 * usable_atr)
        and latest_close_location <= 0.40
    )
    range_rejection_direction = "BUY" if buy_rejection else "SELL" if sell_rejection else "NEUTRAL"

    return {
        "status": "OK",
        "uses_closed_candles_only": True,
        "three_closed_direction": three_closed_direction,
        "three_closed_pressure_direction": three_closed_pressure_direction,
        "three_closed_pressure_strength": round(pressure_strength, 4),
        "three_closed_bullish_count": bull_count,
        "three_closed_bearish_count": bear_count,
        "three_closed_net_atr": round(net3_atr, 4),
        "latest_closed_body_atr": round(latest_body_atr, 4),
        "micro_break_high": round(micro_break_high, 6),
        "micro_break_low": round(micro_break_low, 6),
        "live_open": round(live_open, 6),
        "live_close": round(live_close, 6),
        "live_body_atr": round(live_body_atr, 4),
        "trend_pullback_direction": trend_pullback_direction,
        "pullback_seen_buy": buy_pullback_seen,
        "pullback_seen_sell": sell_pullback_seen,
        "breakout_retest_direction": breakout_retest_direction,
        "breakout_range_high": round(range_high, 6),
        "breakout_range_low": round(range_low, 6),
        "breakout_seen_buy": buy_break_seen,
        "breakout_seen_sell": sell_break_seen,
        "range_rejection_direction": range_rejection_direction,
        "latest_close_location": round(latest_close_location, 4),
        "latest_ema5": round(latest_ema5, 6),
        "latest_ema13": round(latest_ema13, 6),
    }
