from __future__ import annotations

"""V4.0.2 technical playbook core retained inside the V5.0.2 research strategy.

A single decision combines V2 entry quality, closed-candle multi-timeframe
context, live M1 triggers, market structure, support/resistance, objective order
blocks, Atome-derived indicator families, session quality and normalized news.
Hard safety gates remain separate and cannot be overridden by a high score.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from time import perf_counter

import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.analysis.atome_factor_model import build_atome_factor_model
from services.analysis.verified_market_context import build_verified_market_context
from services.analysis.cross_market_context import build_cross_market_context
from services.analysis.scalp_trend_confirmation import analyze_m1_trend_confirmation
from services.analysis.scalp_playbook_engine import analyze_scalp_playbooks
from services.market_data.spread_utils import hard_entry_spread_limit_usd, spread_exceeds

_REQUIRED = {"time", "open", "high", "low", "close"}
_METRIC_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_STRUCTURE_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_ZONE_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_ORDER_BLOCK_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_TIMEFRAME_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return default if pd.isna(result) else result
    except (TypeError, ValueError):
        return default


def _utc_datetime(value: Any) -> datetime | None:
    try:
        stamp = pd.to_datetime(value).to_pydatetime()
    except Exception:
        return None
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _frame(data: Any, timeframe: str) -> pd.DataFrame:
    if data is None:
        raise ValueError(f"{timeframe} candles are missing.")

    minimum = max(55, int(scalping_settings.SCALPING_MIN_REQUIRED_CANDLES))
    if isinstance(data, pd.DataFrame):
        missing = _REQUIRED.difference(data.columns)
        if missing:
            raise ValueError(f"{timeframe} candles are missing columns: {sorted(missing)}")
        if len(data) < minimum:
            raise ValueError(f"{timeframe} has only {len(data)} valid candles; {minimum} required.")

        # The MT5 snapshot service marks frames that it already normalized.
        # Reusing that object avoids repeated dtype, NaN, and chronology scans
        # across roughly 700 rows on every half-second cache-hit cycle.
        if bool(data.attrs.get("scalping_normalized", False)):
            return data

        numeric_columns = [name for name in ("open", "high", "low", "close", "tick_volume") if name in data.columns]
        clean_numeric = all(pd.api.types.is_numeric_dtype(data[name]) for name in numeric_columns)
        clean_values = not bool(data[["open", "high", "low", "close"]].isna().any().any())
        chronological = bool(data["time"].is_monotonic_increasing)
        if clean_numeric and clean_values and chronological:
            return data
        frame = data.copy()
    else:
        frame = pd.DataFrame(data)
        missing = _REQUIRED.difference(frame.columns)
        if missing:
            raise ValueError(f"{timeframe} candles are missing columns: {sorted(missing)}")

    for column in ["open", "high", "low", "close", "tick_volume"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)
    if len(frame) < minimum:
        raise ValueError(f"{timeframe} has only {len(frame)} valid candles; {minimum} required.")
    return frame


def _frame_diagnostic(
    frame: pd.DataFrame,
    timeframe: str,
    source: str | None = None,
    cache_record: dict[str, Any] | None = None,
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    live_time = _utc_datetime(frame.iloc[-1]["time"])
    closed_time = _utc_datetime(frame.iloc[-2]["time"])
    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    source_name = (source or timeframe).split("_", 1)[0]
    duration_seconds = int(_TIMEFRAME_SECONDS.get(source_name, _TIMEFRAME_SECONDS.get(timeframe, 0)))
    closed_close_time = closed_time + timedelta(seconds=duration_seconds) if closed_time else None
    live_signed_age = (now - live_time).total_seconds() if live_time else None
    closed_open_signed_age = (now - closed_time).total_seconds() if closed_time else None
    closed_signed_age = (now - closed_close_time).total_seconds() if closed_close_time else None
    live_age = max(0.0, live_signed_age) if live_signed_age is not None else None
    closed_age = max(0.0, closed_signed_age) if closed_signed_age is not None else None
    cache = cache_record or {}
    return {
        "timeframe": timeframe,
        "source_timeframe": source or timeframe,
        "bars_received": len(frame),
        "minimum_required": max(55, int(scalping_settings.SCALPING_MIN_REQUIRED_CANDLES)),
        "live_candle_time": live_time.isoformat() if live_time else "",
        "last_closed_candle_time": closed_time.isoformat() if closed_time else "",
        "last_closed_candle_close_time": closed_close_time.isoformat() if closed_close_time else "",
        "timeframe_duration_seconds": duration_seconds,
        "live_data_age_seconds": round(live_age, 2) if live_age is not None else None,
        "closed_data_age_seconds": round(closed_age, 2) if closed_age is not None else None,
        "closed_candle_open_age_seconds": round(max(0.0, closed_open_signed_age), 2) if closed_open_signed_age is not None else None,
        "live_timestamp_future_seconds": round(max(0.0, -live_signed_age), 2) if live_signed_age is not None else None,
        "closed_timestamp_future_seconds": round(max(0.0, -closed_signed_age), 2) if closed_signed_age is not None else None,
        "diagnostic_clock_time": now.isoformat(),
        "cache_status": cache.get("status", "UNKNOWN"),
        "cache_age_seconds": cache.get("cache_age_seconds"),
        "fetch_duration_ms": cache.get("fetch_duration_ms"),
        "refresh_reason": cache.get("refresh_reason", ""),
        "tick_patched": bool(cache.get("tick_patched", False)),
        "next_boundary_in_seconds": cache.get("next_boundary_in_seconds"),
        "last_fetch_error": cache.get("last_fetch_error", ""),
        "valid": True,
    }


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    ranges = pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()],
        axis=1,
    )
    return ranges.max(axis=1).ewm(alpha=1.0 / period, adjust=False).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs = gain / loss.replace(0.0, float("nan"))
    value = 100.0 - 100.0 / (1.0 + rs)
    value = value.fillna(50.0).where(loss != 0.0, 100.0)
    return value.where((gain != 0.0) | (loss != 0.0), 50.0)


def _metric_cache_key(frame: pd.DataFrame, timeframe: str, live_trigger: bool) -> tuple[Any, ...]:
    if not live_trigger:
        # Closed-candle indicators must not be invalidated when only the
        # unfinished live candle is tick-patched. A new closed candle changes
        # this signature naturally at the next timeframe boundary.
        closed = frame.iloc[-2]
        previous = frame.iloc[-3]
        return (
            timeframe,
            False,
            len(frame),
            str(closed["time"]),
            round(_float(closed["open"]), 8),
            round(_float(closed["high"]), 8),
            round(_float(closed["low"]), 8),
            round(_float(closed["close"]), 8),
            str(previous["time"]),
            round(_float(previous["close"]), 8),
        )

    last = frame.iloc[-1]
    closed = frame.iloc[-2]
    return (
        timeframe,
        True,
        len(frame),
        str(last["time"]),
        round(_float(last["open"]), 8),
        round(_float(last["high"]), 8),
        round(_float(last["low"]), 8),
        round(_float(last["close"]), 8),
        str(closed["time"]),
        round(_float(closed["close"]), 8),
    )


def _metrics(frame: pd.DataFrame, timeframe: str, live_trigger: bool = False) -> dict[str, Any]:
    key = _metric_cache_key(frame, timeframe, live_trigger)
    cached = _METRIC_CACHE.get(key)
    if cached is not None:
        result = dict(cached)
        result["cache_hit"] = True
        return result

    working = frame.copy()
    close = working["close"]
    for period in (5, 8, 13, 21, 34, 50):
        working[f"ema{period}"] = close.ewm(span=period, adjust=False).mean()
    working["atr"] = _atr(working)
    working["rsi7"] = _rsi(close, 7)
    working["rsi14"] = _rsi(close, 14)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    working["macd"] = ema12 - ema26
    working["macd_signal"] = working["macd"].ewm(span=9, adjust=False).mean()
    middle = close.rolling(20).mean()
    deviation = close.rolling(20).std(ddof=0)
    working["bb_upper"] = middle + 2.0 * deviation
    working["bb_lower"] = middle - 2.0 * deviation

    index = -1 if live_trigger else -2
    latest = working.iloc[index]
    previous = working.iloc[index - 1]
    recent = working.iloc[index - 2:index + 1] if index == -1 else working.iloc[-4:-1]
    atr = max(_float(latest["atr"]), 1e-9)
    body = _float(latest["close"] - latest["open"])
    body_abs = abs(body)
    candle_range = max(_float(latest["high"] - latest["low"]), 1e-9)
    upper_wick = max(0.0, _float(latest["high"]) - max(_float(latest["open"]), _float(latest["close"])))
    lower_wick = max(0.0, min(_float(latest["open"]), _float(latest["close"])) - _float(latest["low"]))
    band_width = max(_float(latest["bb_upper"] - latest["bb_lower"]), 1e-9)
    band_position = (_float(latest["close"]) - _float(latest["bb_lower"])) / band_width
    absolute_index = len(working) + index
    lookback = working.iloc[max(0, absolute_index - int(scalping_settings.SCALPING_BREAKOUT_LOOKBACK)):absolute_index]
    previous_high = _float(lookback["high"].max())
    previous_low = _float(lookback["low"].min())
    candle_time = _utc_datetime(latest["time"])

    result = {
        "timeframe": timeframe,
        "candle_time": candle_time,
        "open": _float(latest["open"]),
        "high": _float(latest["high"]),
        "low": _float(latest["low"]),
        "close": _float(latest["close"]),
        "previous_close": _float(previous["close"]),
        "ema_fast": _float(latest["ema5"]),
        "ema_slow": _float(latest["ema13"]),
        "ema_context": _float(latest["ema34"]),
        "ema8": _float(latest["ema8"]),
        "ema21": _float(latest["ema21"]),
        "ema50": _float(latest["ema50"]),
        "ema_fast_slope": _float(latest["ema5"] - working.iloc[index - 3]["ema5"]),
        "atr": atr,
        "rsi": _float(latest["rsi14"], 50.0),
        "rsi7": _float(latest["rsi7"], 50.0),
        "macd": _float(latest["macd"]),
        "macd_signal": _float(latest["macd_signal"]),
        "momentum": _float(latest["close"] - working.iloc[index - 3]["close"]),
        "previous_high": previous_high,
        "previous_low": previous_low,
        "breakout_buy": _float(latest["close"]) > previous_high,
        "breakout_sell": _float(latest["close"]) < previous_low,
        "candle_body": body,
        "candle_range": candle_range,
        "body_range_ratio": body_abs / candle_range,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "hammer": body_abs > 0 and lower_wick >= body_abs * 2.0 and upper_wick <= body_abs * 1.25,
        "shooting_star": body_abs > 0 and upper_wick >= body_abs * 2.0 and lower_wick <= body_abs * 1.25,
        "bullish_engulfing": body > 0 and _float(previous["close"] - previous["open"]) < 0 and _float(latest["close"]) >= _float(previous["open"]) and _float(latest["open"]) <= _float(previous["close"]),
        "bearish_engulfing": body < 0 and _float(previous["close"] - previous["open"]) > 0 and _float(latest["open"]) >= _float(previous["close"]) and _float(latest["close"]) <= _float(previous["open"]),
        "three_bullish": bool(len(recent) == 3 and (recent["close"] > recent["open"]).all()),
        "three_bearish": bool(len(recent) == 3 and (recent["close"] < recent["open"]).all()),
        "bb_position": max(0.0, min(1.0, band_position)),
        "distance_from_fast_ema": abs(_float(latest["close"] - latest["ema5"])),
        "distance_fast_atr_ratio": abs(_float(latest["close"] - latest["ema5"])) / atr,
        "calculation_source": "LIVE_CANDLE" if live_trigger else "CLOSED_CANDLE",
        "cache_hit": False,
    }
    if len(_METRIC_CACHE) > 250:
        _METRIC_CACHE.clear()
    _METRIC_CACHE[key] = dict(result)
    return result



def _live_trigger_metrics(frame: pd.DataFrame, closed: dict[str, Any]) -> dict[str, Any]:
    """Build current-M1 trigger metrics without recalculating every indicator.

    Closed-candle EMA and ATR values are already cached. The live EMA/ATR are
    updated recursively from those values, while candle-shape metrics use only
    the current and previous rows. This preserves trigger accuracy and removes
    the expensive full-series indicator calculation from every tick-patched
    cycle.
    """
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]
    open_price = _float(latest["open"])
    high = _float(latest["high"])
    low = _float(latest["low"])
    close = _float(latest["close"])
    previous_open = _float(previous["open"])
    previous_close = _float(previous["close"])

    ema_alpha = 2.0 / (float(scalping_settings.SCALPING_FAST_EMA_PERIOD) + 1.0)
    ema_fast = ema_alpha * close + (1.0 - ema_alpha) * _float(closed.get("ema_fast"), close)
    previous_atr = max(_float(closed.get("atr"), 0.0), 1e-9)
    true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
    atr_alpha = 1.0 / max(1.0, float(scalping_settings.SCALPING_ATR_PERIOD))
    atr = atr_alpha * true_range + (1.0 - atr_alpha) * previous_atr

    body = close - open_price
    body_abs = abs(body)
    candle_range = max(high - low, 1e-9)
    upper_wick = max(0.0, high - max(open_price, close))
    lower_wick = max(0.0, min(open_price, close) - low)
    previous_body = previous_close - previous_open

    return {
        "timeframe": "M1",
        "candle_time": _utc_datetime(latest["time"]),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "previous_close": previous_close,
        "ema_fast": ema_fast,
        "atr": atr,
        "candle_body": body,
        "candle_range": candle_range,
        "body_range_ratio": body_abs / candle_range,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "hammer": body_abs > 0 and lower_wick >= body_abs * 2.0 and upper_wick <= body_abs * 1.25,
        "shooting_star": body_abs > 0 and upper_wick >= body_abs * 2.0 and lower_wick <= body_abs * 1.25,
        "bullish_engulfing": body > 0 and previous_body < 0 and close >= previous_open and open_price <= previous_close,
        "bearish_engulfing": body < 0 and previous_body > 0 and open_price >= previous_close and close <= previous_open,
        "distance_from_fast_ema": abs(close - ema_fast),
        "distance_fast_atr_ratio": abs(close - ema_fast) / max(atr, 1e-9),
        "calculation_source": "LIVE_CANDLE_LIGHTWEIGHT",
    }



def _closed_context_key(frame: pd.DataFrame, timeframe: str) -> tuple[Any, ...]:
    closed = frame.iloc[-2]
    return (
        timeframe,
        len(frame),
        str(closed["time"]),
        round(_float(closed["open"]), 8),
        round(_float(closed["high"]), 8),
        round(_float(closed["low"]), 8),
        round(_float(closed["close"]), 8),
    )


def _cached_context(
    cache: dict[tuple[Any, ...], dict[str, Any]],
    key: tuple[Any, ...],
    builder,
) -> dict[str, Any]:
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)
    value = builder()
    if len(cache) > 150:
        cache.clear()
    cache[key] = dict(value)
    return value

def _pivots(frame: pd.DataFrame, left: int = 2, right: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    values = frame.reset_index(drop=True)
    for index in range(left, len(values) - right):
        high = _float(values.iloc[index]["high"])
        low = _float(values.iloc[index]["low"])
        window = values.iloc[index - left:index + right + 1]
        if high >= _float(window["high"].max()):
            highs.append((index, high))
        if low <= _float(window["low"].min()):
            lows.append((index, low))
    return highs, lows


def _structure(frame: pd.DataFrame, current_price: float) -> dict[str, Any]:
    closed = frame.iloc[:-1]
    highs, lows = _pivots(closed)
    last_highs, last_lows = highs[-3:], lows[-3:]
    direction = "NEUTRAL"
    reason = "Swing sequence is mixed."
    if len(last_highs) >= 2 and len(last_lows) >= 2:
        if last_highs[-1][1] > last_highs[-2][1] and last_lows[-1][1] > last_lows[-2][1]:
            direction, reason = "BULLISH", "Higher high and higher low sequence."
        elif last_highs[-1][1] < last_highs[-2][1] and last_lows[-1][1] < last_lows[-2][1]:
            direction, reason = "BEARISH", "Lower high and lower low sequence."
    else:
        sample = closed.iloc[-12:]
        if len(sample) >= 3:
            change = _float(sample.iloc[-1]["close"] - sample.iloc[0]["close"])
            threshold = max(_float(_atr(sample).iloc[-1]) * 0.20, 1e-9)
            if change > threshold:
                direction, reason = "BULLISH", "Closed-candle progression is bullish without enough classical pivots."
            elif change < -threshold:
                direction, reason = "BEARISH", "Closed-candle progression is bearish without enough classical pivots."
    recent_high = last_highs[-1][1] if last_highs else _float(closed.iloc[-20:]["high"].max())
    recent_low = last_lows[-1][1] if last_lows else _float(closed.iloc[-20:]["low"].min())
    bos_buy = current_price > recent_high
    bos_sell = current_price < recent_low
    return {
        "direction": direction,
        "reason": reason,
        "recent_swing_high": recent_high,
        "recent_swing_low": recent_low,
        "bos_buy": bos_buy,
        "bos_sell": bos_sell,
        "choch_buy": direction == "BEARISH" and bos_buy,
        "choch_sell": direction == "BULLISH" and bos_sell,
        "swing_highs": [round(value, 5) for _, value in last_highs],
        "swing_lows": [round(value, 5) for _, value in last_lows],
    }


def _zones(frame: pd.DataFrame, price: float, atr: float) -> dict[str, Any]:
    highs, lows = _pivots(frame.iloc[:-1])
    tolerance = max(atr * 0.20, 0.10)

    def cluster(points: list[tuple[int, float]]) -> list[dict[str, float]]:
        clusters: list[list[float]] = []
        for _, value in points[-24:]:
            for group in clusters:
                if abs(value - sum(group) / len(group)) <= tolerance:
                    group.append(value)
                    break
            else:
                clusters.append([value])
        return [
            {"lower": min(group) - tolerance / 2, "upper": max(group) + tolerance / 2, "touches": len(group), "center": sum(group) / len(group)}
            for group in clusters
        ]

    supports = sorted((zone for zone in cluster(lows) if zone["center"] <= price), key=lambda z: price - z["center"])
    resistances = sorted((zone for zone in cluster(highs) if zone["center"] >= price), key=lambda z: z["center"] - price)
    support = supports[0] if supports else None
    resistance = resistances[0] if resistances else None
    support_distance = price - support["upper"] if support else None
    resistance_distance = resistance["lower"] - price if resistance else None
    return {
        "support": support,
        "resistance": resistance,
        "near_support": bool(support and support_distance <= atr * 0.35),
        "near_resistance": bool(resistance and resistance_distance <= atr * 0.35),
        "support_distance_atr": round(support_distance / atr, 4) if support_distance is not None and atr > 0 else None,
        "resistance_distance_atr": round(resistance_distance / atr, 4) if resistance_distance is not None and atr > 0 else None,
    }


def _order_blocks(frame: pd.DataFrame, price: float) -> dict[str, Any]:
    work = frame.iloc[:-1].copy().reset_index(drop=True)
    atrs = _atr(work)
    bullish: list[dict[str, Any]] = []
    bearish: list[dict[str, Any]] = []
    start = max(8, len(work) - 55)
    for index in range(start, len(work) - 2):
        candle = work.iloc[index]
        next_two = work.iloc[index + 1:index + 3]
        atr = max(_float(atrs.iloc[index]), 1e-9)
        prior = work.iloc[max(0, index - 8):index]
        if prior.empty:
            continue
        displacement_up = _float(next_two["close"].max() - candle["high"])
        displacement_down = _float(candle["low"] - next_two["close"].min())
        prior_high = _float(prior["high"].max())
        prior_low = _float(prior["low"].min())
        if _float(candle["close"]) < _float(candle["open"]) and displacement_up >= atr * 0.55 and _float(next_two["close"].max()) > prior_high:
            bullish.append({"lower": _float(candle["low"]), "upper": _float(candle["open"]), "strength": displacement_up / atr, "time": str(candle["time"])})
        if _float(candle["close"]) > _float(candle["open"]) and displacement_down >= atr * 0.55 and _float(next_two["close"].min()) < prior_low:
            bearish.append({"lower": _float(candle["open"]), "upper": _float(candle["high"]), "strength": displacement_down / atr, "time": str(candle["time"])})
    bull = bullish[-1] if bullish else None
    bear = bearish[-1] if bearish else None
    return {
        "bullish": bull,
        "bearish": bear,
        "in_bullish": bool(bull and bull["lower"] <= price <= bull["upper"]),
        "in_bearish": bool(bear and bear["lower"] <= price <= bear["upper"]),
        "bullish_candidates": len(bullish),
        "bearish_candidates": len(bearish),
    }


def _regime(m5: dict[str, Any], m15: dict[str, Any], h1: dict[str, Any], h4: dict[str, Any], structure: dict[str, Any]) -> dict[str, Any]:
    bullish_votes = sum(item["ema8"] > item["ema21"] for item in (m5, m15, h1, h4))
    bearish_votes = sum(item["ema8"] < item["ema21"] for item in (m5, m15, h1, h4))
    if bullish_votes >= 3 and structure["direction"] == "BULLISH":
        return {"mode": "TREND", "direction": "BUY", "confidence": bullish_votes / 4.0, "reason": f"{bullish_votes}/4 timeframes and bullish structure align."}
    if bearish_votes >= 3 and structure["direction"] == "BEARISH":
        return {"mode": "TREND", "direction": "SELL", "confidence": bearish_votes / 4.0, "reason": f"{bearish_votes}/4 timeframes and bearish structure align."}
    if structure["choch_buy"]:
        return {"mode": "REVERSAL", "direction": "BUY", "confidence": 0.75, "reason": "Bullish change of character."}
    if structure["choch_sell"]:
        return {"mode": "REVERSAL", "direction": "SELL", "confidence": 0.75, "reason": "Bearish change of character."}
    if structure["bos_buy"]:
        return {"mode": "BREAKOUT", "direction": "BUY", "confidence": 0.8, "reason": "Price broke the latest closed swing high."}
    if structure["bos_sell"]:
        return {"mode": "BREAKOUT", "direction": "SELL", "confidence": 0.8, "reason": "Price broke the latest closed swing low."}
    ema_separation = abs(m15["ema8"] - m15["ema21"]) / max(m15["atr"], 1e-9)
    if ema_separation < 0.18 and abs(bullish_votes - bearish_votes) <= 1:
        return {"mode": "RANGE", "direction": "NEUTRAL", "confidence": 0.6, "reason": "M15 EMA separation is small and timeframe votes are balanced."}
    return {
        "mode": "NO_TRADE",
        "direction": "NEUTRAL",
        "confidence": 0.3,
        "reason": f"Conflicting context: bullish_votes={bullish_votes}, bearish_votes={bearish_votes}, structure={structure['direction']}.",
    }


def _trigger(
    direction: str,
    live: dict[str, Any],
    closed_m1: dict[str, Any],
    structure: dict[str, Any],
    zones: dict[str, Any],
    blocks: dict[str, Any],
    regime: dict[str, Any],
    mtf: dict[str, Any],
    verified: dict[str, Any],
    base_pattern: str,
) -> tuple[bool, str, list[str], float]:
    buy = direction == "BUY"
    standard_points = float(getattr(scalping_settings, "SCALPING_UNIFIED_STANDARD_TRIGGER_POINTS", 16.0))
    if base_pattern in {"BREAKOUT", "PULLBACK_CONTINUATION", "MOMENTUM_IMPULSE"}:
        return True, base_pattern, [f"V2-qualified {base_pattern.lower()} trigger."], standard_points
    if buy and (live["bullish_engulfing"] or live["hammer"]) and (zones["near_support"] or blocks["in_bullish"]):
        return True, "ZONE_REJECTION", ["Bullish live-candle rejection at support/order block."], standard_points
    if not buy and (live["bearish_engulfing"] or live["shooting_star"]) and (zones["near_resistance"] or blocks["in_bearish"]):
        return True, "ZONE_REJECTION", ["Bearish live-candle rejection at resistance/order block."], standard_points
    if buy and structure["bos_buy"] and live["body_range_ratio"] >= 0.55 and live["candle_body"] > 0:
        return True, "STRUCTURE_BREAK", ["Bullish break of structure with displacement candle."], standard_points
    if not buy and structure["bos_sell"] and live["body_range_ratio"] >= 0.55 and live["candle_body"] < 0:
        return True, "STRUCTURE_BREAK", ["Bearish break of structure with displacement candle."], standard_points

    # Strong directional context previously had no way to enter after a normal
    # M1 pullback unless a new breakout or a major zone rejection appeared.
    # A trend reclaim is a concrete live-candle trigger, not a context-only
    # shortcut. It requires MTF, swing structure, regime, ADX, volume, RSI,
    # fast-EMA reclaim, and anti-chase VWAP/distance checks to agree.
    required_live_fields = {
        "close", "ema_fast", "previous_close", "low", "high",
        "candle_body", "body_range_ratio", "distance_fast_atr_ratio",
    }
    if bool(getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_ENABLED", True)) and required_live_fields.issubset(live):
        expected_structure = "BULLISH" if buy else "BEARISH"
        context_ok = (
            regime.get("mode") == "TREND"
            and regime.get("direction") == direction
            and structure.get("direction") == expected_structure
            and mtf.get("dominant_direction") == direction
        )
        body_ok = live["candle_body"] > 0 if buy else live["candle_body"] < 0
        close_side_ok = live["close"] > live["ema_fast"] if buy else live["close"] < live["ema_fast"]
        touched_fast = live["low"] <= live["ema_fast"] if buy else live["high"] >= live["ema_fast"]
        reclaimed_fast = (
            live["previous_close"] <= live["ema_fast"] and live["close"] > live["ema_fast"]
            if buy
            else live["previous_close"] >= live["ema_fast"] and live["close"] < live["ema_fast"]
        )
        distance_ok = live["distance_fast_atr_ratio"] <= float(
            getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_MAX_FAST_EMA_DISTANCE_ATR", 0.35)
        )
        body_ratio_ok = live["body_range_ratio"] >= float(
            getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_MIN_BODY_RATIO", 0.30)
        )
        vwap_distance = _float(verified.get("vwap_distance_atr", 0.0))
        vwap_ok = abs(vwap_distance) <= float(
            getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_MAX_VWAP_DISTANCE_ATR", 1.75)
        )
        relative_volume = _float(verified.get("relative_tick_volume", 0.0))
        volume_ok = relative_volume >= float(
            getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_MIN_RELATIVE_VOLUME", 0.65)
        )
        adx = _float(verified.get("adx_m5", 0.0))
        trend_direction = str(verified.get("trend_direction", "NEUTRAL"))
        adx_ok = adx >= float(getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_MIN_ADX", 18.0)) and trend_direction == direction
        rsi = _float(closed_m1.get("rsi", 50.0), 50.0)
        if buy:
            rsi_ok = float(getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_BUY_RSI_MIN", 42.0)) <= rsi <= float(getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_BUY_RSI_MAX", 68.0))
        else:
            rsi_ok = float(getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_SELL_RSI_MIN", 32.0)) <= rsi <= float(getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_SELL_RSI_MAX", 58.0))

        if all((context_ok, body_ok, close_side_ok, touched_fast or reclaimed_fast, distance_ok, body_ratio_ok, vwap_ok, volume_ok, adx_ok, rsi_ok)):
            points = float(getattr(scalping_settings, "SCALPING_UNIFIED_TREND_RECLAIM_TRIGGER_POINTS", 20.0))
            return True, "TREND_RECLAIM", [
                f"Verified {direction} trend pullback reclaimed the M1 fast EMA; "
                f"distance={live['distance_fast_atr_ratio']:.2f} ATR, VWAP={vwap_distance:+.2f} ATR, "
                f"ADX={adx:.1f}, relative volume={relative_volume:.2f}."
            ], points

    return False, "NONE", [], 0.0


def _multi_timeframe_alignment(*items: dict[str, Any]) -> dict[str, Any]:
    directions: list[str] = []
    for item in items:
        fast = _float(item.get("ema8"))
        slow = _float(item.get("ema21"))
        directions.append("BUY" if fast > slow else "SELL" if fast < slow else "NEUTRAL")
    buy_count = directions.count("BUY")
    sell_count = directions.count("SELL")
    neutral_count = directions.count("NEUTRAL")
    dominant = "BUY" if buy_count >= 2 and buy_count > sell_count else "SELL" if sell_count >= 2 and sell_count > buy_count else "NEUTRAL"
    return {
        "directions": directions,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "neutral_count": neutral_count,
        "dominant_direction": dominant,
        "directional_edge": abs(buy_count - sell_count),
        "resolved": dominant in {"BUY", "SELL"},
    }


def _score_direction(direction: str, snapshot: ScalpingSnapshotState, base: ScalpSignalState, metrics: dict[str, Any], news: dict[str, Any]) -> tuple[float, dict[str, float], list[str], str, bool, list[str]]:
    buy = direction == "BUY"
    m1, m5, m15, h1, h4 = metrics["M1"], metrics["M5"], metrics["M15"], metrics["H1"], metrics["H4"]
    structure, zones, blocks, regime = metrics["structure"], metrics["zones"], metrics["order_blocks"], metrics["regime"]
    factor_model = metrics["factor_model"]
    base_score = _float(base.metrics.get("buy_score" if buy else "sell_score", 0.0))
    factor_direction = factor_model.get("buy" if buy else "sell", {})
    factor_score = _float(factor_direction.get("adjusted_score", 0.0))
    components: dict[str, float] = {}
    reasons: list[str] = []
    families: list[str] = []

    components["legacy_entry_quality"] = min(12.0, base_score * 0.12)
    if components["legacy_entry_quality"] >= 4.0:
        families.append("legacy_entry")

    components["atome_factor_families"] = min(12.0, factor_score * 0.12)
    if factor_score >= 25.0 and int(factor_direction.get("factor_count", 0)) >= 2:
        families.append("indicator_families")
        reasons.append(f"Unified indicator family score={factor_score:.1f} for {direction}.")

    mtf = metrics.get("multi_timeframe_alignment") or _multi_timeframe_alignment(m5, m15, h1, h4)
    mtf_alignments = int(mtf["buy_count"] if buy else mtf["sell_count"])
    mtf_dominant = mtf.get("dominant_direction") == direction
    components["multi_timeframe"] = mtf_alignments * 4.0 if mtf_dominant else 0.0
    if mtf_dominant:
        families.append("multi_timeframe")
        reasons.append(
            f"Resolved multi-timeframe context supports {direction}: "
            f"BUY={mtf['buy_count']}, SELL={mtf['sell_count']}, NEUTRAL={mtf['neutral_count']}."
        )
    elif mtf_alignments:
        reasons.append(
            f"Multi-timeframe votes are unresolved/opposed for {direction}: "
            f"BUY={mtf['buy_count']}, SELL={mtf['sell_count']}, NEUTRAL={mtf['neutral_count']}; no points awarded."
        )

    structure_match = structure["direction"] == ("BULLISH" if buy else "BEARISH")
    structure_break = structure["bos_buy"] if buy else structure["bos_sell"]
    # Do not double-count a break of structure when the underlying swing
    # sequence is neutral or points the other way. In that case the event is
    # represented by the BREAKOUT/REVERSAL regime only. Market-structure points
    # and the market_structure confirmation family require directional swing
    # structure to agree with the scored side.
    components["market_structure"] = (14.0 if structure_break else 10.0) if structure_match else 0.0
    if structure_match:
        families.append("market_structure")
        reasons.append(structure["reason"])
    elif structure_break:
        reasons.append(
            f"{direction} break-of-structure context is recorded by the regime, "
            "but neutral/opposing swing structure receives no structure points."
        )

    regime_match = regime["direction"] == direction
    components["market_regime"] = 10.0 if regime_match else 2.0 if regime["mode"] == "RANGE" else 0.0
    if regime_match:
        families.append("market_regime")
        reasons.append(f"{regime['mode']} regime supports {direction}.")

    live = metrics["M1_live"]
    base_pattern = base.pattern if base.direction == direction else "NONE"
    mtf = metrics.get("multi_timeframe_alignment") or _multi_timeframe_alignment(m5, m15, h1, h4)
    verified = metrics.get("verified_context", {})
    trigger_ok, pattern, trigger_reasons, trigger_points = _trigger(
        direction, live, m1, structure, zones, blocks, regime, mtf, verified, base_pattern
    )
    components["candle_trigger"] = trigger_points if trigger_ok else 0.0
    if trigger_ok:
        families.append("entry_trigger")
    reasons.extend(trigger_reasons)

    zone_ok = zones["near_support"] if buy else zones["near_resistance"]
    zone_conflict = zones["near_resistance"] if buy else zones["near_support"]
    block_ok = blocks["in_bullish"] if buy else blocks["in_bearish"]
    block_conflict = blocks["in_bearish"] if buy else blocks["in_bullish"]
    components["support_resistance"] = 6.0 if zone_ok else -4.0 if zone_conflict else 0.0
    components["order_block"] = 6.0 if block_ok else -4.0 if block_conflict else 0.0
    if zone_ok or block_ok:
        families.append("location")
    if zone_conflict:
        reasons.append(f"{direction} is penalized because price is near the opposing zone.")
    if block_conflict:
        reasons.append(f"{direction} is penalized by the opposing order block.")

    momentum_ok = (m1["momentum"] > 0 and m1["macd"] > m1["macd_signal"]) if buy else (m1["momentum"] < 0 and m1["macd"] < m1["macd_signal"])
    components["momentum"] = 5.0 if momentum_ok else 0.0
    if momentum_ok:
        families.append("momentum")

    components["session_liquidity"] = 3.0 if snapshot.session in {"London", "New York"} else 1.5

    bias = str(news.get("directional_bias", "NEUTRAL"))
    if bias == direction:
        components["economic_context"] = 5.0
        families.append("economic_context")
        reasons.append("Verified economic surprise agrees with direction.")
    elif bias not in {"NEUTRAL", direction}:
        components["economic_context"] = -5.0
        reasons.append("Verified economic surprise conflicts with direction.")
    else:
        components["economic_context"] = 0.0

    verified = metrics.get("verified_context", {})
    relative_volume = _float(verified.get("relative_tick_volume", 1.0), 1.0)
    signed_volume = _float(verified.get("signed_tick_volume_proxy", 0.0))
    volume_aligned = signed_volume > 0.15 if buy else signed_volume < -0.15
    volume_conflict = signed_volume < -0.25 if buy else signed_volume > 0.25
    if relative_volume >= 1.10 and volume_aligned:
        components["verified_volume"] = 2.0
        reasons.append(f"Verified tick-volume proxy confirms {direction} (relative={relative_volume:.2f}).")
    elif volume_conflict:
        components["verified_volume"] = -2.0
        reasons.append(f"Verified tick-volume proxy conflicts with {direction}.")
    elif relative_volume < 0.55:
        components["verified_volume"] = -1.0
        reasons.append("Relative MT5 tick volume is weak.")
    else:
        components["verified_volume"] = 0.0

    vwap_distance = _float(verified.get("vwap_distance_atr", 0.0))
    vwap_aligned = vwap_distance > 0.10 if buy else vwap_distance < -0.10
    vwap_conflict = vwap_distance < -0.25 if buy else vwap_distance > 0.25
    components["verified_vwap"] = 2.0 if vwap_aligned and abs(vwap_distance) <= 1.50 else -2.0 if vwap_conflict else 0.0
    if components["verified_vwap"] > 0:
        reasons.append(f"Rolling VWAP context supports {direction} ({vwap_distance:+.2f} ATR).")
    elif components["verified_vwap"] < 0:
        reasons.append(f"Rolling VWAP context conflicts with {direction} ({vwap_distance:+.2f} ATR).")

    adx = _float(verified.get("adx_m5", 0.0))
    verified_trend = str(verified.get("trend_direction", "NEUTRAL"))
    if adx >= 22.0 and verified_trend == direction:
        components["verified_trend_strength"] = 2.0
    elif adx >= 30.0 and verified_trend not in {"NEUTRAL", direction}:
        components["verified_trend_strength"] = -2.0
    else:
        components["verified_trend_strength"] = 0.0

    pivot_name = str(verified.get("nearest_pivot", ""))
    pivot_distance = verified.get("nearest_pivot_distance_atr")
    pivot_distance = _float(pivot_distance, 99.0) if pivot_distance is not None else 99.0
    supportive = pivot_name in ({"S1", "S2"} if buy else {"R1", "R2"})
    opposing = pivot_name in ({"R1", "R2"} if buy else {"S1", "S2"})
    components["verified_pivot"] = 1.5 if supportive and pivot_distance <= 0.35 else -1.5 if opposing and pivot_distance <= 0.35 else 0.0

    cross = metrics.get("cross_market_context", {})
    cross_bias = str(cross.get("gold_bias", "NEUTRAL"))
    cross_ok = str(cross.get("status", "")) == "OK"
    if cross_ok and cross_bias == direction:
        components["cross_market"] = 3.0
        families.append("cross_market")
        reasons.append("Verified MT5 cross-market USD pressure agrees with the gold direction.")
    elif cross_ok and cross_bias not in {"NEUTRAL", direction}:
        components["cross_market"] = -3.0
        reasons.append("Verified MT5 cross-market USD pressure conflicts with the gold direction.")
    else:
        components["cross_market"] = 0.0

    score = max(0.0, min(100.0, sum(components.values())))
    families = list(dict.fromkeys(families))
    return score, components, reasons, pattern, trigger_ok, families



def _score_acceptance(
    *,
    score: float,
    minimum_score: float,
    direction: str,
    direction_margin: float,
    minimum_direction_margin: float,
    family_count: int,
    minimum_families: int,
    entry_trigger_present: bool,
    directional_context_present: bool,
    regime: dict[str, Any],
    verified_context: dict[str, Any],
    vwap_overextended: bool,
) -> dict[str, Any]:
    """Evaluate the score gate without weakening hard safety requirements."""
    raw_pass = score >= minimum_score
    shortfall = max(0.0, minimum_score - score)
    tolerance = max(
        0.0,
        float(getattr(scalping_settings, "SCALPING_UNIFIED_BORDERLINE_SCORE_TOLERANCE", 0.0)),
    )
    enabled = bool(
        getattr(scalping_settings, "SCALPING_UNIFIED_BORDERLINE_SCORE_ENABLED", False)
    )
    required_families = max(
        minimum_families,
        int(getattr(scalping_settings, "SCALPING_UNIFIED_BORDERLINE_MIN_CONFIRMING_FAMILIES", minimum_families)),
    )
    required_margin = max(
        minimum_direction_margin,
        float(getattr(scalping_settings, "SCALPING_UNIFIED_BORDERLINE_MIN_DIRECTION_MARGIN", minimum_direction_margin)),
    )
    minimum_completeness = float(
        getattr(scalping_settings, "SCALPING_UNIFIED_BORDERLINE_MIN_DATA_COMPLETENESS", 0.95)
    )
    completeness = _float(
        verified_context.get(
            "data_completeness_score",
            verified_context.get("data_quality_score", 0.0),
        )
    )
    allowed_regimes = set(
        getattr(
            scalping_settings,
            "SCALPING_UNIFIED_BORDERLINE_ALLOWED_REGIMES",
            ("TREND", "BREAKOUT", "REVERSAL"),
        )
    )
    regime_mode = str(regime.get("mode", "NO_TRADE"))
    regime_direction = str(regime.get("direction", "NEUTRAL"))

    borderline_pass = bool(
        enabled
        and not raw_pass
        and shortfall <= tolerance + 1e-9
        and entry_trigger_present
        and directional_context_present
        and family_count >= required_families
        and direction_margin >= required_margin
        and regime_mode in allowed_regimes
        and regime_direction == direction
        and str(verified_context.get("status", "ERROR")) == "OK"
        and completeness >= minimum_completeness
        and not vwap_overextended
    )
    return {
        "passed": raw_pass or borderline_pass,
        "raw_pass": raw_pass,
        "borderline_pass": borderline_pass,
        "mode": "RAW_PASS" if raw_pass else "BORDERLINE_ACCEPTED" if borderline_pass else "BLOCKED",
        "shortfall": round(shortfall, 4),
        "tolerance": tolerance,
        "required_families": required_families,
        "required_direction_margin": required_margin,
        "minimum_data_completeness": minimum_completeness,
        "data_completeness": completeness,
    }

def _direct_score_decision(
    *,
    buy_score: float,
    sell_score: float,
) -> dict[str, Any]:
    """Select the higher unified score in paper mode.

    This intentionally contains no secondary strategy gates. BUY wins when its
    score is strictly greater than SELL; SELL wins when its score is strictly
    greater than BUY. An exact tie returns WAIT. Hard operational protections
    remain outside this function: valid market data, global spread limits, news
    blocks, risk limits, maximum positions, and the loss-streak cooldown.
    """
    enabled = bool(getattr(scalping_settings, "SCALPING_DIRECT_SCORE_PAPER_ENABLED", False))
    paper_only = bool(scalping_settings.SCALPING_PAPER_ONLY)
    controlled_demo = bool(
        getattr(scalping_settings, "SCALPING_DEMO_EXECUTION_ENABLED", False)
        and not getattr(scalping_settings, "SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED", False)
    )
    score_runtime_enabled = paper_only or controlled_demo
    if buy_score > sell_score:
        direction = "BUY"
        winner_score = buy_score
        other_score = sell_score
    elif sell_score > buy_score:
        direction = "SELL"
        winner_score = sell_score
        other_score = buy_score
    else:
        direction = "NONE"
        winner_score = buy_score
        other_score = sell_score

    minimum_winner_score = float(
        getattr(scalping_settings, "SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE", 0.0)
    )
    direction_exists = direction in {"BUY", "SELL"}
    winner_quality_passed = float(winner_score) >= minimum_winner_score
    passed = bool(enabled and score_runtime_enabled and direction_exists and winner_quality_passed)
    if passed:
        mode = "DIRECT_SCORE"
    elif direction == "NONE":
        mode = "TIE_WAIT"
    elif enabled and score_runtime_enabled and not winner_quality_passed:
        mode = "WEAK_SCORE_WAIT"
    else:
        mode = "DISABLED"
    failed_gates = []
    if direction == "NONE":
        failed_gates.append("exact_tie")
    elif not winner_quality_passed:
        failed_gates.append("winner_score")
    if not enabled or not score_runtime_enabled:
        failed_gates.append("direct_score_disabled")
    return {
        "passed": passed,
        "mode": mode,
        "winner_direction": direction,
        "winner_score": round(float(winner_score), 4),
        "other_score": round(float(other_score), 4),
        "margin": round(abs(float(buy_score) - float(sell_score)), 4),
        "buy_score": round(float(buy_score), 4),
        "sell_score": round(float(sell_score), 4),
        "paper_only": paper_only,
        "controlled_demo": controlled_demo,
        "score_runtime_enabled": score_runtime_enabled,
        "enabled": enabled,
        "minimum_winner_score": minimum_winner_score,
        "winner_quality_passed": winner_quality_passed,
        "failed_gates": failed_gates,
    }

def _trade_economics(
    *,
    snapshot: ScalpingSnapshotState,
    m1: dict[str, Any],
    entry_path: str,
) -> dict[str, Any]:
    """Create spread-, volatility-, and barrier-aware TP/SL values.

    Paper mode retains the historical economics for regression compatibility.
    Controlled demo mode models the actual excursion required after crossing the
    bid/ask spread. A stop must leave enough adverse-price room beyond the
    initial spread, while the target cannot require an excessively asymmetric
    move relative to that room.
    """

    value_per_price = max(
        1e-9,
        float(snapshot.contract_size) * float(scalping_settings.SCALPING_LOT_SIZE),
    )
    spread_cost = max(0.0, float(snapshot.spread) * value_per_price)
    atr_profit_capacity = max(0.0, _float(m1.get("atr", 0.0)) * value_per_price)
    controlled_demo = bool(
        not scalping_settings.SCALPING_PAPER_ONLY
        and getattr(scalping_settings, "SCALPING_DEMO_EXECUTION_ENABLED", False)
        and not getattr(scalping_settings, "SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED", False)
    )

    if controlled_demo:
        base_target = float(scalping_settings.SCALPING_DEMO_MIN_PROFIT_TARGET_USD)
        maximum_target = float(scalping_settings.SCALPING_DEMO_MAX_PROFIT_TARGET_USD)
        target = max(
            base_target,
            spread_cost * float(scalping_settings.SCALPING_DEMO_TARGET_SPREAD_MULTIPLIER),
            atr_profit_capacity
            * float(scalping_settings.SCALPING_DEMO_TARGET_ATR_PROFIT_RATIO),
        )
        if entry_path == "BREAKOUT_RETEST":
            target = max(
                target,
                atr_profit_capacity
                * float(scalping_settings.SCALPING_DEMO_BREAKOUT_TARGET_ATR_PROFIT_RATIO),
            )

        adverse_buffer = max(
            float(scalping_settings.SCALPING_DEMO_STOP_MIN_ADVERSE_BUFFER_USD),
            atr_profit_capacity
            * float(scalping_settings.SCALPING_DEMO_STOP_ADVERSE_ATR_RATIO),
        )
        minimum_stop = float(scalping_settings.SCALPING_DEMO_MIN_STOP_LOSS_USD)
        maximum_stop = float(scalping_settings.SCALPING_DEMO_MAX_STOP_LOSS_USD)
        stop = max(minimum_stop, spread_cost + adverse_buffer)
        minimum_reward_risk = float(
            scalping_settings.SCALPING_DEMO_MIN_REWARD_RISK_RATIO
        )
        target = max(target, stop * minimum_reward_risk)
        target = min(maximum_target, target)

        # The favorable mid-price excursion is approximately target + spread,
        # while the additional adverse excursion after entry is stop - spread.
        # Increase the stop buffer when the target would otherwise be far more
        # distant than the stop in market-price terms.
        maximum_barrier_asymmetry = float(
            scalping_settings.SCALPING_DEMO_MAX_BARRIER_ASYMMETRY
        )
        required_adverse_buffer = (target + spread_cost) / max(
            maximum_barrier_asymmetry, 1e-9
        )
        stop = max(stop, spread_cost + required_adverse_buffer)
        stop = min(maximum_stop, stop)
        target = max(target, stop * minimum_reward_risk)
        target = min(maximum_target, target)
        maximum_spread_target_ratio = float(
            scalping_settings.SCALPING_DEMO_MAX_SPREAD_TARGET_RATIO
        )
    else:
        base_target = float(scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD)
        maximum_target = float(scalping_settings.SCALPING_MAX_PROFIT_TARGET_USD)
        target = max(
            base_target,
            spread_cost * float(scalping_settings.SCALPING_TARGET_SPREAD_MULTIPLIER),
            atr_profit_capacity * float(scalping_settings.SCALPING_TARGET_ATR_PROFIT_RATIO),
        )
        if entry_path == "BREAKOUT_RETEST":
            target = max(
                target,
                atr_profit_capacity
                * float(scalping_settings.SCALPING_BREAKOUT_TARGET_ATR_PROFIT_RATIO),
            )

        minimum_stop = float(scalping_settings.SCALPING_MIN_STOP_LOSS_USD)
        maximum_stop = float(scalping_settings.SCALPING_MAX_STOP_LOSS_USD)
        stop = max(
            minimum_stop,
            atr_profit_capacity * float(scalping_settings.SCALPING_STOP_ATR_PROFIT_RATIO),
            spread_cost * float(scalping_settings.SCALPING_STOP_SPREAD_MULTIPLIER),
        )
        stop = min(maximum_stop, stop)
        minimum_reward_risk = float(scalping_settings.SCALPING_MIN_REWARD_RISK_RATIO)
        target = max(target, stop * minimum_reward_risk)
        target = min(maximum_target, target)
        maximum_spread_target_ratio = float(
            scalping_settings.SCALPING_MAX_SPREAD_TARGET_RATIO
        )
        maximum_barrier_asymmetry = 999.0

    reward_risk = target / max(stop, 1e-9)
    spread_target_ratio = spread_cost / max(target, 1e-9)
    adverse_excursion_after_spread = max(0.0, stop - spread_cost)
    favorable_excursion_after_spread = max(0.0, target + spread_cost)
    barrier_asymmetry = favorable_excursion_after_spread / max(
        adverse_excursion_after_spread, 1e-9
    )
    adverse_buffer_minimum = (
        max(
            float(scalping_settings.SCALPING_DEMO_STOP_MIN_ADVERSE_BUFFER_USD),
            atr_profit_capacity
            * float(scalping_settings.SCALPING_DEMO_STOP_ADVERSE_ATR_RATIO),
        )
        if controlled_demo
        else 0.0
    )

    return {
        "target_usd": round(target, 2),
        "stop_usd": round(stop, 2),
        "reward_risk_ratio": round(reward_risk, 4),
        "spread_cost_usd": round(spread_cost, 4),
        "spread_target_ratio": round(spread_target_ratio, 4),
        "atr_profit_capacity_usd": round(atr_profit_capacity, 4),
        "minimum_reward_risk_ratio": minimum_reward_risk,
        "reward_risk_ok": reward_risk + 1e-9 >= minimum_reward_risk,
        "spread_target_ok": spread_target_ratio <= maximum_spread_target_ratio + 1e-9,
        "controlled_demo_economics": controlled_demo,
        "adverse_excursion_after_spread_usd": round(adverse_excursion_after_spread, 4),
        "favorable_excursion_after_spread_usd": round(favorable_excursion_after_spread, 4),
        "barrier_asymmetry": round(barrier_asymmetry, 4),
        "maximum_barrier_asymmetry": maximum_barrier_asymmetry,
        "barrier_asymmetry_ok": barrier_asymmetry <= maximum_barrier_asymmetry + 1e-9,
        "adverse_buffer_minimum_usd": round(adverse_buffer_minimum, 4),
        "adverse_buffer_ok": (
            not controlled_demo
            or adverse_excursion_after_spread + 1e-9 >= adverse_buffer_minimum
        ),
    }


def _entry_quality_decision(
    *,
    direction: str,
    winner_score: float,
    other_score: float,
    snapshot: ScalpingSnapshotState,
    m1: dict[str, Any],
    trend_confirmation: dict[str, Any],
    playbook: dict[str, Any],
    mtf_alignment: dict[str, Any],
    structure: dict[str, Any],
    zones: dict[str, Any],
    regime: dict[str, Any],
    factor_model: dict[str, Any],
    verified_context: dict[str, Any],
    cross_market_context: dict[str, Any],
) -> dict[str, Any]:
    """Authorize only a defined XAUUSD price-action playbook.

    The score winner identifies the candidate direction. Entry timing must be
    a closed-candle pullback, breakout retest, range rejection, controlled
    continuation, or an adaptive live micro-break of a level established by
    completed candles. This avoids blind chasing while allowing strong aligned
    momentum to enter as soon as support or resistance actually gives way.
    """

    margin = float(winner_score) - float(other_score)
    opposite = "SELL" if direction == "BUY" else "BUY"
    trend_direction = str(trend_confirmation.get("trend_direction", "NEUTRAL"))
    three_closed_direction = str(playbook.get("three_closed_direction", "NEUTRAL"))
    pressure_direction = str(playbook.get("three_closed_pressure_direction", "NEUTRAL"))
    pressure_strength = _float(playbook.get("three_closed_pressure_strength", 0.0))
    trend_strength = _float(trend_confirmation.get("trend_strength", 0.0))
    regime_mode = str(regime.get("mode", "NO_TRADE"))
    regime_direction = str(regime.get("direction", "NEUTRAL"))
    structure_direction = str(structure.get("direction", "NEUTRAL"))

    context_sources = {
        "multi_timeframe": str(mtf_alignment.get("dominant_direction", "NEUTRAL")),
        "market_structure": structure_direction,
        "market_regime": regime_direction if regime_mode != "NO_TRADE" else "NEUTRAL",
        "verified_adx": str(verified_context.get("trend_direction", "NEUTRAL")),
        "factor_model": (
            str(factor_model.get("preferred_direction", "NEUTRAL"))
            if str(factor_model.get("status", "ERROR")) == "OK"
            and _float(factor_model.get("preferred_score", 0.0)) >= 25.0
            else "NEUTRAL"
        ),
        "cross_market": (
            str(cross_market_context.get("gold_bias", "NEUTRAL"))
            if str(cross_market_context.get("status", "ERROR")) == "OK"
            else "NEUTRAL"
        ),
    }
    support_sources = sorted(
        name for name, value in context_sources.items() if value == direction
    )
    opposition_sources = sorted(
        name for name, value in context_sources.items() if value == opposite
    )

    vwap_signed = _float(verified_context.get("vwap_distance_atr", 0.0))
    vwap_distance = abs(vwap_signed)
    ema_distance = abs(_float(m1.get("distance_fast_atr_ratio", 0.0)))
    relative_volume = _float(verified_context.get("relative_tick_volume", 0.0))
    liquidity = str(verified_context.get("liquidity_regime", "UNKNOWN"))
    rsi = _float(m1.get("rsi", 50.0), 50.0)
    adx = _float(verified_context.get("adx_m5", 0.0))
    spread_atr_ratio = float(snapshot.spread) / max(_float(m1.get("atr", 0.0)), 1e-9)
    near_support = bool(zones.get("near_support", False))
    near_resistance = bool(zones.get("near_resistance", False))
    bad_location = (direction == "BUY" and near_resistance) or (
        direction == "SELL" and near_support
    )

    micro_break_high = _float(playbook.get("micro_break_high", 0.0))
    micro_break_low = _float(playbook.get("micro_break_low", 0.0))
    live_close = _float(playbook.get("live_close", snapshot.mid), snapshot.mid)
    live_body_atr = _float(playbook.get("live_body_atr", 0.0))
    micro_buffer = float(scalping_settings.SCALPING_MICRO_BREAK_BUFFER_ATR) * max(
        _float(m1.get("atr", 0.0)), 1e-9
    )
    micro_buy = bool(
        live_close >= micro_break_high + micro_buffer
        and live_body_atr >= float(scalping_settings.SCALPING_MICRO_BREAK_MIN_LIVE_BODY_ATR)
    )
    micro_sell = bool(
        live_close <= micro_break_low - micro_buffer
        and live_body_atr <= -float(scalping_settings.SCALPING_MICRO_BREAK_MIN_LIVE_BODY_ATR)
    )
    micro_break_direction = "BUY" if micro_buy else "SELL" if micro_sell else "NEUTRAL"

    strong_cross_market_opposition = bool(
        context_sources["cross_market"] == opposite
        and abs(_float(cross_market_context.get("pressure_score", 0.0)))
        >= float(scalping_settings.SCALPING_STRONG_CROSS_MARKET_PRESSURE)
    )

    trend_pullback = bool(
        trend_direction == direction
        and str(playbook.get("trend_pullback_direction", "NEUTRAL")) == direction
        and three_closed_direction == direction
    )
    breakout_retest = bool(
        str(playbook.get("breakout_retest_direction", "NEUTRAL")) == direction
        and regime_mode in {"BREAKOUT", "TREND"}
        and regime_direction in {direction, "NEUTRAL"}
        and trend_direction in {direction, "NEUTRAL"}
    )
    micro_break_continuation = bool(
        micro_break_direction == direction
        and regime_mode in {"TREND", "BREAKOUT", "REVERSAL"}
        and regime_direction == direction
        and structure_direction in {direction, "NEUTRAL"}
        and str(mtf_alignment.get("dominant_direction", "NEUTRAL")) == direction
        and str(verified_context.get("trend_direction", "NEUTRAL")) in {direction, "NEUTRAL"}
        and (
            trend_direction in {direction, "NEUTRAL"}
            or trend_strength
            <= float(scalping_settings.SCALPING_MICRO_BREAK_MAX_OPPOSITE_TREND_STRENGTH)
        )
    )
    trend_continuation = bool(
        pressure_direction == direction
        and regime_mode in {"TREND", "BREAKOUT", "REVERSAL"}
        and regime_direction in {direction, "NEUTRAL"}
        and structure_direction in {direction, "NEUTRAL"}
        and str(mtf_alignment.get("dominant_direction", "NEUTRAL")) in {direction, "NEUTRAL"}
        and (
            trend_direction in {direction, "NEUTRAL"}
            or trend_strength
            <= float(scalping_settings.SCALPING_TREND_CONTINUATION_MAX_OPPOSITE_TREND_STRENGTH)
        )
        and not bad_location
    )

    range_rejection = bool(
        str(playbook.get("range_rejection_direction", "NEUTRAL")) == direction
        and regime_mode in {"RANGE", "NO_TRADE"}
        and trend_direction == "NEUTRAL"
        and (
            direction == "BUY" and near_support
            or direction == "SELL" and near_resistance
        )
        and adx <= float(scalping_settings.SCALPING_RANGE_MAX_ADX)
    )

    if trend_pullback:
        selected_path = "TREND_PULLBACK"
        minimum_score = float(scalping_settings.SCALPING_TREND_PULLBACK_MIN_SCORE)
        minimum_margin = float(scalping_settings.SCALPING_TREND_PULLBACK_MIN_MARGIN)
        minimum_support = int(scalping_settings.SCALPING_TREND_PULLBACK_MIN_SUPPORT)
        maximum_opposition = int(scalping_settings.SCALPING_TREND_PULLBACK_MAX_OPPOSITION)
        maximum_vwap = float(scalping_settings.SCALPING_TREND_PULLBACK_MAX_VWAP_ATR)
        maximum_ema = float(scalping_settings.SCALPING_TREND_PULLBACK_MAX_EMA_ATR)
        rsi_min, rsi_max = (
            (
                float(scalping_settings.SCALPING_TREND_PULLBACK_BUY_RSI_MIN),
                float(scalping_settings.SCALPING_TREND_PULLBACK_BUY_RSI_MAX),
            )
            if direction == "BUY"
            else (
                float(scalping_settings.SCALPING_TREND_PULLBACK_SELL_RSI_MIN),
                float(scalping_settings.SCALPING_TREND_PULLBACK_SELL_RSI_MAX),
            )
        )
        path_gates = {
            "playbook": True,
            "trend": trend_direction == direction,
            "three_closed_confirmation": three_closed_direction == direction,
            "location": not bad_location,
            "adx": adx >= float(scalping_settings.SCALPING_TREND_MIN_ADX),
        }
    elif breakout_retest:
        selected_path = "BREAKOUT_RETEST"
        minimum_score = float(scalping_settings.SCALPING_BREAKOUT_RETEST_MIN_SCORE)
        minimum_margin = float(scalping_settings.SCALPING_BREAKOUT_RETEST_MIN_MARGIN)
        minimum_support = int(scalping_settings.SCALPING_BREAKOUT_RETEST_MIN_SUPPORT)
        maximum_opposition = int(scalping_settings.SCALPING_BREAKOUT_RETEST_MAX_OPPOSITION)
        maximum_vwap = float(scalping_settings.SCALPING_BREAKOUT_RETEST_MAX_VWAP_ATR)
        maximum_ema = float(scalping_settings.SCALPING_BREAKOUT_RETEST_MAX_EMA_ATR)
        rsi_min, rsi_max = (
            (
                float(scalping_settings.SCALPING_BREAKOUT_RETEST_BUY_RSI_MIN),
                float(scalping_settings.SCALPING_BREAKOUT_RETEST_BUY_RSI_MAX),
            )
            if direction == "BUY"
            else (
                float(scalping_settings.SCALPING_BREAKOUT_RETEST_SELL_RSI_MIN),
                float(scalping_settings.SCALPING_BREAKOUT_RETEST_SELL_RSI_MAX),
            )
        )
        path_gates = {
            "playbook": True,
            "regime": regime_mode in {"BREAKOUT", "TREND"},
            "trend_not_opposite": trend_direction != opposite,
            "location": not bad_location,
            "adx": adx >= float(scalping_settings.SCALPING_BREAKOUT_MIN_ADX),
        }
    elif micro_break_continuation:
        selected_path = "MICRO_BREAK_CONTINUATION"
        minimum_score = float(scalping_settings.SCALPING_MICRO_BREAK_MIN_SCORE)
        minimum_margin = float(scalping_settings.SCALPING_MICRO_BREAK_MIN_MARGIN)
        minimum_support = int(scalping_settings.SCALPING_MICRO_BREAK_MIN_SUPPORT)
        maximum_opposition = int(scalping_settings.SCALPING_MICRO_BREAK_MAX_OPPOSITION)
        maximum_vwap = float(scalping_settings.SCALPING_MICRO_BREAK_MAX_VWAP_ATR)
        maximum_ema = float(scalping_settings.SCALPING_MICRO_BREAK_MAX_EMA_ATR)
        rsi_min, rsi_max = (
            (
                float(scalping_settings.SCALPING_MICRO_BREAK_BUY_RSI_MIN),
                float(scalping_settings.SCALPING_MICRO_BREAK_BUY_RSI_MAX),
            )
            if direction == "BUY"
            else (
                float(scalping_settings.SCALPING_MICRO_BREAK_SELL_RSI_MIN),
                float(scalping_settings.SCALPING_MICRO_BREAK_SELL_RSI_MAX),
            )
        )
        path_gates = {
            "playbook": True,
            "micro_break": micro_break_direction == direction,
            "live_body": abs(live_body_atr)
            >= float(scalping_settings.SCALPING_MICRO_BREAK_MIN_LIVE_BODY_ATR),
            "regime": regime_mode in {"TREND", "BREAKOUT", "REVERSAL"},
            "regime_direction": regime_direction == direction,
            "structure_direction": structure_direction in {direction, "NEUTRAL"},
            "mtf_direction": str(mtf_alignment.get("dominant_direction", "NEUTRAL")) == direction,
            "verified_adx_direction": str(verified_context.get("trend_direction", "NEUTRAL"))
            in {direction, "NEUTRAL"},
            "trend_not_strongly_opposite": (
                trend_direction in {direction, "NEUTRAL"}
                or trend_strength
                <= float(scalping_settings.SCALPING_MICRO_BREAK_MAX_OPPOSITE_TREND_STRENGTH)
            ),
            "adx": adx >= float(scalping_settings.SCALPING_MICRO_BREAK_MIN_ADX),
            "micro_volume": relative_volume
            >= float(scalping_settings.SCALPING_MICRO_BREAK_MIN_RELATIVE_VOLUME),
            "micro_spread": float(snapshot.spread)
            <= float(scalping_settings.SCALPING_MICRO_BREAK_MAX_SPREAD_USD),
            # A verified micro break resolves the local support/resistance veto.
            # The level must be broken first; merely being near it never passes.
            "location_break_confirmed": micro_break_direction == direction,
        }
    elif trend_continuation:
        selected_path = "TREND_CONTINUATION"
        minimum_score = float(scalping_settings.SCALPING_TREND_CONTINUATION_MIN_SCORE)
        minimum_margin = float(scalping_settings.SCALPING_TREND_CONTINUATION_MIN_MARGIN)
        minimum_support = int(scalping_settings.SCALPING_TREND_CONTINUATION_MIN_SUPPORT)
        maximum_opposition = int(scalping_settings.SCALPING_TREND_CONTINUATION_MAX_OPPOSITION)
        maximum_vwap = float(scalping_settings.SCALPING_TREND_CONTINUATION_MAX_VWAP_ATR)
        maximum_ema = float(scalping_settings.SCALPING_TREND_CONTINUATION_MAX_EMA_ATR)
        rsi_min, rsi_max = (
            (
                float(scalping_settings.SCALPING_TREND_CONTINUATION_BUY_RSI_MIN),
                float(scalping_settings.SCALPING_TREND_CONTINUATION_BUY_RSI_MAX),
            )
            if direction == "BUY"
            else (
                float(scalping_settings.SCALPING_TREND_CONTINUATION_SELL_RSI_MIN),
                float(scalping_settings.SCALPING_TREND_CONTINUATION_SELL_RSI_MAX),
            )
        )
        path_gates = {
            "playbook": True,
            "continuation_pressure": pressure_direction == direction,
            "pressure_strength": pressure_strength >= 0.50,
            "regime": regime_mode in {"TREND", "BREAKOUT", "REVERSAL"},
            "regime_direction": regime_direction in {direction, "NEUTRAL"},
            "structure_direction": structure_direction in {direction, "NEUTRAL"},
            "mtf_direction": str(mtf_alignment.get("dominant_direction", "NEUTRAL")) in {direction, "NEUTRAL"},
            "trend_not_strongly_opposite": (
                trend_direction in {direction, "NEUTRAL"}
                or trend_strength
                <= float(scalping_settings.SCALPING_TREND_CONTINUATION_MAX_OPPOSITE_TREND_STRENGTH)
            ),
            "location": not bad_location,
            "adx": adx >= float(scalping_settings.SCALPING_TREND_CONTINUATION_MIN_ADX),
            "continuation_volume": relative_volume
            >= float(scalping_settings.SCALPING_TREND_CONTINUATION_MIN_RELATIVE_VOLUME),
        }
    elif range_rejection:
        selected_path = "RANGE_REJECTION"
        minimum_score = float(scalping_settings.SCALPING_RANGE_REJECTION_MIN_SCORE)
        minimum_margin = float(scalping_settings.SCALPING_RANGE_REJECTION_MIN_MARGIN)
        minimum_support = int(scalping_settings.SCALPING_RANGE_REJECTION_MIN_SUPPORT)
        maximum_opposition = int(scalping_settings.SCALPING_RANGE_REJECTION_MAX_OPPOSITION)
        maximum_vwap = float(scalping_settings.SCALPING_RANGE_REJECTION_MAX_VWAP_ATR)
        maximum_ema = float(scalping_settings.SCALPING_RANGE_REJECTION_MAX_EMA_ATR)
        rsi_min, rsi_max = (
            (
                float(scalping_settings.SCALPING_RANGE_REJECTION_BUY_RSI_MIN),
                float(scalping_settings.SCALPING_RANGE_REJECTION_BUY_RSI_MAX),
            )
            if direction == "BUY"
            else (
                float(scalping_settings.SCALPING_RANGE_REJECTION_SELL_RSI_MIN),
                float(scalping_settings.SCALPING_RANGE_REJECTION_SELL_RSI_MAX),
            )
        )
        path_gates = {
            "playbook": True,
            "range_regime": regime_mode in {"RANGE", "NO_TRADE"},
            "zone": (
                direction == "BUY" and near_support
                or direction == "SELL" and near_resistance
            ),
            "low_adx": adx <= float(scalping_settings.SCALPING_RANGE_MAX_ADX),
        }
    else:
        selected_path = "NO_PLAYBOOK"
        minimum_score = float(scalping_settings.SCALPING_TREND_PULLBACK_MIN_SCORE)
        minimum_margin = float(scalping_settings.SCALPING_TREND_PULLBACK_MIN_MARGIN)
        minimum_support = int(scalping_settings.SCALPING_TREND_PULLBACK_MIN_SUPPORT)
        maximum_opposition = int(scalping_settings.SCALPING_TREND_PULLBACK_MAX_OPPOSITION)
        maximum_vwap = float(scalping_settings.SCALPING_TREND_PULLBACK_MAX_VWAP_ATR)
        maximum_ema = float(scalping_settings.SCALPING_TREND_PULLBACK_MAX_EMA_ATR)
        rsi_min, rsi_max = 0.0, 100.0
        path_gates = {
            "playbook": False,
            "trend_pullback": trend_pullback,
            "breakout_retest": breakout_retest,
            "micro_break_continuation": micro_break_continuation,
            "trend_continuation": trend_continuation,
            "range_rejection": range_rejection,
        }

    economics = _trade_economics(
        snapshot=snapshot,
        m1=m1,
        entry_path=selected_path,
    )
    common_gates = {
        "score": float(winner_score) >= minimum_score,
        "margin": margin >= minimum_margin,
        "context_support": len(support_sources) >= minimum_support,
        "context_opposition": len(opposition_sources) <= maximum_opposition,
        "cross_market_not_strongly_opposite": not strong_cross_market_opposition,
        "vwap_distance": vwap_distance <= maximum_vwap,
        "ema_distance": ema_distance <= maximum_ema,
        "relative_volume": relative_volume
        >= float(scalping_settings.SCALPING_PLAYBOOK_MIN_RELATIVE_VOLUME),
        "liquidity": liquidity in {"NORMAL", "HIGH"},
        "rsi": rsi_min <= rsi <= rsi_max,
        "spread_atr": spread_atr_ratio
        <= float(scalping_settings.SCALPING_MAX_SPREAD_ATR_RATIO),
        "reward_risk": bool(economics["reward_risk_ok"]),
        "spread_target": bool(economics["spread_target_ok"]),
        "adverse_buffer": bool(economics.get("adverse_buffer_ok", True)),
        "barrier_asymmetry": bool(economics.get("barrier_asymmetry_ok", True)),
    }
    gates = {**path_gates, **common_gates}
    failed = [name for name, passed in gates.items() if not passed]
    passed = selected_path != "NO_PLAYBOOK" and not failed

    return {
        "passed": passed,
        "mode": selected_path if passed else "QUALITY_WAIT",
        "selected_path": selected_path,
        "direction": direction,
        "winner_score": round(float(winner_score), 4),
        "other_score": round(float(other_score), 4),
        "margin": round(margin, 4),
        "minimum_score": minimum_score,
        "minimum_margin": minimum_margin,
        "support_votes": len(support_sources),
        "opposition_votes": len(opposition_sources),
        "support_sources": support_sources,
        "opposition_sources": opposition_sources,
        "context_sources": context_sources,
        "trend_direction": trend_direction,
        "three_closed_direction": three_closed_direction,
        "pressure_direction": pressure_direction,
        "pressure_strength": round(pressure_strength, 4),
        "micro_break_direction": micro_break_direction,
        "micro_break_high": round(micro_break_high, 6),
        "micro_break_low": round(micro_break_low, 6),
        "micro_break_buffer": round(micro_buffer, 6),
        "live_close": round(live_close, 6),
        "live_body_atr": round(live_body_atr, 4),
        "trend_strength": round(trend_strength, 4),
        "vwap_distance_atr": round(vwap_distance, 4),
        "ema_distance_atr": round(ema_distance, 4),
        "relative_volume": round(relative_volume, 4),
        "liquidity_regime": liquidity,
        "rsi": round(rsi, 4),
        "adx_m5": round(adx, 4),
        "spread_atr_ratio": round(spread_atr_ratio, 4),
        "near_support": near_support,
        "near_resistance": near_resistance,
        "economics": economics,
        "gates": gates,
        "failed_gates": failed,
    }

def build_unified_scalp_signal(snapshot: ScalpingSnapshotState, base: ScalpSignalState, news_context: dict[str, Any] | None = None) -> ScalpSignalState:
    analysis_started = perf_counter()
    signal_timing_ms: dict[str, float] = {}
    news = news_context or {}
    reasons: list[str] = []
    blocks: list[str] = []
    if news.get("hard_block"):
        blocks.extend(news.get("block_reasons", ["Unified news protection blocked trading."]))
    hard_spread_limit = hard_entry_spread_limit_usd()
    if spread_exceeds(snapshot.spread, hard_spread_limit):
        blocks.append(
            f"Spread exceeds the absolute scalping entry limit: "
            f"{snapshot.spread:.3f} > {hard_spread_limit:.3f}."
        )
    elif spread_exceeds(snapshot.spread, float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD)):
        reasons.append(
            f"Elevated spread {snapshot.spread:.3f} requires adaptive score-margin economics; "
            f"normal limit={scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD:.3f}, "
            f"hard limit={hard_spread_limit:.3f}."
        )

    try:
        phase_started = perf_counter()
        frames = {name: _frame(data, name) for name, data in snapshot.candles.items() if data is not None}
        signal_timing_ms["frame_validation"] = (perf_counter() - phase_started) * 1000.0
        m1_frame, m5_frame, m15_frame = frames["M1"], frames["M5"], frames["M15"]
        h1_frame = frames.get("H1", m15_frame)
        h4_frame = frames.get("H4", h1_frame)
        cache_details = getattr(snapshot, "candle_cache_details", {}) or {}
        phase_started = perf_counter()
        diagnostics = {
            "M1": _frame_diagnostic(m1_frame, "M1", cache_record=cache_details.get("M1"), reference_time=snapshot.timestamp),
            "M5": _frame_diagnostic(m5_frame, "M5", cache_record=cache_details.get("M5"), reference_time=snapshot.timestamp),
            "M15": _frame_diagnostic(m15_frame, "M15", cache_record=cache_details.get("M15"), reference_time=snapshot.timestamp),
            "H1": _frame_diagnostic(
                h1_frame,
                "H1",
                "H1" if "H1" in frames else "M15_FALLBACK",
                cache_details.get("H1"),
                snapshot.timestamp,
            ),
            "H4": _frame_diagnostic(
                h4_frame,
                "H4",
                "H4" if "H4" in frames else "H1_FALLBACK",
                cache_details.get("H4"),
                snapshot.timestamp,
            ),
        }
        signal_timing_ms["candle_diagnostics"] = (perf_counter() - phase_started) * 1000.0
        phase_started = perf_counter()
        m1 = _metrics(m1_frame, "M1")
        m1_live = _live_trigger_metrics(m1_frame, m1)
        m5, m15 = _metrics(m5_frame, "M5"), _metrics(m15_frame, "M15")
        h1, h4 = _metrics(h1_frame, "H1"), _metrics(h4_frame, "H4")
        mtf_alignment = _multi_timeframe_alignment(m5, m15, h1, h4)
        trend_confirmation = analyze_m1_trend_confirmation(
            m1_frame, atr=m1["atr"]
        )
        playbook = analyze_scalp_playbooks(
            m1_frame,
            atr=m1["atr"],
            micro_break_lookback=int(scalping_settings.SCALPING_MICRO_BREAK_LOOKBACK_CANDLES),
        )
        signal_timing_ms["indicator_metrics"] = (perf_counter() - phase_started) * 1000.0
        phase_started = perf_counter()
        m15_context_key = _closed_context_key(m15_frame, "M15")
        m5_context_key = _closed_context_key(m5_frame, "M5")
        structure = _cached_context(
            _STRUCTURE_CACHE,
            ("structure",) + m15_context_key,
            lambda: _structure(m15_frame, m15["close"]),
        )
        zones = _cached_context(
            _ZONE_CACHE,
            ("zones",) + m15_context_key,
            lambda: _zones(m15_frame, m15["close"], m15["atr"]),
        )
        order_blocks = _cached_context(
            _ORDER_BLOCK_CACHE,
            ("order_blocks",) + m5_context_key,
            lambda: _order_blocks(m5_frame, m5["close"]),
        )
        regime = _regime(m5, m15, h1, h4, structure)
        signal_timing_ms["structure_zone_regime"] = (perf_counter() - phase_started) * 1000.0
        phase_started = perf_counter()
        factor_model = build_atome_factor_model(snapshot, base)
        signal_timing_ms["factor_model"] = (perf_counter() - phase_started) * 1000.0
        phase_started = perf_counter()
        verified_context = build_verified_market_context(snapshot)
        signal_timing_ms["verified_context"] = (perf_counter() - phase_started) * 1000.0
        phase_started = perf_counter()
        cross_market_context = build_cross_market_context()
        signal_timing_ms["cross_market_context"] = (perf_counter() - phase_started) * 1000.0
    except Exception as error:
        return ScalpSignalState(
            action="WAIT", direction="NONE", allowed=False, score=0.0, confidence=0.0,
            target_profit_usd=0.0, stop_loss_usd=0.0, signal_key="", pattern="NONE",
            metrics={"data_quality": {"valid": False, "error": f"{type(error).__name__}: {error}"}, "signal_timing_ms": signal_timing_ms},
            reasons=[], block_reasons=[f"Unified analysis failed: {type(error).__name__}: {error}"],
        )

    metrics: dict[str, Any] = {
        "M1": m1, "M1_live": m1_live, "M5": m5, "M15": m15, "H1": h1, "H4": h4,
        "structure": structure, "zones": zones, "order_blocks": order_blocks, "regime": regime,
        "factor_model": factor_model, "verified_context": verified_context,
        "cross_market_context": cross_market_context,
        "multi_timeframe_alignment": mtf_alignment,
        "trend_confirmation": trend_confirmation,
        "playbook": playbook,
        "signal_timing_ms": signal_timing_ms,
        "news_context": news, "data_quality": diagnostics,
        "clock_diagnostics": {
            "market_clock_source": getattr(snapshot, "market_clock_source", "SYSTEM_UTC"),
            "market_clock_time": snapshot.timestamp.isoformat() if snapshot.timestamp else "",
            "system_clock_time": getattr(snapshot, "system_timestamp", None).isoformat() if getattr(snapshot, "system_timestamp", None) else "",
            "market_clock_offset_seconds": round(float(getattr(snapshot, "market_clock_offset_seconds", 0.0) or 0.0), 3),
        },
    }

    if factor_model.get("status") != "OK" and bool(scalping_settings.SCALPING_UNIFIED_REQUIRE_FACTOR_ENGINE):
        blocks.append(f"Unified factor engine is not healthy: {factor_model.get('status')} {factor_model.get('error', '')}".strip())

    if bool(getattr(scalping_settings, "SCALPING_VERIFIED_MARKET_CONTEXT_ENABLED", True)):
        verified_status = str(verified_context.get("status", "ERROR"))
        verified_quality = _float(verified_context.get("data_quality_score", 0.0))
        if bool(getattr(scalping_settings, "SCALPING_VERIFIED_MARKET_CONTEXT_REQUIRED", True)) and verified_status != "OK":
            blocks.append(f"Verified market context is unavailable: {verified_status} {verified_context.get('error', '')}".strip())
        minimum_quality = float(getattr(scalping_settings, "SCALPING_VERIFIED_MIN_DATA_QUALITY_SCORE", 0.75))
        if verified_status == "OK" and verified_quality < minimum_quality:
            blocks.append(f"Verified market-data quality is too low: {verified_quality:.2f} < {minimum_quality:.2f}.")

    m1_age = diagnostics["M1"].get("live_data_age_seconds")
    if m1_age is not None and m1_age > float(scalping_settings.SCALPING_UNIFIED_MAX_M1_DATA_AGE_SECONDS):
        blocks.append(f"M1 market data is stale: {m1_age:.1f}s > {scalping_settings.SCALPING_UNIFIED_MAX_M1_DATA_AGE_SECONDS:.1f}s.")

    phase_started = perf_counter()
    buy_score, buy_components, buy_reasons, buy_pattern, buy_trigger, buy_families = _score_direction("BUY", snapshot, base, metrics, news)
    sell_score, sell_components, sell_reasons, sell_pattern, sell_trigger, sell_families = _score_direction("SELL", snapshot, base, metrics, news)
    signal_timing_ms["direction_scoring"] = (perf_counter() - phase_started) * 1000.0

    if buy_score >= sell_score:
        direction, score, other = "BUY", buy_score, sell_score
        direction_reasons, pattern, trigger_ok, selected_families = buy_reasons, buy_pattern, buy_trigger, buy_families
    else:
        direction, score, other = "SELL", sell_score, buy_score
        direction_reasons, pattern, trigger_ok, selected_families = sell_reasons, sell_pattern, sell_trigger, sell_families
    reasons.extend(direction_reasons)

    minimum_score = float(scalping_settings.SCALPING_UNIFIED_MIN_ENTRY_SCORE)
    if snapshot.session == "Asian":
        minimum_score = max(minimum_score, float(scalping_settings.SCALPING_UNIFIED_ASIAN_MIN_SCORE))
        if (
            not bool(getattr(scalping_settings, "SCALPING_DIRECT_SCORE_PAPER_ENABLED", False) and (scalping_settings.SCALPING_PAPER_ONLY or getattr(scalping_settings, "SCALPING_DEMO_EXECUTION_ENABLED", False)))
            and spread_exceeds(snapshot.spread, float(scalping_settings.SCALPING_UNIFIED_ASIAN_MAX_SPREAD_USD))
        ):
            blocks.append(
                f"Asian-session spread exceeds the stricter unified limit: {snapshot.spread:.3f} > {scalping_settings.SCALPING_UNIFIED_ASIAN_MAX_SPREAD_USD:.3f}."
            )

    family_count = len(selected_families)
    minimum_families = int(scalping_settings.SCALPING_UNIFIED_MIN_CONFIRMING_FAMILIES)
    entry_trigger_family_present = "entry_trigger" in selected_families
    configured_context_families = set(
        getattr(
            scalping_settings,
            "SCALPING_UNIFIED_DIRECTIONAL_CONTEXT_FAMILIES",
            ("multi_timeframe", "market_structure", "market_regime", "location"),
        )
    )
    matching_context_families = sorted(configured_context_families.intersection(selected_families))
    directional_context_family_present = bool(matching_context_families)

    selected_vwap_distance = _float(verified_context.get("vwap_distance_atr", 0.0))
    max_entry_vwap_distance = float(
        getattr(scalping_settings, "SCALPING_UNIFIED_MAX_ENTRY_VWAP_DISTANCE_ATR", 2.50)
    )
    vwap_overextended = (
        direction == "BUY" and selected_vwap_distance > max_entry_vwap_distance
    ) or (
        direction == "SELL" and selected_vwap_distance < -max_entry_vwap_distance
    )

    direction_margin = score - other
    direct_score_decision = _direct_score_decision(
        buy_score=buy_score,
        sell_score=sell_score,
    )
    direct_mode_enabled = bool(
        getattr(scalping_settings, "SCALPING_DIRECT_SCORE_PAPER_ENABLED", False)
        and (
            scalping_settings.SCALPING_PAPER_ONLY
            or (
                getattr(scalping_settings, "SCALPING_DEMO_EXECUTION_ENABLED", False)
                and not getattr(scalping_settings, "SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED", False)
            )
        )
    )

    entry_quality_decision = _entry_quality_decision(
        direction=str(direct_score_decision["winner_direction"]),
        winner_score=float(direct_score_decision["winner_score"]),
        other_score=float(direct_score_decision["other_score"]),
        snapshot=snapshot,
        m1=m1,
        trend_confirmation=trend_confirmation,
        playbook=playbook,
        mtf_alignment=mtf_alignment,
        structure=structure,
        zones=zones,
        regime=regime,
        factor_model=factor_model,
        verified_context=verified_context,
        cross_market_context=cross_market_context,
    ) if direct_score_decision["winner_direction"] in {"BUY", "SELL"} else {
        "passed": False,
        "mode": "QUALITY_WAIT",
        "direction": "NONE",
        "failed_gates": ["exact_tie"],
        "gates": {},
    }

    if direct_score_decision["passed"]:
        direction = str(direct_score_decision["winner_direction"])
        if direction == "BUY":
            score, other = buy_score, sell_score
            direction_reasons = buy_reasons
            selected_families = list(buy_families)
        else:
            score, other = sell_score, buy_score
            direction_reasons = sell_reasons
            selected_families = list(sell_families)
        direction_margin = score - other
        pattern = (
            str(entry_quality_decision.get("mode"))
            if entry_quality_decision.get("passed")
            and entry_quality_decision.get("mode") != "QUALITY_DISABLED"
            else "DIRECT_SCORE"
        )
        trigger_ok = bool(entry_quality_decision.get("passed"))
        family_count = len(selected_families)
        entry_trigger_family_present = "entry_trigger" in selected_families
        matching_context_families = sorted(configured_context_families.intersection(selected_families))
        directional_context_family_present = bool(matching_context_families)
        reasons = list(direction_reasons) + [
            f"Score winner selected {direction}: BUY={buy_score:.1f}, SELL={sell_score:.1f}."
        ]
        if entry_quality_decision.get("passed"):
            quality_mode = str(entry_quality_decision.get("mode", "QUALITY"))
            reasons.append(
                f"{quality_mode} accepted {direction}; "
                f"context support={entry_quality_decision.get('support_votes', 0)}, "
                f"opposition={entry_quality_decision.get('opposition_votes', 0)}."
            )

    score_acceptance = _score_acceptance(
        score=score,
        minimum_score=minimum_score,
        direction=direction,
        direction_margin=direction_margin,
        minimum_direction_margin=float(scalping_settings.SCALPING_DIRECTION_TIE_MARGIN),
        family_count=family_count,
        minimum_families=minimum_families,
        entry_trigger_present=entry_trigger_family_present,
        directional_context_present=directional_context_family_present,
        regime=regime,
        verified_context=verified_context,
        vwap_overextended=vwap_overextended,
    )

    if direct_mode_enabled:
        # The user's paper-mode policy is deliberately simple: the strictly
        # higher unified score chooses the direction. All strategy-quality
        # gates below are diagnostics only in this mode. Hard operational
        # safety blocks are collected separately and remain active.
        if not direct_score_decision["passed"]:
            if direct_score_decision["mode"] == "TIE_WAIT":
                blocks.append(
                    f"BUY and SELL unified scores are exactly tied: "
                    f"{buy_score:.1f} versus {sell_score:.1f}."
                )
            elif direct_score_decision["mode"] == "WEAK_SCORE_WAIT":
                blocks.append(
                    f"Winning unified score is below the quality floor: "
                    f"{direct_score_decision['winner_score']:.1f} < "
                    f"{direct_score_decision['minimum_winner_score']:.1f}."
                )
            else:
                blocks.append("Score-winner paper decision is disabled.")
        elif not entry_quality_decision.get("passed", False):
            failed = list(entry_quality_decision.get("failed_gates", []))
            blocks.append(
                "Regime-playbook quality gate failed: "
                + ", ".join(failed)
                + "."
            )
    else:
        if not score_acceptance["passed"]:
            blocks.append(f"Unified score is below minimum: {score:.1f} < {minimum_score:.1f}.")
        elif score_acceptance["borderline_pass"]:
            reasons.append(
                f"Strict borderline acceptance applied: score shortfall "
                f"{score_acceptance['shortfall']:.2f} <= {score_acceptance['tolerance']:.2f}; "
                "entry trigger, directional context, regime, data completeness, family count, and direction margin all passed."
            )
        if direction_margin < float(scalping_settings.SCALPING_DIRECTION_TIE_MARGIN):
            blocks.append(f"BUY and SELL unified scores are too close: {buy_score:.1f} versus {sell_score:.1f}.")
        if family_count < minimum_families:
            blocks.append(f"Only {family_count} confirming families support {direction}; {minimum_families} required.")
        if bool(getattr(scalping_settings, "SCALPING_UNIFIED_REQUIRE_ENTRY_TRIGGER_FAMILY", True)) and not entry_trigger_family_present:
            blocks.append("The required entry-trigger family is missing; momentum and context alone cannot authorize a trade.")
        if bool(getattr(scalping_settings, "SCALPING_UNIFIED_REQUIRE_DIRECTIONAL_CONTEXT_FAMILY", True)) and not directional_context_family_present:
            blocks.append("The required directional-context family is missing; an entry trigger cannot trade without trend, structure, regime, or location support.")
        if not trigger_ok:
            blocks.append("No breakout, pullback/reclaim, candle rejection, or structure entry trigger exists.")
        if (
            bool(scalping_settings.SCALPING_UNIFIED_REQUIRE_RESOLVED_REGIME)
            and regime["mode"] == "NO_TRADE"
        ):
            blocks.append(f"Market regime is unresolved or conflicting: {regime['reason']}")

    for item in base.block_reasons:
        text = item.lower()
        if direct_mode_enabled:
            if "spread exceeds" in text or "candles are missing" in text:
                blocks.append(item)
        elif any(token in text for token in ("spread exceeds", "atr is outside", "candles are missing", "session")):
            blocks.append(item)

    score_diagnostics = {
        "version": scalping_settings.SCALPING_UNIFIED_SCORE_COMPONENT_VERSION,
        "selected_direction": direction,
        "minimum_score": minimum_score,
        "direction_margin": round(direction_margin, 2),
        "minimum_direction_margin": float(scalping_settings.SCALPING_DIRECTION_TIE_MARGIN),
        "confirming_families": selected_families,
        "confirming_family_count": family_count,
        "minimum_confirming_families": minimum_families,
        "entry_trigger_family_present": entry_trigger_family_present,
        "entry_trigger_family_required": bool(getattr(scalping_settings, "SCALPING_UNIFIED_REQUIRE_ENTRY_TRIGGER_FAMILY", True)),
        "directional_context_family_present": directional_context_family_present,
        "directional_context_family_required": bool(getattr(scalping_settings, "SCALPING_UNIFIED_REQUIRE_DIRECTIONAL_CONTEXT_FAMILY", True)),
        "matching_directional_context_families": matching_context_families,
        "selected_pattern": pattern,
        "score_shortfall": round(max(0.0, minimum_score - score), 2),
        "score_authorization_mode": direct_score_decision["mode"] if direct_mode_enabled else score_acceptance["mode"],
        "score_raw_pass": score_acceptance["raw_pass"],
        "direct_score_decision": direct_score_decision,
        "direct_score_accepted": direct_score_decision["passed"],
        "entry_quality_decision": entry_quality_decision,
        "trend_confirmation": trend_confirmation,
        "playbook": playbook,
        "score_borderline_accepted": score_acceptance["borderline_pass"],
        "score_threshold_tolerance": score_acceptance["tolerance"],
        "score_borderline_required_families": score_acceptance["required_families"],
        "score_borderline_required_direction_margin": score_acceptance["required_direction_margin"],
        "score_borderline_min_data_completeness": score_acceptance["minimum_data_completeness"],
        "selected_vwap_distance_atr": round(selected_vwap_distance, 3),
        "max_entry_vwap_distance_atr": max_entry_vwap_distance,
        "vwap_overextended": vwap_overextended,
        "buy_components": buy_components,
        "sell_components": sell_components,
        "buy_positive_total": round(sum(value for value in buy_components.values() if value > 0), 2),
        "sell_positive_total": round(sum(value for value in sell_components.values() if value > 0), 2),
        "buy_penalties": round(sum(value for value in buy_components.values() if value < 0), 2),
        "sell_penalties": round(sum(value for value in sell_components.values() if value < 0), 2),
        "maximum_possible_score": 100.0,
        "multi_timeframe_alignment": mtf_alignment,
    }
    signal_timing_ms["total"] = (perf_counter() - analysis_started) * 1000.0
    metrics.update({
        "buy_score": round(buy_score, 2), "sell_score": round(sell_score, 2),
        "buy_components": buy_components, "sell_components": sell_components,
        "buy_confirming_families": buy_families, "sell_confirming_families": sell_families,
        "score_diagnostics": score_diagnostics,
    })

    # Preserve the score-winning technical candidate and its adaptive economics
    # even when the closed-candle playbook returns WAIT. V5.0.2 needs these
    # values to evaluate a distinct tick-confirmed continuation path. Operational
    # blocks (news, stale data, spread, provider failure) remain in block_reasons
    # and can never be bypassed by the meta-controller.
    economics = entry_quality_decision.get("economics", {})
    target = _float(
        economics.get("target_usd"),
        float(scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD),
    )
    stop = _float(
        economics.get("stop_usd"),
        float(scalping_settings.SCALPING_MIN_STOP_LOSS_USD),
    )
    bucket = round(snapshot.mid / max(0.01, float(scalping_settings.SCALPING_SIGNAL_PRICE_BUCKET_USD)))
    candle_time = m1_live["candle_time"] or snapshot.timestamp
    component_version = str(
        getattr(scalping_settings, "SCALPING_UNIFIED_SCORE_COMPONENT_VERSION", "V5.0.2")
    )
    candidate_pattern = (
        str(entry_quality_decision.get("selected_path", "DIRECT_SCORE"))
        if str(entry_quality_decision.get("selected_path", "NO_PLAYBOOK")) != "NO_PLAYBOOK"
        else "DIRECT_SCORE"
    )
    key = f"{component_version}|{direction}|{candidate_pattern}|{candle_time.strftime('%Y%m%d%H%M%S')}|{bucket}"
    metrics["technical_candidate"] = {
        "direction": direction if direct_score_decision.get("passed") else "NONE",
        "score": round(score, 4),
        "other_score": round(other, 4),
        "margin": round(direction_margin, 4),
        "target_usd": round(target, 4),
        "stop_usd": round(stop, 4),
        "signal_key": key,
        "candidate_pattern": candidate_pattern,
        "native_playbook_allowed": bool(entry_quality_decision.get("passed", False)),
    }

    if blocks:
        candidate_direction = direction if direct_score_decision.get("passed") else "NONE"
        return ScalpSignalState(
            action="WAIT", direction=candidate_direction, allowed=False, score=round(score, 2), confidence=round(score / 100.0, 4),
            target_profit_usd=round(target, 2), stop_loss_usd=round(stop, 2), signal_key=key, pattern=candidate_pattern, metrics=metrics,
            reasons=reasons, block_reasons=list(dict.fromkeys(blocks)),
        )
    return ScalpSignalState(
        action=direction, direction=direction, allowed=True, score=round(score, 2), confidence=round(score / 100.0, 4),
        target_profit_usd=round(target, 2), stop_loss_usd=round(stop, 2), signal_key=key, pattern=pattern,
        metrics=metrics, reasons=reasons, block_reasons=[],
    )
