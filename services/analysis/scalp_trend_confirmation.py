from __future__ import annotations

"""M1 trend/confirmation analysis for paced XAUUSD paper scalping.

The entry trend uses only the latest 20 *closed* M1 candles.  The fast
confirmation uses the latest three M1 candles (two closed plus the current live
candle) so the bot can react inside the current minute without treating one
noisy tick as a complete trend change.
"""

from typing import Any

import numpy as np
import pandas as pd

from config import scalping_settings

_REQUIRED = {"open", "high", "low", "close"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if not np.isfinite(number) else number
    except (TypeError, ValueError):
        return default


def _direction(value: float, positive_threshold: float, negative_threshold: float) -> str:
    if value >= positive_threshold:
        return "BUY"
    if value <= -negative_threshold:
        return "SELL"
    return "NEUTRAL"


def analyze_m1_trend_confirmation(
    frame: pd.DataFrame,
    *,
    atr: float,
) -> dict[str, Any]:
    """Return the 20-candle trend and 3-candle entry confirmation.

    The calculation deliberately avoids future data:
    - trend: frame rows ending at ``-2`` (last completed candle)
    - confirmation: rows ``-3:`` (two completed candles plus current live M1)
    """

    lookback = max(8, int(scalping_settings.SCALPING_TREND_LOOKBACK_CANDLES))
    confirmation_count = max(
        2, int(scalping_settings.SCALPING_CONFIRMATION_CANDLES)
    )
    minimum_rows = lookback + 1
    if frame is None or len(frame) < minimum_rows or not _REQUIRED.issubset(frame.columns):
        return {
            "status": "ERROR",
            "error": f"At least {minimum_rows} valid M1 candles are required.",
            "trend_direction": "NEUTRAL",
            "confirmation_direction": "NEUTRAL",
            "entry_direction": "NEUTRAL",
            "trend_confirmed": False,
        }

    usable_atr = max(abs(_safe_float(atr)), 1e-9)
    closed = frame.iloc[:-1]
    trend_frame = closed.tail(lookback)
    closes = trend_frame["close"].astype(float).to_numpy()
    opens = trend_frame["open"].astype(float).to_numpy()
    x = np.arange(len(closes), dtype=float)
    slope = float(np.polyfit(x, closes, 1)[0]) if len(closes) > 1 else 0.0
    net_move = float(closes[-1] - closes[0])
    path = float(np.abs(np.diff(closes)).sum())
    efficiency = abs(net_move) / path if path > 1e-9 else 0.0
    net_move_atr = net_move / usable_atr
    slope_span_atr = slope * max(1, len(closes) - 1) / usable_atr
    ema_fast = float(pd.Series(closes).ewm(span=5, adjust=False).mean().iloc[-1])
    ema_slow = float(pd.Series(closes).ewm(span=13, adjust=False).mean().iloc[-1])
    bullish_candles = int(np.sum(closes > opens))
    bearish_candles = int(np.sum(closes < opens))

    minimum_net = float(scalping_settings.SCALPING_TREND_MIN_NET_MOVE_ATR)
    minimum_slope = float(scalping_settings.SCALPING_TREND_MIN_SLOPE_SPAN_ATR)
    minimum_efficiency = float(scalping_settings.SCALPING_TREND_MIN_EFFICIENCY)

    bullish_trend = bool(
        net_move_atr >= minimum_net
        and slope_span_atr >= minimum_slope
        and ema_fast > ema_slow
        and efficiency >= minimum_efficiency
    )
    bearish_trend = bool(
        net_move_atr <= -minimum_net
        and slope_span_atr <= -minimum_slope
        and ema_fast < ema_slow
        and efficiency >= minimum_efficiency
    )
    trend_direction = "BUY" if bullish_trend else "SELL" if bearish_trend else "NEUTRAL"

    trend_strength = min(
        1.0,
        (
            min(abs(net_move_atr) / max(minimum_net * 3.0, 1e-9), 1.0)
            + min(abs(slope_span_atr) / max(minimum_slope * 3.0, 1e-9), 1.0)
            + min(efficiency / max(minimum_efficiency * 2.5, 1e-9), 1.0)
            + (1.0 if trend_direction != "NEUTRAL" else 0.0)
        )
        / 4.0,
    )

    confirm_frame = frame.tail(confirmation_count)
    confirm_open = confirm_frame["open"].astype(float).to_numpy()
    confirm_close = confirm_frame["close"].astype(float).to_numpy()
    bodies = confirm_close - confirm_open
    bullish_confirmations = int(np.sum(bodies > 0.0))
    bearish_confirmations = int(np.sum(bodies < 0.0))
    required_confirmations = max(
        2, int(scalping_settings.SCALPING_CONFIRMATION_MIN_DIRECTIONAL_CANDLES)
    )
    confirmation_net_move = float(confirm_close[-1] - confirm_open[0])
    confirmation_net_atr = confirmation_net_move / usable_atr
    minimum_confirmation_move = float(
        scalping_settings.SCALPING_CONFIRMATION_MIN_NET_MOVE_ATR
    )
    latest_body_atr = float(bodies[-1] / usable_atr)
    maximum_opposing_body = float(
        scalping_settings.SCALPING_CONFIRMATION_MAX_OPPOSING_BODY_ATR
    )

    bullish_confirmation = bool(
        bullish_confirmations >= required_confirmations
        and confirmation_net_atr >= minimum_confirmation_move
        and latest_body_atr >= -maximum_opposing_body
        and confirm_close[-1] >= confirm_close[0]
    )
    bearish_confirmation = bool(
        bearish_confirmations >= required_confirmations
        and confirmation_net_atr <= -minimum_confirmation_move
        and latest_body_atr <= maximum_opposing_body
        and confirm_close[-1] <= confirm_close[0]
    )
    confirmation_direction = (
        "BUY" if bullish_confirmation else "SELL" if bearish_confirmation else "NEUTRAL"
    )
    confirmation_strength = min(
        1.0,
        (
            max(bullish_confirmations, bearish_confirmations) / confirmation_count
            + min(
                abs(confirmation_net_atr)
                / max(minimum_confirmation_move * 5.0, 1e-9),
                1.0,
            )
        )
        / 2.0,
    )

    entry_direction = (
        trend_direction
        if trend_direction in {"BUY", "SELL"}
        and trend_direction == confirmation_direction
        else "NEUTRAL"
    )

    return {
        "status": "OK",
        "lookback_candles": lookback,
        "confirmation_candles": confirmation_count,
        "trend_direction": trend_direction,
        "trend_confirmed": entry_direction in {"BUY", "SELL"},
        "confirmation_direction": confirmation_direction,
        "entry_direction": entry_direction,
        "trend_strength": round(trend_strength, 4),
        "confirmation_strength": round(confirmation_strength, 4),
        "net_move": round(net_move, 6),
        "net_move_atr": round(net_move_atr, 4),
        "slope_per_candle": round(slope, 8),
        "slope_span_atr": round(slope_span_atr, 4),
        "efficiency_ratio": round(efficiency, 4),
        "ema_fast": round(ema_fast, 6),
        "ema_slow": round(ema_slow, 6),
        "bullish_trend_candles": bullish_candles,
        "bearish_trend_candles": bearish_candles,
        "bullish_confirmation_candles": bullish_confirmations,
        "bearish_confirmation_candles": bearish_confirmations,
        "required_confirmation_candles": required_confirmations,
        "confirmation_net_move_atr": round(confirmation_net_atr, 4),
        "latest_body_atr": round(latest_body_atr, 4),
        "three_of_three": max(bullish_confirmations, bearish_confirmations)
        == confirmation_count,
    }
