from __future__ import annotations

"""Optional MT5-derived USD pressure context.

This is not a synthetic DXY. It is a cached confirmation score built only when
at least three real broker symbols are available. Missing symbols produce a
neutral result and never inject hard-coded prices.
"""

import math
import time
from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:  # test/offline environments
    mt5 = None

from config import scalping_settings

_CACHE: dict[str, Any] = {"loaded_at": 0.0, "result": None}
_PAIR_CONFIG = {
    "EURUSD": (-0.40, ("EURUSD",)),
    "GBPUSD": (-0.20, ("GBPUSD",)),
    "USDJPY": (0.25, ("USDJPY",)),
    "USDCHF": (0.15, ("USDCHF",)),
}


def clear_cross_market_cache() -> None:
    _CACHE.update({"loaded_at": 0.0, "result": None})


def _resolve_symbol(base: str) -> str | None:
    if mt5 is None:
        return None
    info = mt5.symbol_info(base)
    if info is not None:
        return base
    try:
        matches = mt5.symbols_get(group=f"*{base}*") or ()
    except Exception:
        matches = ()
    names = [getattr(item, "name", "") for item in matches if getattr(item, "name", "")]
    names.sort(key=lambda name: (len(name), name))
    return names[0] if names else None


def _closed_return(symbol: str, lookback: int) -> float | None:
    if mt5 is None:
        return None
    try:
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, max(lookback + 3, 7))
    except Exception:
        return None
    if rates is None or len(rates) < lookback + 2:
        return None
    closes = [float(row["close"]) for row in rates]
    current_closed = closes[-2]
    earlier_closed = closes[-2 - lookback]
    if current_closed <= 0 or earlier_closed <= 0:
        return None
    return math.log(current_closed / earlier_closed)


def build_cross_market_context(force_refresh: bool = False) -> dict[str, Any]:
    if not bool(getattr(scalping_settings, "SCALPING_CROSS_MARKET_CONTEXT_ENABLED", True)):
        return {"status": "DISABLED", "usd_bias": "NEUTRAL", "gold_bias": "NEUTRAL"}
    if mt5 is None:
        return {"status": "MT5_UNAVAILABLE", "usd_bias": "NEUTRAL", "gold_bias": "NEUTRAL", "pressure_score": 0.0, "available_symbols": 0, "required_symbols": int(getattr(scalping_settings, "SCALPING_CROSS_MARKET_MIN_SYMBOLS", 3))}

    now = time.monotonic()
    refresh = max(15.0, float(getattr(scalping_settings, "SCALPING_CROSS_MARKET_REFRESH_SECONDS", 60.0)))
    if not force_refresh and _CACHE.get("result") is not None and now - float(_CACHE.get("loaded_at", 0.0)) < refresh:
        cached = dict(_CACHE["result"])
        cached["cache_hit"] = True
        cached["cache_age_seconds"] = round(now - float(_CACHE["loaded_at"]), 3)
        return cached

    lookback = max(1, int(getattr(scalping_settings, "SCALPING_CROSS_MARKET_M5_LOOKBACK", 3)))
    scale = max(1e-6, float(getattr(scalping_settings, "SCALPING_CROSS_MARKET_RETURN_SCALE", 0.001)))
    minimum = max(1, int(getattr(scalping_settings, "SCALPING_CROSS_MARKET_MIN_SYMBOLS", 3)))
    weighted_sum = 0.0
    weight_used = 0.0
    details: dict[str, Any] = {}

    for base, (weight, _) in _PAIR_CONFIG.items():
        symbol = _resolve_symbol(base)
        value = _closed_return(symbol, lookback) if symbol else None
        if value is None or not math.isfinite(value):
            details[base] = {"status": "UNAVAILABLE", "symbol": symbol or ""}
            continue
        normalized = max(-1.0, min(1.0, value / scale))
        contribution = normalized * weight
        weighted_sum += contribution
        weight_used += abs(weight)
        details[base] = {
            "status": "OK",
            "symbol": symbol,
            "log_return": round(value, 8),
            "normalized_return": round(normalized, 4),
            "usd_weight": weight,
            "contribution": round(contribution, 4),
        }

    available = sum(1 for item in details.values() if item.get("status") == "OK")
    if available < minimum or weight_used <= 0:
        result = {
            "status": "INSUFFICIENT_DATA",
            "usd_bias": "NEUTRAL",
            "gold_bias": "NEUTRAL",
            "pressure_score": 0.0,
            "available_symbols": available,
            "required_symbols": minimum,
            "details": details,
            "cache_hit": False,
            "cache_age_seconds": 0.0,
        }
    else:
        pressure = max(-1.0, min(1.0, weighted_sum / weight_used))
        threshold = max(0.05, float(getattr(scalping_settings, "SCALPING_CROSS_MARKET_BIAS_THRESHOLD", 0.25)))
        usd_bias = "STRONG" if pressure >= threshold else "WEAK" if pressure <= -threshold else "NEUTRAL"
        gold_bias = "SELL" if usd_bias == "STRONG" else "BUY" if usd_bias == "WEAK" else "NEUTRAL"
        result = {
            "status": "OK",
            "usd_bias": usd_bias,
            "gold_bias": gold_bias,
            "pressure_score": round(pressure, 4),
            "available_symbols": available,
            "required_symbols": minimum,
            "details": details,
            "cache_hit": False,
            "cache_age_seconds": 0.0,
        }

    _CACHE.update({"loaded_at": now, "result": dict(result)})
    return result
