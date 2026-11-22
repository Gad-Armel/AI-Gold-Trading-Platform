from __future__ import annotations

"""Verified, broker-derived market context for the unified scalper.

Only real MT5 candle fields are used. Missing data never falls back to synthetic
prices or hard-coded market values. Tick-volume statistics are explicitly
labelled as proxies rather than true exchange order flow.
"""

from typing import Any
import math
import time
import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState
from services.market_data.spread_utils import spread_exceeds

_CONTEXT_CACHE: dict[str, Any] = {"key": None, "loaded_at": 0.0, "core": None}


def clear_verified_market_context_cache() -> None:
    _CONTEXT_CACHE.update({"key": None, "loaded_at": 0.0, "core": None})


def _frame(data: Any, name: str) -> pd.DataFrame:
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")
    for col in ("open", "high", "low", "close", "tick_volume"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)
    if len(frame) < max(55, int(scalping_settings.SCALPING_MIN_REQUIRED_CANDLES)):
        raise ValueError(f"{name} has insufficient valid candles: {len(frame)}")
    return frame


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    tr = pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def _adx(frame: pd.DataFrame, period: int = 14) -> tuple[float, float, float]:
    high = frame["high"]
    low = frame["low"]
    close = frame["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr = _atr(frame, period).replace(0.0, float("nan"))
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, float("nan"))
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return float(adx.iloc[-2] if len(adx) > 1 else adx.iloc[-1]), float(plus_di.iloc[-2]), float(minus_di.iloc[-2])


def _previous_day_pivots(m15: pd.DataFrame) -> dict[str, Any]:
    closed = m15.iloc[:-1].copy()
    closed["date"] = pd.to_datetime(closed["time"]).dt.date
    dates = sorted(closed["date"].dropna().unique())
    if len(dates) < 2:
        return {"status": "INSUFFICIENT_HISTORY"}
    previous_date = dates[-2]
    day = closed[closed["date"] == previous_date]
    if day.empty:
        return {"status": "INSUFFICIENT_HISTORY"}
    high = float(day["high"].max())
    low = float(day["low"].min())
    close = float(day.iloc[-1]["close"])
    pp = (high + low + close) / 3.0
    return {
        "status": "OK",
        "date": str(previous_date),
        "high": high,
        "low": low,
        "close": close,
        "PP": pp,
        "R1": 2.0 * pp - low,
        "R2": pp + (high - low),
        "S1": 2.0 * pp - high,
        "S2": pp - (high - low),
    }


def _raw_closed_signature(data: Any, name: str) -> tuple[Any, ...]:
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if len(frame) < 2:
        return (name, len(frame), "")
    row = frame.iloc[-2]
    return (
        name,
        len(frame),
        str(row.get("time", "")),
        round(float(row.get("open", 0.0)), 8),
        round(float(row.get("high", 0.0)), 8),
        round(float(row.get("low", 0.0)), 8),
        round(float(row.get("close", 0.0)), 8),
        round(float(row.get("tick_volume", 0.0) or 0.0), 4),
    )


def _cache_key(snapshot: ScalpingSnapshotState) -> tuple[Any, ...]:
    return (
        _raw_closed_signature(snapshot.candles.get("M1"), "M1"),
        _raw_closed_signature(snapshot.candles.get("M5"), "M5"),
        _raw_closed_signature(snapshot.candles.get("M15"), "M15"),
        int(getattr(scalping_settings, "SCALPING_VERIFIED_VOLUME_LOOKBACK", 20)),
        int(getattr(scalping_settings, "SCALPING_VERIFIED_DELTA_PROXY_LOOKBACK", 10)),
        int(getattr(scalping_settings, "SCALPING_VERIFIED_VWAP_LOOKBACK", 120)),
    )


def build_verified_market_context(snapshot: ScalpingSnapshotState) -> dict[str, Any]:
    calculation_started = time.perf_counter()
    try:
        key = _cache_key(snapshot)
        now = time.monotonic()
        cache_hit = key == _CONTEXT_CACHE.get("key") and _CONTEXT_CACHE.get("core") is not None
        if cache_hit:
            core = dict(_CONTEXT_CACHE["core"])
        else:
            m1 = _frame(snapshot.candles.get("M1"), "M1")
            m5 = _frame(snapshot.candles.get("M5"), "M5")
            m15 = _frame(snapshot.candles.get("M15"), "M15")
            closed_m1 = m1.iloc[:-1].copy()
            if "tick_volume" not in closed_m1.columns or closed_m1["tick_volume"].dropna().empty:
                raise ValueError("M1 tick_volume is unavailable.")

            volume = closed_m1["tick_volume"].fillna(0.0).clip(lower=0.0)
            lookback = max(10, int(getattr(scalping_settings, "SCALPING_VERIFIED_VOLUME_LOOKBACK", 20)))
            baseline = volume.iloc[-(lookback + 1):-1]
            current_volume = float(volume.iloc[-1])
            baseline_median = float(baseline.median()) if not baseline.empty else 0.0
            relative_volume = current_volume / baseline_median if baseline_median > 0 else 1.0

            proxy_lookback = max(5, int(getattr(scalping_settings, "SCALPING_VERIFIED_DELTA_PROXY_LOOKBACK", 10)))
            proxy_frame = closed_m1.tail(proxy_lookback)
            signed = (proxy_frame["close"] - proxy_frame["open"]).apply(lambda x: 1.0 if x > 0 else -1.0 if x < 0 else 0.0)
            total_proxy_volume = float(proxy_frame["tick_volume"].clip(lower=0.0).sum())
            signed_volume_proxy = float((signed * proxy_frame["tick_volume"].clip(lower=0.0)).sum()) / total_proxy_volume if total_proxy_volume > 0 else 0.0

            vwap_lookback = max(30, int(getattr(scalping_settings, "SCALPING_VERIFIED_VWAP_LOOKBACK", 120)))
            vwap_frame = closed_m1.tail(vwap_lookback)
            typical = (vwap_frame["high"] + vwap_frame["low"] + vwap_frame["close"]) / 3.0
            vwap_volume = vwap_frame["tick_volume"].clip(lower=0.0)
            volume_sum = float(vwap_volume.sum())
            rolling_vwap = float((typical * vwap_volume).sum() / volume_sum) if volume_sum > 0 else float(vwap_frame["close"].mean())
            atr_m1 = float(_atr(m1).iloc[-2])
            current_close = float(closed_m1.iloc[-1]["close"])
            vwap_distance_atr = (current_close - rolling_vwap) / atr_m1 if atr_m1 > 0 else 0.0

            adx, plus_di, minus_di = _adx(m5)
            trend_direction = "BUY" if plus_di > minus_di else "SELL" if minus_di > plus_di else "NEUTRAL"
            trend_regime = "STRONG" if adx >= 30 else "TRENDING" if adx >= 22 else "WEAK"

            pivots = _previous_day_pivots(m15)
            nearest_pivot = ""
            nearest_pivot_distance_atr = None
            if pivots.get("status") == "OK" and atr_m1 > 0:
                names = ("PP", "R1", "R2", "S1", "S2")
                nearest_pivot = min(names, key=lambda item: abs(current_close - float(pivots[item])))
                nearest_pivot_distance_atr = abs(current_close - float(pivots[nearest_pivot])) / atr_m1

            core = {
                "relative_tick_volume": round(relative_volume, 4),
                "current_tick_volume": current_volume,
                "baseline_tick_volume_median": round(baseline_median, 4),
                "signed_tick_volume_proxy": round(max(-1.0, min(1.0, signed_volume_proxy)), 4),
                "proxy_disclaimer": "Candle-direction weighted MT5 tick volume; not true exchange order-flow delta.",
                "rolling_vwap": round(rolling_vwap, 6),
                "vwap_distance_atr": round(vwap_distance_atr, 4),
                "adx_m5": round(adx, 4),
                "plus_di_m5": round(plus_di, 4),
                "minus_di_m5": round(minus_di, 4),
                "trend_direction": trend_direction,
                "trend_regime": trend_regime,
                "previous_day_pivots": pivots,
                "nearest_pivot": nearest_pivot,
                "nearest_pivot_distance_atr": round(nearest_pivot_distance_atr, 4) if nearest_pivot_distance_atr is not None else None,
            }
            _CONTEXT_CACHE.update({"key": key, "loaded_at": now, "core": dict(core)})

        relative_volume = float(core.get("relative_tick_volume", 1.0))
        session_limit = float(
            scalping_settings.SCALPING_UNIFIED_ASIAN_MAX_SPREAD_USD
            if snapshot.session == "Asian"
            else scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD
        )
        if spread_exceeds(snapshot.spread, session_limit) or relative_volume < 0.55:
            liquidity_regime = "LOW"
        elif snapshot.spread <= session_limit * 0.70 and relative_volume >= 1.20:
            liquidity_regime = "HIGH"
        else:
            liquidity_regime = "NORMAL"

        cache = getattr(snapshot, "candle_cache_details", {}) or {}
        fetch_errors = [str((cache.get(tf) or {}).get("last_fetch_error", "")) for tf in ("M1", "M5", "M15", "H1", "H4")]
        pivots = core.get("previous_day_pivots", {})
        finite_values = (
            float(core.get("relative_tick_volume", 0.0)),
            float(core.get("signed_tick_volume_proxy", 0.0)),
            float(core.get("rolling_vwap", 0.0)),
            float(core.get("adx_m5", 0.0)),
        )
        quality_parts = {
            "bars": 1.0,
            "tick_volume": 1.0 if float(core.get("baseline_tick_volume_median", 0.0)) > 0 else 0.0,
            "fresh_cache": 1.0 if not any(fetch_errors) else 0.5,
            "finite_metrics": 1.0 if all(math.isfinite(v) for v in finite_values) else 0.0,
            "pivot_history": 1.0 if pivots.get("status") == "OK" else 0.5,
        }
        completeness_score = sum(quality_parts.values()) / len(quality_parts)
        result = {
            "status": "OK",
            "data_quality_score": round(completeness_score, 4),
            "data_completeness_score": round(completeness_score, 4),
            "quality_components": quality_parts,
            **core,
            "liquidity_regime": liquidity_regime,
            "cache_hit": cache_hit,
            "cache_age_seconds": round(now - float(_CONTEXT_CACHE.get("loaded_at", now)), 3),
        }
        result["calculation_duration_ms"] = round((time.perf_counter() - calculation_started) * 1000.0, 3)
        return result
    except Exception as error:
        return {
            "status": "ERROR",
            "data_quality_score": 0.0,
            "data_completeness_score": 0.0,
            "cache_hit": False,
            "calculation_duration_ms": round((time.perf_counter() - calculation_started) * 1000.0, 3),
            "error": f"{type(error).__name__}: {error}",
        }
