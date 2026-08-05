from __future__ import annotations

"""Atome-inspired indicator families used inside the one V3.4 decision.

This module is not a second AI.  It creates directional technical features for
``unified_scalping_intelligence``.  In V3.0 it accidentally checked the obsolete
shadow-intelligence switch, so it always returned DISABLED.  V3.4 checks the
unified factor flag directly and exposes explicit data-quality diagnostics.
"""

from typing import Any

import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState

_REQUIRED_COLUMNS = {"time", "open", "high", "low", "close"}
_FACTOR_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return default if pd.isna(result) else result
    except (TypeError, ValueError):
        return default


def _prepare(data: Any, timeframe: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    if data is None:
        raise ValueError(f"{timeframe} candles are missing.")
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    received = len(frame)
    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"{timeframe} candles are missing columns: {sorted(missing)}")
    for column in ["open", "high", "low", "close", "tick_volume"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)

    # MT5's last row is normally the unfinished candle.  Technical context and
    # crosses must be based on closed candles so their values cannot repaint.
    closed = frame.iloc[:-1].copy() if len(frame) > 1 else frame.iloc[0:0].copy()
    required_total = max(55, int(scalping_settings.SCALPING_MIN_REQUIRED_CANDLES))
    required_closed = required_total - 1
    if len(frame) < required_total or len(closed) < required_closed:
        raise ValueError(
            f"{timeframe} has {len(frame)} total/{len(closed)} closed valid candles; "
            f"{required_total} total ({required_closed} closed) required."
        )
    diagnostic = {
        "timeframe": timeframe,
        "bars_received": received,
        "valid_bars": len(frame),
        "closed_bars_used": len(closed),
        "minimum_required": required_total,
        "minimum_closed_required": required_closed,
        "last_closed_time": str(closed.iloc[-1]["time"]),
        "valid": True,
    }
    return closed, diagnostic


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    average_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    average_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = average_gain / average_loss.replace(0.0, float("nan"))
    result = 100.0 - (100.0 / (1.0 + rs))
    result = result.fillna(50.0)
    result = result.where(average_loss != 0.0, 100.0)
    return result.where((average_gain != 0.0) | (average_loss != 0.0), 50.0)


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1).ewm(alpha=1.0 / period, adjust=False).mean()


def _stochastic(frame: pd.DataFrame, period: int = 14, smooth: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest = frame["low"].rolling(period).min()
    highest = frame["high"].rolling(period).max()
    denominator = (highest - lowest).replace(0.0, float("nan"))
    raw_k = 100.0 * (frame["close"] - lowest) / denominator
    k = raw_k.rolling(smooth).mean().fillna(50.0)
    d = k.rolling(smooth).mean().fillna(50.0)
    return k, d


def _indicators(frame: pd.DataFrame) -> dict[str, Any]:
    working = frame.copy()
    close = working["close"]
    working["ema8"] = close.ewm(span=8, adjust=False).mean()
    working["ema21"] = close.ewm(span=21, adjust=False).mean()
    working["ema50"] = close.ewm(span=50, adjust=False).mean()
    working["rsi14"] = _rsi(close, 14)
    working["rsi7"] = _rsi(close, 7)

    middle = close.rolling(20).mean()
    deviation = close.rolling(20).std(ddof=0)
    working["bb_upper"] = middle + 2.0 * deviation
    working["bb_lower"] = middle - 2.0 * deviation
    working["bb_width"] = working["bb_upper"] - working["bb_lower"]
    working["bb_width_average"] = working["bb_width"].rolling(50, min_periods=20).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    working["macd"] = ema12 - ema26
    working["macd_signal"] = working["macd"].ewm(span=9, adjust=False).mean()
    working["stoch_k"], working["stoch_d"] = _stochastic(working)
    working["atr14"] = _atr(working, 14)

    latest = working.iloc[-1]
    previous = working.iloc[-2]
    recent = working.iloc[-3:]
    band_width = _safe_float(latest["bb_upper"] - latest["bb_lower"])
    previous_band_width = _safe_float(previous["bb_width"])
    previous_average_width = _safe_float(previous["bb_width_average"])
    previous_width_ratio = (
        previous_band_width / previous_average_width
        if previous_average_width > 0
        else 1.0
    )
    band_position = (
        (_safe_float(latest["close"]) - _safe_float(latest["bb_lower"])) / band_width
        if band_width > 0
        else 0.5
    )
    body = _safe_float(latest["close"] - latest["open"])
    body_abs = abs(body)
    lower_wick = max(0.0, min(_safe_float(latest["open"]), _safe_float(latest["close"])) - _safe_float(latest["low"]))
    upper_wick = max(0.0, _safe_float(latest["high"]) - max(_safe_float(latest["open"]), _safe_float(latest["close"])))
    atr_value = _safe_float(latest["atr14"])
    atr_lookback = max(20, int(scalping_settings.SCALPING_UNIFIED_FACTOR_ATR_LOOKBACK))
    atr_average = _safe_float(working["atr14"].tail(atr_lookback).mean())
    atr_ratio = atr_value / atr_average if atr_average > 0 else 1.0
    previous_body = _safe_float(previous["close"] - previous["open"])
    bullish_engulfing = bool(
        body > 0.0
        and previous_body < 0.0
        and _safe_float(latest["open"]) <= _safe_float(previous["close"])
        and _safe_float(latest["close"]) >= _safe_float(previous["open"])
    )
    bearish_engulfing = bool(
        body < 0.0
        and previous_body > 0.0
        and _safe_float(latest["open"]) >= _safe_float(previous["close"])
        and _safe_float(latest["close"]) <= _safe_float(previous["open"])
    )
    # A squeeze is evidence only after a closed candle expands through the
    # previous band.  This avoids treating quiet compression as a breakout and
    # avoids using MT5's still-forming final candle.
    squeeze_ready = previous_width_ratio <= 0.80
    band_expanding = band_width > previous_band_width * 1.05
    bullish_band_expansion = bool(
        squeeze_ready
        and band_expanding
        and _safe_float(latest["close"]) > _safe_float(previous["bb_upper"])
    )
    bearish_band_expansion = bool(
        squeeze_ready
        and band_expanding
        and _safe_float(latest["close"]) < _safe_float(previous["bb_lower"])
    )

    return {
        "close": _safe_float(latest["close"]),
        "ema8": _safe_float(latest["ema8"]),
        "ema21": _safe_float(latest["ema21"]),
        "ema50": _safe_float(latest["ema50"]),
        "rsi14": _safe_float(latest["rsi14"], 50.0),
        "rsi7": _safe_float(latest["rsi7"], 50.0),
        "previous_rsi14": _safe_float(previous["rsi14"], 50.0),
        "previous_rsi7": _safe_float(previous["rsi7"], 50.0),
        "bb_position": max(0.0, min(1.0, band_position)),
        "bb_width_ratio": round(previous_width_ratio, 6),
        "bullish_band_expansion": bullish_band_expansion,
        "bearish_band_expansion": bearish_band_expansion,
        "macd": _safe_float(latest["macd"]),
        "macd_signal": _safe_float(latest["macd_signal"]),
        "previous_macd": _safe_float(previous["macd"]),
        "previous_macd_signal": _safe_float(previous["macd_signal"]),
        "stoch_k": _safe_float(latest["stoch_k"], 50.0),
        "stoch_d": _safe_float(latest["stoch_d"], 50.0),
        "previous_stoch_k": _safe_float(previous["stoch_k"], 50.0),
        "previous_stoch_d": _safe_float(previous["stoch_d"], 50.0),
        "atr": atr_value,
        "atr_ratio": atr_ratio,
        "hammer": body_abs > 0 and lower_wick >= body_abs * 2.0 and upper_wick <= body_abs * 1.25,
        "shooting_star": body_abs > 0 and upper_wick >= body_abs * 2.0 and lower_wick <= body_abs * 1.25,
        "bullish_engulfing": bullish_engulfing,
        "bearish_engulfing": bearish_engulfing,
        "three_bullish": bool((recent["close"] > recent["open"]).all()),
        "three_bearish": bool((recent["close"] < recent["open"]).all()),
    }


def _volatility_adjustment(atr_ratio: float) -> tuple[float, str]:
    if atr_ratio < 0.50:
        return 0.70, "TOO_CALM"
    if 0.80 <= atr_ratio <= 1.50:
        return 1.10, "OPTIMAL"
    if atr_ratio > 2.00:
        return 0.60, "EXTREME"
    return 1.00, "ACCEPTABLE"


def _direction_score(direction: str, m1: dict[str, Any], m5: dict[str, Any], m15: dict[str, Any]) -> dict[str, Any]:
    is_buy = direction == "BUY"
    components = {"ema": 0.0, "rsi": 0.0, "bollinger": 0.0, "macd": 0.0, "stochastic": 0.0, "price_action": 0.0}
    reasons: list[str] = []

    m1_ema_aligned = m1["ema8"] > m1["ema21"] > m1["ema50"] if is_buy else m1["ema8"] < m1["ema21"] < m1["ema50"]
    m5_ema_aligned = m5["ema8"] > m5["ema21"] > m5["ema50"] if is_buy else m5["ema8"] < m5["ema21"] < m5["ema50"]
    m15_context = m15["ema8"] > m15["ema21"] if is_buy else m15["ema8"] < m15["ema21"]
    if m1_ema_aligned:
        components["ema"] += 15.0
        reasons.append("M1 EMA 8/21/50 alignment")
    if m5_ema_aligned:
        components["ema"] += 10.0
        reasons.append("M5 EMA 8/21/50 confirmation")
    if m15_context:
        reasons.append("M15 EMA context alignment")

    if is_buy:
        fast_cross = m1["previous_rsi7"] <= m1["previous_rsi14"] and m1["rsi7"] > m1["rsi14"]
        if m1["rsi14"] < 35.0 and fast_cross:
            components["rsi"] += 15.0
        elif m1["rsi14"] < 45.0 and m1["rsi7"] > 50.0:
            components["rsi"] += 8.0
        if m5["rsi14"] < 40.0:
            components["rsi"] += 5.0
        components["bollinger"] = 15.0 if m1["bullish_band_expansion"] else 15.0 if m1["bb_position"] <= 0.15 else 8.0 if m1["bb_position"] <= 0.30 else 0.0
        macd_cross = m1["previous_macd"] <= m1["previous_macd_signal"] and m1["macd"] > m1["macd_signal"]
        components["macd"] = 15.0 if macd_cross else 7.0 if m1["macd"] > m1["macd_signal"] else 0.0
        stoch_cross = m1["previous_stoch_k"] <= m1["previous_stoch_d"] and m1["stoch_k"] > m1["stoch_d"]
        components["stochastic"] = 10.0 if m1["stoch_k"] < 20.0 and stoch_cross else 5.0 if m1["stoch_k"] < 30.0 else 0.0
        components["price_action"] = 10.0 if (m1["hammer"] or m1["bullish_engulfing"]) else 5.0 if m1["three_bullish"] else 0.0
    else:
        fast_cross = m1["previous_rsi7"] >= m1["previous_rsi14"] and m1["rsi7"] < m1["rsi14"]
        if m1["rsi14"] > 65.0 and fast_cross:
            components["rsi"] += 15.0
        elif m1["rsi14"] > 55.0 and m1["rsi7"] < 50.0:
            components["rsi"] += 8.0
        if m5["rsi14"] > 60.0:
            components["rsi"] += 5.0
        components["bollinger"] = 15.0 if m1["bearish_band_expansion"] else 15.0 if m1["bb_position"] >= 0.85 else 8.0 if m1["bb_position"] >= 0.70 else 0.0
        macd_cross = m1["previous_macd"] >= m1["previous_macd_signal"] and m1["macd"] < m1["macd_signal"]
        components["macd"] = 15.0 if macd_cross else 7.0 if m1["macd"] < m1["macd_signal"] else 0.0
        stoch_cross = m1["previous_stoch_k"] >= m1["previous_stoch_d"] and m1["stoch_k"] < m1["stoch_d"]
        components["stochastic"] = 10.0 if m1["stoch_k"] > 80.0 and stoch_cross else 5.0 if m1["stoch_k"] > 70.0 else 0.0
        components["price_action"] = 10.0 if (m1["shooting_star"] or m1["bearish_engulfing"]) else 5.0 if m1["three_bearish"] else 0.0

    for name, value in components.items():
        if value > 0 and name != "ema":
            reasons.append(f"{name}={value:.0f}")
    raw_score = min(100.0, sum(components.values()))
    factor_count = sum(value > 0 for value in components.values())
    multiplier, regime = _volatility_adjustment(m1["atr_ratio"])
    adjusted_score = min(100.0, raw_score * multiplier)
    return {
        "direction": direction,
        "raw_score": round(raw_score, 2),
        "adjusted_score": round(adjusted_score, 2),
        "factor_count": factor_count,
        "components": components,
        "reasons": reasons,
        "m1_ema_aligned": m1_ema_aligned,
        "m5_ema_aligned": m5_ema_aligned,
        "m15_context_aligned": m15_context,
        "volatility_multiplier": multiplier,
        "volatility_regime": regime,
    }



def _factor_cache_key(snapshot: ScalpingSnapshotState) -> tuple[Any, ...]:
    values: list[Any] = []
    for timeframe in ("M1", "M5", "M15"):
        data = snapshot.candles.get(timeframe)
        frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        if len(frame) < 2:
            values.extend((timeframe, len(frame), "", 0.0))
            continue
        closed = frame.iloc[-2]
        values.extend(
            (
                timeframe,
                len(frame),
                str(closed.get("time", "")),
                round(_safe_float(closed.get("close", 0.0)), 8),
                round(_safe_float(closed.get("high", 0.0)), 8),
                round(_safe_float(closed.get("low", 0.0)), 8),
            )
        )
    values.extend(
        (
            int(scalping_settings.SCALPING_UNIFIED_FACTOR_ATR_LOOKBACK),
            float(scalping_settings.SCALPING_UNIFIED_FACTOR_MIN_SCORE),
            int(scalping_settings.SCALPING_UNIFIED_FACTOR_MIN_FACTORS),
        )
    )
    return tuple(values)

def build_atome_factor_model(snapshot: ScalpingSnapshotState, primary_signal: ScalpSignalState | None = None) -> dict[str, Any]:
    if not bool(scalping_settings.SCALPING_UNIFIED_ATOME_FACTORS_ENABLED):
        return {
            "enabled": False,
            "status": "DISABLED_BY_UNIFIED_SETTING",
            "error": "SCALPING_UNIFIED_ATOME_FACTORS_ENABLED=False",
        }

    diagnostics: dict[str, Any] = {}
    try:
        cache_key = _factor_cache_key(snapshot)
        technical = _FACTOR_CACHE.get(cache_key)
        factor_cache_hit = technical is not None
        if technical is None:
            m1_frame, diagnostics["M1"] = _prepare(snapshot.candles.get("M1"), "M1")
            m5_frame, diagnostics["M5"] = _prepare(snapshot.candles.get("M5"), "M5")
            m15_frame, diagnostics["M15"] = _prepare(snapshot.candles.get("M15"), "M15")
            m1, m5, m15 = _indicators(m1_frame), _indicators(m5_frame), _indicators(m15_frame)
            buy = _direction_score("BUY", m1, m5, m15)
            sell = _direction_score("SELL", m1, m5, m15)
            technical = {
                "diagnostics": diagnostics,
                "m1": m1,
                "m5": m5,
                "m15": m15,
                "buy": buy,
                "sell": sell,
            }
            if len(_FACTOR_CACHE) > 150:
                _FACTOR_CACHE.clear()
            _FACTOR_CACHE[cache_key] = technical
        else:
            diagnostics = technical["diagnostics"]
            m1, m5, m15 = technical["m1"], technical["m5"], technical["m15"]
            buy, sell = technical["buy"], technical["sell"]

        preferred = buy if buy["adjusted_score"] >= sell["adjusted_score"] else sell
        threshold = float(scalping_settings.SCALPING_UNIFIED_FACTOR_MIN_SCORE)
        minimum_factors = int(scalping_settings.SCALPING_UNIFIED_FACTOR_MIN_FACTORS)
        qualified = preferred["adjusted_score"] >= threshold and preferred["factor_count"] >= minimum_factors
        primary_direction = primary_signal.direction if primary_signal and primary_signal.direction in {"BUY", "SELL"} else "NONE"
        agreement = "AGREE" if primary_direction == preferred["direction"] else "NO_PRIMARY_DIRECTION" if primary_direction == "NONE" else "DISAGREE"
        return {
            "enabled": True,
            "status": "OK",
            "cache_hit": factor_cache_hit,
            "qualified": qualified,
            "preferred_direction": preferred["direction"],
            "preferred_score": preferred["adjusted_score"],
            "preferred_raw_score": preferred["raw_score"],
            "preferred_factor_count": preferred["factor_count"],
            "buy": buy,
            "sell": sell,
            "agreement_with_primary": agreement,
            "primary_direction": primary_direction,
            "minimum_score": threshold,
            "minimum_factors": minimum_factors,
            "m1": m1,
            "m5": m5,
            "m15": m15,
            "data_quality": diagnostics,
            "contributes_to_unified_decision": True,
            "changes_primary_trade_decision": True,
        }
    except Exception as error:
        return {
            "enabled": True,
            "status": "ERROR",
            "qualified": False,
            "error": f"{type(error).__name__}: {error}",
            "data_quality": diagnostics,
            "contributes_to_unified_decision": False,
            "changes_primary_trade_decision": False,
        }
