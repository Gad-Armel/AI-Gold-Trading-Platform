from models.market_state import MarketSnapshot, TrendState


TIMEFRAME_WEIGHTS = {
    "M1": 1,
    "M5": 2,
    "M15": 3,
    "H1": 4,
}


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_close_values(candle_data) -> list[float]:
    """
    Extracts close prices from different possible candle formats.

    Supports:
    - pandas DataFrame
    - MT5 numpy arrays
    - list of dictionaries
    - list of tuples
    """

    if candle_data is None:
        return []

    closes = []

    # pandas DataFrame style
    if hasattr(candle_data, "columns") and "close" in candle_data.columns:
        for value in candle_data["close"]:
            close = _safe_float(value)
            if close is not None:
                closes.append(close)

        return closes

    # MT5 numpy structured array style
    if hasattr(candle_data, "dtype"):
        dtype_names = getattr(candle_data.dtype, "names", None)

        if dtype_names and "close" in dtype_names:
            for value in candle_data["close"]:
                close = _safe_float(value)
                if close is not None:
                    closes.append(close)

            return closes

    # List style
    try:
        rows = list(candle_data)
    except TypeError:
        return []

    for row in rows:
        close = None

        if isinstance(row, dict):
            close = row.get("close")

        elif hasattr(row, "close"):
            close = row.close

        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            # Common OHLC order:
            # time, open, high, low, close
            close = row[4]

        close = _safe_float(close)

        if close is not None:
            closes.append(close)

    return closes


def _moving_average(values: list[float], period: int):
    if len(values) < period:
        return None

    return sum(values[-period:]) / period


def _detect_single_timeframe_trend(closes: list[float]) -> tuple[str, int, str]:
    """
    Detects trend for one timeframe.

    Score:
    1 = bullish
    0 = sideways/unknown
    -1 = bearish
    """

    if len(closes) < 30:
        return "UNKNOWN", 0, "Not enough candles."

    last_close = closes[-1]
    previous_close = closes[-5]

    fast_ma = _moving_average(closes, 10)
    slow_ma = _moving_average(closes, 30)

    if fast_ma is None or slow_ma is None:
        return "UNKNOWN", 0, "Moving average could not be calculated."

    momentum = last_close - previous_close

    if fast_ma > slow_ma and momentum > 0 and last_close > fast_ma:
        return "BULLISH", 1, "Fast MA above slow MA and price has upward momentum."

    if fast_ma < slow_ma and momentum < 0 and last_close < fast_ma:
        return "BEARISH", -1, "Fast MA below slow MA and price has downward momentum."

    if fast_ma > slow_ma:
        return "WEAK_BULLISH", 1, "Fast MA is above slow MA, but momentum is not strong."

    if fast_ma < slow_ma:
        return "WEAK_BEARISH", -1, "Fast MA is below slow MA, but momentum is not strong."

    return "SIDEWAYS", 0, "Market is moving sideways."


def detect_trend(snapshot: MarketSnapshot) -> TrendState:
    """
    Detects trend across M1, M5, M15, and H1 candles.
    """

    timeframe_trends = {}
    trend_scores = {}
    reasons = []

    total_weighted_score = 0
    max_possible_score = 0

    for timeframe, weight in TIMEFRAME_WEIGHTS.items():
        candle_data = snapshot.candles.get(timeframe)
        closes = _get_close_values(candle_data)

        trend, score, reason = _detect_single_timeframe_trend(closes)

        timeframe_trends[timeframe] = trend
        trend_scores[timeframe] = score

        total_weighted_score += score * weight
        max_possible_score += weight

        reasons.append(f"{timeframe}: {trend} - {reason}")

    if max_possible_score == 0:
        confidence = 0.0
    else:
        confidence = abs(total_weighted_score) / max_possible_score

    if total_weighted_score >= 4:
        overall_trend = "BULLISH"
    elif total_weighted_score <= -4:
        overall_trend = "BEARISH"
    elif total_weighted_score > 0:
        overall_trend = "WEAK_BULLISH"
    elif total_weighted_score < 0:
        overall_trend = "WEAK_BEARISH"
    else:
        overall_trend = "SIDEWAYS"

    reasons.append(f"Weighted trend score: {total_weighted_score}")

    return TrendState(
        overall_trend=overall_trend,
        timeframe_trends=timeframe_trends,
        trend_scores=trend_scores,
        confidence=round(confidence, 2),
        reasons=reasons,
    )