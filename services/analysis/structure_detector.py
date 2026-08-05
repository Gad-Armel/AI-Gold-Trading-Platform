from models.market_state import MarketSnapshot, StructureState


STRUCTURE_TIMEFRAMES = {
    "M15": 2,
    "H1": 4,
}

LOOKBACK_CANDLES = 50
MIN_CANDLES_REQUIRED = 20
NEAR_LEVEL_ZONE = 0.20


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_current_price(price):
    """
    Extracts a usable price from different possible price formats.
    """

    if price is None:
        return None

    if isinstance(price, (int, float)):
        return float(price)

    if isinstance(price, dict):
        bid = _safe_float(price.get("bid"))
        ask = _safe_float(price.get("ask"))

        if bid is not None and ask is not None:
            return (bid + ask) / 2

        value = _safe_float(price.get("price"))
        if value is not None:
            return value

    if hasattr(price, "bid") and hasattr(price, "ask"):
        bid = _safe_float(price.bid)
        ask = _safe_float(price.ask)

        if bid is not None and ask is not None:
            return (bid + ask) / 2

    if hasattr(price, "last"):
        value = _safe_float(price.last)
        if value is not None:
            return value

    return None


def _get_ohlc_rows(candle_data) -> list[dict]:
    """
    Extracts OHLC rows from:
    - pandas DataFrame
    - MT5 numpy structured arrays
    - list of dictionaries
    - list of tuples/lists
    """

    if candle_data is None:
        return []

    rows = []

    # pandas DataFrame style
    if hasattr(candle_data, "columns"):
        required_columns = {"high", "low", "close"}

        if required_columns.issubset(set(candle_data.columns)):
            for _, row in candle_data.iterrows():
                high = _safe_float(row["high"])
                low = _safe_float(row["low"])
                close = _safe_float(row["close"])

                if high is not None and low is not None and close is not None:
                    rows.append({
                        "high": high,
                        "low": low,
                        "close": close,
                    })

            return rows

    # MT5 numpy structured array style
    if hasattr(candle_data, "dtype"):
        dtype_names = getattr(candle_data.dtype, "names", None)

        if dtype_names and {"high", "low", "close"}.issubset(set(dtype_names)):
            for row in candle_data:
                high = _safe_float(row["high"])
                low = _safe_float(row["low"])
                close = _safe_float(row["close"])

                if high is not None and low is not None and close is not None:
                    rows.append({
                        "high": high,
                        "low": low,
                        "close": close,
                    })

            return rows

    # List style
    try:
        candle_rows = list(candle_data)
    except TypeError:
        return []

    for row in candle_rows:
        high = None
        low = None
        close = None

        if isinstance(row, dict):
            high = row.get("high")
            low = row.get("low")
            close = row.get("close")

        elif hasattr(row, "high") and hasattr(row, "low") and hasattr(row, "close"):
            high = row.high
            low = row.low
            close = row.close

        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            # Common OHLC order:
            # time, open, high, low, close
            high = row[2]
            low = row[3]
            close = row[4]

        high = _safe_float(high)
        low = _safe_float(low)
        close = _safe_float(close)

        if high is not None and low is not None and close is not None:
            rows.append({
                "high": high,
                "low": low,
                "close": close,
            })

    return rows


def _detect_timeframe_structure(
    current_price: float,
    rows: list[dict],
) -> tuple[str, float | None, float | None, int, str]:
    """
    Detects structure for one timeframe.

    Score:
    1 = bullish structure area
    0 = neutral/range
    -1 = bearish structure area
    """

    if len(rows) < MIN_CANDLES_REQUIRED:
        return "UNKNOWN", None, None, 0, "Not enough candles for structure detection."

    recent_rows = rows[-LOOKBACK_CANDLES:]

    # Exclude the latest candle from support/resistance calculation.
    # This avoids using the current candle as its own level.
    level_rows = recent_rows[:-1]

    if len(level_rows) < MIN_CANDLES_REQUIRED:
        return "UNKNOWN", None, None, 0, "Not enough historical candles for key levels."

    support = min(row["low"] for row in level_rows)
    resistance = max(row["high"] for row in level_rows)

    price_range = resistance - support

    if price_range <= 0:
        return "UNKNOWN", support, resistance, 0, "Invalid support/resistance range."

    position_in_range = (current_price - support) / price_range

    if current_price > resistance:
        return (
            "BREAKOUT_UP",
            support,
            resistance,
            1,
            "Price is above recent resistance.",
        )

    if current_price < support:
        return (
            "BREAKDOWN_DOWN",
            support,
            resistance,
            -1,
            "Price is below recent support.",
        )

    if position_in_range <= NEAR_LEVEL_ZONE:
        return (
            "NEAR_SUPPORT",
            support,
            resistance,
            1,
            "Price is near support zone.",
        )

    if position_in_range >= 1 - NEAR_LEVEL_ZONE:
        return (
            "NEAR_RESISTANCE",
            support,
            resistance,
            -1,
            "Price is near resistance zone.",
        )

    return (
        "MIDDLE_OF_RANGE",
        support,
        resistance,
        0,
        "Price is between support and resistance.",
    )


def detect_structure(snapshot: MarketSnapshot) -> StructureState:
    """
    Detects market structure using M15 and H1 candles.
    """

    current_price = _get_current_price(snapshot.price)

    timeframe_structure = {}
    key_levels = {}
    reasons = []

    if current_price is None:
        return StructureState(
            structure_bias="UNKNOWN",
            nearest_support=None,
            nearest_resistance=None,
            distance_to_support=None,
            distance_to_resistance=None,
            timeframe_structure={},
            key_levels={},
            confidence=0.0,
            reasons=["Current price could not be detected."],
        )

    weighted_score = 0
    total_weight = 0

    supports = []
    resistances = []

    for timeframe, weight in STRUCTURE_TIMEFRAMES.items():
        candle_data = snapshot.candles.get(timeframe)
        rows = _get_ohlc_rows(candle_data)

        structure, support, resistance, score, reason = _detect_timeframe_structure(
            current_price=current_price,
            rows=rows,
        )

        timeframe_structure[timeframe] = structure

        if support is not None and resistance is not None:
            support = round(support, 3)
            resistance = round(resistance, 3)

            key_levels[timeframe] = {
                "support": support,
                "resistance": resistance,
            }

            supports.append(support)
            resistances.append(resistance)

        weighted_score += score * weight
        total_weight += weight

        reasons.append(f"{timeframe}: {structure} - {reason}")

    if not supports or not resistances:
        return StructureState(
            structure_bias="UNKNOWN",
            nearest_support=None,
            nearest_resistance=None,
            distance_to_support=None,
            distance_to_resistance=None,
            timeframe_structure=timeframe_structure,
            key_levels=key_levels,
            confidence=0.0,
            reasons=reasons,
        )

    supports_below_price = [level for level in supports if level <= current_price]
    resistances_above_price = [level for level in resistances if level >= current_price]

    if supports_below_price:
        nearest_support = max(supports_below_price)
    else:
        nearest_support = max(supports)

    if resistances_above_price:
        nearest_resistance = min(resistances_above_price)
    else:
        nearest_resistance = min(resistances)

    distance_to_support = current_price - nearest_support
    distance_to_resistance = nearest_resistance - current_price

    if total_weight == 0:
        confidence = 0.0
    else:
        confidence = abs(weighted_score) / total_weight

    if weighted_score >= 4:
        structure_bias = "BULLISH_STRUCTURE"
    elif weighted_score <= -4:
        structure_bias = "BEARISH_STRUCTURE"
    elif weighted_score > 0:
        structure_bias = "WEAK_BULLISH_STRUCTURE"
    elif weighted_score < 0:
        structure_bias = "WEAK_BEARISH_STRUCTURE"
    else:
        structure_bias = "NEUTRAL_STRUCTURE"

    reasons.append(f"Weighted structure score: {weighted_score}")
    reasons.append(f"Nearest support: {round(nearest_support, 3)}")
    reasons.append(f"Nearest resistance: {round(nearest_resistance, 3)}")
    reasons.append(f"Distance to support: {round(distance_to_support, 3)}")
    reasons.append(f"Distance to resistance: {round(distance_to_resistance, 3)}")

    return StructureState(
        structure_bias=structure_bias,
        nearest_support=round(nearest_support, 3),
        nearest_resistance=round(nearest_resistance, 3),
        distance_to_support=round(distance_to_support, 3),
        distance_to_resistance=round(distance_to_resistance, 3),
        timeframe_structure=timeframe_structure,
        key_levels=key_levels,
        confidence=round(confidence, 2),
        reasons=reasons,
    )