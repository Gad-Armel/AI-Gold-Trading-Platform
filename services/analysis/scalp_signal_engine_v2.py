from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from config import scalping_settings
from services.market_data.spread_utils import hard_entry_spread_limit_usd, spread_exceeds
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState


_REQUIRED_COLUMNS = {"time", "open", "high", "low", "close"}
_METRIC_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if pd.isna(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _prepare_candles(data: Any, timeframe: str) -> pd.DataFrame:
    if data is None:
        raise ValueError(f"{timeframe} candles are missing.")

    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(
            f"{timeframe} candles are missing columns: {sorted(missing)}"
        )

    for column in ["open", "high", "low", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["open", "high", "low", "close"]).copy()
    frame = frame.sort_values("time").reset_index(drop=True)

    minimum = int(scalping_settings.SCALPING_MIN_REQUIRED_CANDLES)
    if len(frame) < minimum:
        raise ValueError(
            f"{timeframe} has only {len(frame)} valid candles; {minimum} required."
        )

    return frame


def _rsi(close: pd.Series, period: int) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0.0)
    loss = -change.clip(upper=0.0)

    average_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    average_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0.0, float("nan"))
    result = 100.0 - (100.0 / (1.0 + relative_strength))

    # When no losses exist, RSI should be 100; when no movement exists, 50.
    result = result.fillna(50.0)
    result = result.where(average_loss != 0.0, 100.0)
    result = result.where((average_gain != 0.0) | (average_loss != 0.0), 50.0)
    return result


def _atr(frame: pd.DataFrame, period: int) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    true_range = ranges.max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False).mean()


def _timeframe_metric_key(frame: pd.DataFrame, timeframe: str) -> tuple[Any, ...]:
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]
    return (
        timeframe,
        len(frame),
        str(latest["time"]),
        round(_safe_float(latest["open"]), 8),
        round(_safe_float(latest["high"]), 8),
        round(_safe_float(latest["low"]), 8),
        round(_safe_float(latest["close"]), 8),
        str(previous["time"]),
        round(_safe_float(previous["close"]), 8),
    )


def _timeframe_metrics(frame: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    cache_key = _timeframe_metric_key(frame, timeframe)
    cached = _METRIC_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    fast_period = int(scalping_settings.SCALPING_FAST_EMA_PERIOD)
    slow_period = int(scalping_settings.SCALPING_SLOW_EMA_PERIOD)
    context_period = int(scalping_settings.SCALPING_CONTEXT_EMA_PERIOD)
    atr_period = int(scalping_settings.SCALPING_ATR_PERIOD)
    rsi_period = int(scalping_settings.SCALPING_RSI_PERIOD)
    momentum_lookback = int(scalping_settings.SCALPING_MOMENTUM_LOOKBACK)
    breakout_lookback = int(scalping_settings.SCALPING_BREAKOUT_LOOKBACK)

    working = frame.copy()
    working["ema_fast"] = working["close"].ewm(
        span=fast_period,
        adjust=False,
    ).mean()
    working["ema_slow"] = working["close"].ewm(
        span=slow_period,
        adjust=False,
    ).mean()
    working["ema_context"] = working["close"].ewm(
        span=context_period,
        adjust=False,
    ).mean()
    working["atr"] = _atr(working, atr_period)
    working["rsi"] = _rsi(working["close"], rsi_period)

    latest = working.iloc[-1]
    previous = working.iloc[-2]
    momentum_index = max(0, len(working) - 1 - momentum_lookback)
    momentum_reference = working.iloc[momentum_index]

    breakout_source = working.iloc[-(breakout_lookback + 1):-1]
    previous_high = _safe_float(breakout_source["high"].max())
    previous_low = _safe_float(breakout_source["low"].min())

    close = _safe_float(latest["close"])
    open_price = _safe_float(latest["open"])
    high = _safe_float(latest["high"])
    low = _safe_float(latest["low"])
    atr_value = max(_safe_float(latest["atr"]), 0.0)
    candle_body = close - open_price
    candle_range = max(high - low, 0.0)

    time_value = latest["time"]
    if isinstance(time_value, pd.Timestamp):
        candle_time = time_value.to_pydatetime()
    elif isinstance(time_value, datetime):
        candle_time = time_value
    else:
        candle_time = pd.to_datetime(time_value).to_pydatetime()

    result = {
        "timeframe": timeframe,
        "candle_time": candle_time,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "previous_close": _safe_float(previous["close"]),
        "ema_fast": _safe_float(latest["ema_fast"]),
        "ema_slow": _safe_float(latest["ema_slow"]),
        "ema_context": _safe_float(latest["ema_context"]),
        "atr": atr_value,
        "rsi": _safe_float(latest["rsi"], 50.0),
        "momentum": close - _safe_float(momentum_reference["close"]),
        "ema_fast_slope": _safe_float(latest["ema_fast"])
        - _safe_float(working.iloc[momentum_index]["ema_fast"]),
        "previous_high": previous_high,
        "previous_low": previous_low,
        "breakout_buy": close > previous_high,
        "breakout_sell": close < previous_low,
        "pullback_buy": (
            _safe_float(latest["ema_fast"]) > _safe_float(latest["ema_slow"])
            and low <= _safe_float(latest["ema_fast"])
            and close > _safe_float(latest["ema_fast"])
        ),
        "pullback_sell": (
            _safe_float(latest["ema_fast"]) < _safe_float(latest["ema_slow"])
            and high >= _safe_float(latest["ema_fast"])
            and close < _safe_float(latest["ema_fast"])
        ),
        "impulse_buy": candle_body > 0 and (
            atr_value <= 0 or candle_body >= atr_value * 0.25
        ),
        "impulse_sell": candle_body < 0 and (
            atr_value <= 0 or abs(candle_body) >= atr_value * 0.25
        ),
        "candle_body": candle_body,
        "candle_range": candle_range,
        "distance_from_fast_ema": abs(close - _safe_float(latest["ema_fast"])),
        "distance_fast_atr_ratio": (
            abs(close - _safe_float(latest["ema_fast"])) / atr_value
            if atr_value > 0
            else float("inf")
        ),
    }
    if len(_METRIC_CACHE) > 300:
        _METRIC_CACHE.clear()
    _METRIC_CACHE[cache_key] = dict(result)
    return result


def _session_allowed(snapshot: ScalpingSnapshotState) -> tuple[bool, str]:
    active = set(snapshot.active_sessions)

    if not active:
        if scalping_settings.SCALPING_BLOCK_OFF_SESSION:
            return False, "No configured trading session is active."
        return True, "Off-session trading is permitted by configuration."

    allowed = False
    if "Asian" in active and scalping_settings.SCALPING_ALLOW_ASIAN_SESSION:
        allowed = True
    if "London" in active and scalping_settings.SCALPING_ALLOW_LONDON_SESSION:
        allowed = True
    if "New York" in active and scalping_settings.SCALPING_ALLOW_NEW_YORK_SESSION:
        allowed = True

    if not allowed:
        return False, f"Active sessions are disabled for scalping: {sorted(active)}"

    return True, f"Active session accepted: {snapshot.session}."


def _score_direction(
    direction: str,
    snapshot: ScalpingSnapshotState,
    m1: dict[str, Any],
    m5: dict[str, Any],
    m15: dict[str, Any],
) -> tuple[float, list[str], str]:
    reasons: list[str] = []
    score = 0.0
    is_buy = direction == "BUY"

    spread = snapshot.spread
    max_spread = float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD)
    if spread <= max_spread * 0.35:
        score += 15.0
        reasons.append("Spread is excellent for a scalp.")
    elif spread <= max_spread:
        score += 8.0
        reasons.append("Spread is inside the scalping limit.")

    def aligned(metrics: dict[str, Any]) -> bool:
        if is_buy:
            return (
                metrics["ema_fast"] > metrics["ema_slow"]
                and metrics["close"] > metrics["ema_context"]
            )
        return (
            metrics["ema_fast"] < metrics["ema_slow"]
            and metrics["close"] < metrics["ema_context"]
        )

    if aligned(m1):
        score += 22.0
        reasons.append(f"M1 EMA structure supports {direction}.")
    if aligned(m5):
        score += 20.0
        reasons.append(f"M5 context supports {direction}.")
    if aligned(m15):
        score += 10.0
        reasons.append(f"M15 context supports {direction}.")

    minimum_momentum = float(
        scalping_settings.SCALPING_MIN_DIRECTIONAL_MOMENTUM_USD
    )
    momentum_ok = (
        m1["momentum"] >= minimum_momentum and m1["ema_fast_slope"] > 0
        if is_buy
        else m1["momentum"] <= -minimum_momentum and m1["ema_fast_slope"] < 0
    )
    if momentum_ok:
        score += 15.0
        reasons.append(f"M1 momentum supports {direction}.")
    else:
        reasons.append(
            f"M1 momentum is not strong enough for {direction}: "
            f"{m1['momentum']:.3f}."
        )

    price_side_ok = (
        m1["close"] > m1["ema_fast"]
        if is_buy
        else m1["close"] < m1["ema_fast"]
    )
    if price_side_ok:
        score += 5.0
        reasons.append(f"M1 close is on the correct side of the fast EMA for {direction}.")
    elif scalping_settings.SCALPING_REQUIRE_PRICE_SIDE_CONFIRMATION:
        reasons.append(f"M1 close is on the wrong side of the fast EMA for {direction}.")

    breakout = m1["breakout_buy"] if is_buy else m1["breakout_sell"]
    pullback = m1["pullback_buy"] if is_buy else m1["pullback_sell"]
    impulse = m1["impulse_buy"] if is_buy else m1["impulse_sell"]
    distance_ratio = m1["distance_fast_atr_ratio"]

    breakout_quality = (
        breakout
        and momentum_ok
        and (price_side_ok or not scalping_settings.SCALPING_REQUIRE_PRICE_SIDE_CONFIRMATION)
        and distance_ratio
        <= float(scalping_settings.SCALPING_MAX_BREAKOUT_DISTANCE_ATR_RATIO)
    )
    pullback_quality = (
        pullback
        and momentum_ok
        and (price_side_ok or not scalping_settings.SCALPING_REQUIRE_PRICE_SIDE_CONFIRMATION)
        and distance_ratio
        <= float(scalping_settings.SCALPING_MAX_PULLBACK_DISTANCE_ATR_RATIO)
    )
    impulse_quality = (
        bool(scalping_settings.SCALPING_ENABLE_MOMENTUM_IMPULSE)
        and impulse
        and momentum_ok
        and (price_side_ok or not scalping_settings.SCALPING_REQUIRE_PRICE_SIDE_CONFIRMATION)
    )

    if breakout_quality:
        score += 15.0
        pattern = "BREAKOUT"
        reasons.append(
            f"Qualified M1 breakout detected for {direction}; "
            f"EMA distance={distance_ratio:.3f} ATR."
        )
    elif pullback_quality:
        score += 13.0
        pattern = "PULLBACK_CONTINUATION"
        reasons.append(
            f"Qualified M1 pullback continuation detected for {direction}; "
            f"EMA distance={distance_ratio:.3f} ATR."
        )
    elif impulse_quality:
        score += 7.0
        pattern = "MOMENTUM_IMPULSE"
        reasons.append(f"Qualified M1 impulse candle supports {direction}.")
    else:
        pattern = "NO_ENTRY_PATTERN"
        if breakout and distance_ratio > float(
            scalping_settings.SCALPING_MAX_BREAKOUT_DISTANCE_ATR_RATIO
        ):
            reasons.append(
                "Breakout rejected as overextended: "
                f"{distance_ratio:.3f} ATR from the fast EMA."
            )
        elif pullback and distance_ratio > float(
            scalping_settings.SCALPING_MAX_PULLBACK_DISTANCE_ATR_RATIO
        ):
            reasons.append(
                "Pullback rejected because the entry is too far from the fast EMA: "
                f"{distance_ratio:.3f} ATR."
            )
        elif impulse and not scalping_settings.SCALPING_ENABLE_MOMENTUM_IMPULSE:
            reasons.append("Standalone momentum-impulse entries are disabled in V2.")

    rsi = m1["rsi"]
    if is_buy:
        rsi_ok = (
            float(scalping_settings.SCALPING_BUY_RSI_MIN)
            <= rsi
            <= float(scalping_settings.SCALPING_BUY_RSI_MAX)
        )
    else:
        rsi_ok = (
            float(scalping_settings.SCALPING_SELL_RSI_MIN)
            <= rsi
            <= float(scalping_settings.SCALPING_SELL_RSI_MAX)
        )

    if rsi_ok:
        score += 8.0
        reasons.append(f"M1 RSI is compatible with {direction}: {rsi:.1f}.")

    atr_value = m1["atr"]
    if (
        float(scalping_settings.SCALPING_MIN_M1_ATR_USD)
        <= atr_value
        <= float(scalping_settings.SCALPING_MAX_M1_ATR_USD)
    ):
        score += 5.0
        reasons.append(f"M1 ATR is tradable: {atr_value:.3f}.")

    if snapshot.session in {"London", "New York"}:
        score += 5.0
        reasons.append(f"{snapshot.session} session activity bonus applied.")
    elif snapshot.session == "Asian":
        score += 2.0
        reasons.append("Asian session accepted with a smaller activity bonus.")

    return min(score, 100.0), reasons, pattern


def _dynamic_targets(
    score: float,
    atr: float,
    volume_value: float,
    spread: float,
) -> tuple[float, float]:
    minimum_target = float(scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD)
    maximum_target = float(scalping_settings.SCALPING_MAX_PROFIT_TARGET_USD)
    minimum_score = float(scalping_settings.SCALPING_MIN_ENTRY_SCORE)

    score_range = max(1.0, 100.0 - minimum_score)
    score_ratio = max(0.0, min(1.0, (score - minimum_score) / score_range))
    score_target = minimum_target + (maximum_target - minimum_target) * score_ratio

    spread_cost = max(0.0, spread * volume_value)
    spread_floor = spread_cost * float(
        scalping_settings.SCALPING_TARGET_SPREAD_MULTIPLIER
    )

    atr_profit_capacity = max(0.0, atr * volume_value)
    min_stop = float(scalping_settings.SCALPING_MIN_STOP_LOSS_USD)
    max_stop = float(scalping_settings.SCALPING_MAX_STOP_LOSS_USD)
    stop = atr_profit_capacity * float(
        scalping_settings.SCALPING_STOP_ATR_PROFIT_RATIO
    )
    stop = max(min_stop, min(max_stop, stop))

    target = max(minimum_target, spread_floor, stop, score_target)
    target = min(maximum_target, target)

    return round(target, 2), round(stop, 2)


def _signal_key(
    direction: str,
    pattern: str,
    snapshot: ScalpingSnapshotState,
    m1: dict[str, Any],
) -> str:
    candle_time = m1["candle_time"].strftime("%Y%m%d%H%M%S")
    bucket_size = max(
        0.01,
        float(scalping_settings.SCALPING_SIGNAL_PRICE_BUCKET_USD),
    )
    price_bucket = round(snapshot.mid / bucket_size)
    return f"{direction}|{pattern}|{candle_time}|{price_bucket}"


def _wait_signal(
    reasons: list[str],
    block_reasons: list[str],
    metrics: dict[str, Any] | None = None,
) -> ScalpSignalState:
    return ScalpSignalState(
        action="WAIT",
        direction="NONE",
        allowed=False,
        score=0.0,
        confidence=0.0,
        target_profit_usd=0.0,
        stop_loss_usd=0.0,
        signal_key="",
        pattern="NONE",
        metrics=metrics or {},
        reasons=reasons,
        block_reasons=block_reasons,
    )


def build_scalp_signal(snapshot: ScalpingSnapshotState) -> ScalpSignalState:
    reasons: list[str] = []
    block_reasons: list[str] = []

    if not scalping_settings.SCALPING_ENABLED:
        return _wait_signal([], ["Scalping is disabled in configuration."])

    hard_spread_limit = hard_entry_spread_limit_usd()
    if spread_exceeds(snapshot.spread, hard_spread_limit):
        block_reasons.append(
            "Spread exceeds the absolute scalping entry limit: "
            f"{snapshot.spread:.3f} > {hard_spread_limit:.3f}."
        )

    session_ok, session_reason = _session_allowed(snapshot)
    reasons.append(session_reason)
    if not session_ok:
        block_reasons.append(session_reason)

    try:
        m1 = _timeframe_metrics(
            _prepare_candles(snapshot.candles.get("M1"), "M1"),
            "M1",
        )
        m5 = _timeframe_metrics(
            _prepare_candles(snapshot.candles.get("M5"), "M5"),
            "M5",
        )
        m15 = _timeframe_metrics(
            _prepare_candles(snapshot.candles.get("M15"), "M15"),
            "M15",
        )
    except Exception as error:
        block_reasons.append(str(error))
        return _wait_signal(reasons, block_reasons)

    metrics = {
        "M1": m1,
        "M5": m5,
        "M15": m15,
    }

    if not (
        float(scalping_settings.SCALPING_MIN_M1_ATR_USD)
        <= m1["atr"]
        <= float(scalping_settings.SCALPING_MAX_M1_ATR_USD)
    ):
        block_reasons.append(
            "M1 ATR is outside the permitted scalping range: "
            f"{m1['atr']:.3f}."
        )

    buy_score, buy_reasons, buy_pattern = _score_direction(
        "BUY", snapshot, m1, m5, m15
    )
    sell_score, sell_reasons, sell_pattern = _score_direction(
        "SELL", snapshot, m1, m5, m15
    )

    metrics["buy_score"] = buy_score
    metrics["sell_score"] = sell_score

    if buy_score >= sell_score:
        direction = "BUY"
        score = buy_score
        direction_reasons = buy_reasons
        pattern = buy_pattern
        opposite_score = sell_score
    else:
        direction = "SELL"
        score = sell_score
        direction_reasons = sell_reasons
        pattern = sell_pattern
        opposite_score = buy_score

    reasons.extend(direction_reasons)

    minimum_score = float(scalping_settings.SCALPING_MIN_ENTRY_SCORE)
    tie_margin = float(scalping_settings.SCALPING_DIRECTION_TIE_MARGIN)

    if score < minimum_score:
        block_reasons.append(
            f"Best scalp score is below minimum: {score:.1f} < {minimum_score:.1f}."
        )

    if score - opposite_score < tie_margin:
        block_reasons.append(
            "BUY and SELL scores are too close for a directional scalp: "
            f"{buy_score:.1f} versus {sell_score:.1f}."
        )

    if pattern == "NO_ENTRY_PATTERN":
        block_reasons.append("No breakout, pullback continuation, or impulse entry exists.")

    if block_reasons:
        wait_state = _wait_signal(reasons, block_reasons, metrics)
        wait_state.score = round(score, 2)
        wait_state.confidence = round(score / 100.0, 4)
        return wait_state

    volume_value = (
        float(scalping_settings.SCALPING_LOT_SIZE) * snapshot.contract_size
    )
    target, stop = _dynamic_targets(
        score, m1["atr"], volume_value, snapshot.spread
    )
    key = _signal_key(direction, pattern, snapshot, m1)

    return ScalpSignalState(
        action=direction,
        direction=direction,
        allowed=True,
        score=round(score, 2),
        confidence=round(score / 100.0, 4),
        target_profit_usd=target,
        stop_loss_usd=stop,
        signal_key=key,
        pattern=pattern,
        metrics=metrics,
        reasons=reasons,
        block_reasons=[],
    )
