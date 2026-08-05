from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import MetaTrader5 as mt5
import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState
from services.market_data.candle_service import get_candles
from services.market_data.price_service import get_current_price
from services.market_data.session_service import detect_market_session


_TIMEFRAME_CONFIG = {
    "M1": ("SCALPING_M1_CANDLES", 60, "SCALPING_M1_FULL_RESYNC_SECONDS"),
    "M5": ("SCALPING_M5_CANDLES", 300, "SCALPING_M5_FULL_RESYNC_SECONDS"),
    "M15": ("SCALPING_M15_CANDLES", 900, "SCALPING_M15_FULL_RESYNC_SECONDS"),
    "H1": ("SCALPING_H1_CANDLES", 3600, "SCALPING_H1_FULL_RESYNC_SECONDS"),
    "H4": ("SCALPING_H4_CANDLES", 14400, "SCALPING_H4_FULL_RESYNC_SECONDS"),
}

# Each timeframe has an independent cache.  A full MT5 history request is made
# only when the expected candle timestamp changes, after an explicit resync
# interval, or after the previous request failed and the retry throttle expires.
_CANDLE_CACHE: dict[str, dict[str, Any]] = {}
_QUOTE_ACTIVITY: dict[str, dict[str, Any]] = {}


def clear_scalping_candle_cache() -> None:
    """Clear the in-process candle and quote-activity caches."""
    _CANDLE_CACHE.clear()
    _QUOTE_ACTIVITY.clear()


def _quote_age_seconds(symbol: str, time_msc: int, bid: float, ask: float) -> float:
    """Measure how long MT5 has gone without publishing a new quote.

    Broker clocks can use a stable server offset, so wall-clock subtraction is
    unreliable. Tracking changes in ``time_msc`` inside the running process
    provides a safe, offset-independent freshness measure.
    """
    now = time.monotonic()
    identity = (int(time_msc), round(float(bid), 10), round(float(ask), 10))
    state = _QUOTE_ACTIVITY.get(symbol)
    if state is None or state.get("identity") != identity:
        _QUOTE_ACTIVITY[symbol] = {"identity": identity, "changed_at": now}
        return 0.0
    return max(0.0, now - float(state.get("changed_at", now)))


def _utc_naive_timestamp(value: Any) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp


def _expected_bucket(now: datetime, period_seconds: int) -> pd.Timestamp:
    epoch = int(now.timestamp())
    bucket_epoch = epoch - epoch % period_seconds
    return pd.Timestamp(datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)).tz_localize(None)


def _seconds_until_next_bucket(now: datetime, period_seconds: int) -> float:
    epoch = now.timestamp()
    remainder = epoch % period_seconds
    return max(0.0, period_seconds - remainder)


def _full_resync_seconds(setting_name: str, period_seconds: int) -> float:
    fallback = max(float(period_seconds) * 2.0, 120.0)
    return max(float(period_seconds), float(getattr(scalping_settings, setting_name, fallback)))


def _tick_patch_live_m1(candles: pd.DataFrame, mid: float, now: datetime) -> tuple[pd.DataFrame, bool]:
    """Update the cached unfinished M1 candle from the current MT5 tick.

    This keeps the live trigger responsive without re-downloading 180 M1 bars
    every 0.5 seconds. A new minute is never synthesized here; the full history
    loader owns candle-boundary transitions.
    """
    if candles is None or candles.empty:
        return candles, False

    expected = _expected_bucket(now, 60)
    last_time = _utc_naive_timestamp(candles.iloc[-1].get("time"))
    if last_time is None or last_time != expected:
        return candles, False

    index = candles.index[-1]
    current_high = float(candles.at[index, "high"])
    current_low = float(candles.at[index, "low"])
    candles.at[index, "close"] = float(mid)
    candles.at[index, "high"] = max(current_high, float(mid))
    candles.at[index, "low"] = min(current_low, float(mid))
    return candles, True


def _load_timeframe(
    symbol: str,
    timeframe: str,
    *,
    now: datetime,
    mid: float,
) -> tuple[Any, bool, dict[str, Any]]:
    count_setting, period_seconds, resync_setting = _TIMEFRAME_CONFIG[timeframe]
    count = int(getattr(scalping_settings, count_setting))
    full_resync_seconds = _full_resync_seconds(resync_setting, period_seconds)
    retry_seconds = max(
        1.0,
        float(getattr(scalping_settings, "SCALPING_CANDLE_MISSING_BAR_RETRY_SECONDS", 5.0)),
    )
    boundary_grace = max(
        0.0,
        float(getattr(scalping_settings, "SCALPING_CANDLE_BOUNDARY_GRACE_SECONDS", 1.5)),
    )

    now_monotonic = time.monotonic()
    cache_key = f"{symbol}:{timeframe}"
    cached = _CANDLE_CACHE.get(cache_key)
    expected_bucket = _expected_bucket(now, period_seconds)
    seconds_into_bucket = now.timestamp() % period_seconds

    cached_data = cached.get("candles") if cached else None
    loaded_at = float(cached.get("loaded_at", 0.0)) if cached else 0.0
    last_attempt_epoch = float(cached.get("last_attempt_epoch", 0.0)) if cached else 0.0
    cache_age = now_monotonic - loaded_at if loaded_at else None
    last_attempt_age = now.timestamp() - last_attempt_epoch if last_attempt_epoch else None
    cached_last_time = (
        _utc_naive_timestamp(cached_data.iloc[-1].get("time"))
        if cached_data is not None and not getattr(cached_data, "empty", True)
        else None
    )

    boundary_refresh_due = bool(
        cached_data is not None
        and cached_last_time is not None
        and cached_last_time < expected_bucket
        and seconds_into_bucket >= boundary_grace
    )
    periodic_resync_due = bool(
        cached_data is not None
        and cache_age is not None
        and cache_age >= full_resync_seconds
    )
    retry_allowed = last_attempt_age is None or last_attempt_age >= retry_seconds
    must_fetch = cached_data is None or ((boundary_refresh_due or periodic_resync_due) and retry_allowed)

    refresh_reason = "CACHE_HIT"
    fetch_duration_ms = 0.0
    fetch_error = ""
    refreshed = False

    if must_fetch:
        if cached_data is None:
            refresh_reason = "INITIAL_LOAD"
        elif boundary_refresh_due:
            refresh_reason = "NEW_CANDLE_BOUNDARY"
        else:
            refresh_reason = "PERIODIC_RESYNC"

        fetch_started = time.perf_counter()
        try:
            candles = get_candles(symbol, timeframe, count)
        except Exception as error:  # defensive around broker/terminal edge cases
            candles = None
            fetch_error = f"{type(error).__name__}: {error}"
        fetch_duration_ms = (time.perf_counter() - fetch_started) * 1000.0

        if candles is not None and not getattr(candles, "empty", False):
            candles = candles.copy()
            # Downstream unified analysis can safely skip repeated full-frame
            # dtype/NaN/chronology scans on each half-second cycle.
            candles.attrs["scalping_normalized"] = True
            refreshed = True
            _CANDLE_CACHE[cache_key] = {
                "loaded_at": now_monotonic,
                "last_attempt_epoch": now.timestamp(),
                "candles": candles,
                "requested_count": count,
                "last_fetch_duration_ms": fetch_duration_ms,
                "last_refresh_reason": refresh_reason,
                "last_fetch_error": "",
            }
            cached = _CANDLE_CACHE[cache_key]
            cached_data = candles
            loaded_at = now_monotonic
            cache_age = 0.0
            cached_last_time = _utc_naive_timestamp(candles.iloc[-1].get("time"))
        elif cached_data is not None:
            # Preserve the last valid history.  Throttle further retries so a
            # closed market or delayed new candle does not create a one-second
            # MT5 request loop.
            cached["last_attempt_epoch"] = now.timestamp()
            cached["last_fetch_duration_ms"] = fetch_duration_ms
            cached["last_fetch_error"] = fetch_error or "MT5 returned no candles."
            cached["last_refresh_reason"] = "STALE_FALLBACK"
            refresh_reason = "STALE_FALLBACK"
        else:
            raise RuntimeError(
                f"MT5 returned no {timeframe} candles for {symbol}."
                + (f" {fetch_error}" if fetch_error else "")
            )

    assert cached_data is not None

    tick_patched = False
    if timeframe == "M1" and bool(
        getattr(scalping_settings, "SCALPING_PATCH_LIVE_M1_FROM_TICK", True)
    ):
        cached_data, tick_patched = _tick_patch_live_m1(cached_data, mid, now)
        if tick_patched and not refreshed:
            refresh_reason = "TICK_PATCHED"

    current_cache = _CANDLE_CACHE.get(cache_key, {})
    final_loaded_at = float(current_cache.get("loaded_at", loaded_at or now_monotonic))
    final_cache_age = max(0.0, now_monotonic - final_loaded_at)
    last_fetch_duration_ms = float(current_cache.get("last_fetch_duration_ms", fetch_duration_ms) or 0.0)
    last_fetch_error = str(current_cache.get("last_fetch_error", fetch_error) or "")
    current_last_time = _utc_naive_timestamp(cached_data.iloc[-1].get("time"))

    status = "REFRESHED" if refreshed else "TICK_PATCHED" if tick_patched else "HIT"
    if refresh_reason == "STALE_FALLBACK":
        status = "STALE_FALLBACK"

    details = {
        "timeframe": timeframe,
        "status": status,
        "refresh_reason": refresh_reason,
        "requested_count": count,
        "bars_received": int(len(cached_data)),
        "cache_age_seconds": round(final_cache_age, 3),
        "fetch_duration_ms": round(last_fetch_duration_ms, 3),
        "tick_patched": tick_patched,
        "expected_current_candle_time": expected_bucket.isoformat(),
        "cached_current_candle_time": current_last_time.isoformat() if current_last_time is not None else "",
        "next_boundary_in_seconds": round(_seconds_until_next_bucket(now, period_seconds), 3),
        "full_resync_seconds": full_resync_seconds,
        "last_fetch_error": last_fetch_error,
    }
    cache_hit = status in {"HIT", "TICK_PATCHED"}
    return cached_data, cache_hit, details


def _load_candles(
    symbol: str,
    *,
    now: datetime,
    mid: float,
) -> tuple[dict[str, Any], bool, dict[str, dict[str, Any]]]:
    candles: dict[str, Any] = {}
    cache_flags: list[bool] = []
    details: dict[str, dict[str, Any]] = {}
    for timeframe in _TIMEFRAME_CONFIG:
        data, cache_hit, record = _load_timeframe(
            symbol,
            timeframe,
            now=now,
            mid=mid,
        )
        candles[timeframe] = data
        cache_flags.append(cache_hit)
        details[timeframe] = record
    return candles, all(cache_flags), details


def _symbol_metadata(symbol: str) -> tuple[float, float]:
    info = mt5.symbol_info(symbol)
    if info is None:
        return (
            float(scalping_settings.SCALPING_CONTRACT_SIZE_FALLBACK),
            0.01,
        )

    contract_size = float(
        getattr(
            info,
            "trade_contract_size",
            scalping_settings.SCALPING_CONTRACT_SIZE_FALLBACK,
        )
        or scalping_settings.SCALPING_CONTRACT_SIZE_FALLBACK
    )
    point = float(getattr(info, "point", 0.01) or 0.01)

    if contract_size <= 0:
        contract_size = float(scalping_settings.SCALPING_CONTRACT_SIZE_FALLBACK)
    if point <= 0:
        point = 0.01

    return contract_size, point


def get_scalping_snapshot(symbol: str) -> ScalpingSnapshotState:
    price = get_current_price(symbol)
    if not price:
        raise RuntimeError(f"No live price returned for {symbol}.")

    bid = float(price.get("bid", 0.0) or 0.0)
    ask = float(price.get("ask", 0.0) or 0.0)
    if bid <= 0 or ask <= 0 or ask < bid:
        raise RuntimeError(f"Invalid bid/ask returned for {symbol}: {price}")

    system_time = datetime.now(timezone.utc)
    tick_time = price.get("tick_time")
    market_time = tick_time if isinstance(tick_time, datetime) else system_time
    if market_time.tzinfo is None:
        market_time = market_time.replace(tzinfo=timezone.utc)
    else:
        market_time = market_time.astimezone(timezone.utc)

    # Candle histories and MT5 ticks must use the same clock. Some brokers
    # expose candle timestamps with a stable server offset relative to the
    # computer clock; using the terminal tick clock prevents false 0-second
    # ages and missed timeframe-boundary refreshes. Session classification still
    # uses actual system UTC so broker offsets cannot move London/New York hours.
    market_clock_offset_seconds = (market_time - system_time).total_seconds()
    mid = (bid + ask) / 2.0
    candles, cache_hit, cache_details = _load_candles(
        symbol,
        now=market_time,
        mid=mid,
    )
    session = detect_market_session(system_time)
    contract_size, point = _symbol_metadata(symbol)

    quote_age_seconds = _quote_age_seconds(
        symbol,
        int(price.get("time_msc", 0) or 0),
        bid,
        ask,
    )

    return ScalpingSnapshotState(
        symbol=symbol,
        timestamp=market_time,
        bid=bid,
        ask=ask,
        spread=ask - bid,
        mid=mid,
        session=session.primary_session,
        active_sessions=list(session.active_sessions),
        candles=candles,
        contract_size=contract_size,
        point=point,
        candle_cache_hit=cache_hit,
        candle_cache_details=cache_details,
        system_timestamp=system_time,
        market_clock_source="MT5_TICK" if isinstance(tick_time, datetime) else "SYSTEM_UTC",
        market_clock_offset_seconds=market_clock_offset_seconds,
        tick_time_msc=int(price.get("time_msc", 0) or 0),
        tick_flags=int(price.get("flags", 0) or 0),
        tick_volume=float(price.get("volume", 0.0) or 0.0),
        tick_volume_real=float(price.get("volume_real", 0.0) or 0.0),
        last_price=float(price.get("last", 0.0) or 0.0),
        quote_age_seconds=round(quote_age_seconds, 3),
    )
