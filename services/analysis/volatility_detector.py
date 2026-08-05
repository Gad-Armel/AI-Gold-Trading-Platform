import math

from config import settings
from models.market_state import MarketSnapshot, VolatilityState


TIMEFRAME_WEIGHTS = {
    "M1": 1,
    "M5": 2,
    "M15": 3,
    "H1": 4,
}

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "H1": 60,
}

ATR_PERIOD = 14
MIN_VALID_TIMEFRAMES = 2


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _setting_float(name, default):
    value = _safe_float(
        getattr(
            settings,
            name,
            default,
        )
    )

    if value is None:
        return float(default)

    return value


def _get_ohlc_rows(candle_data) -> list[dict]:
    """
    Extracts OHLC rows from:

    - pandas DataFrames
    - MT5/numpy structured arrays
    - dictionaries
    - objects with high/low/close attributes
    - tuples in time, open, high, low, close order
    """

    if candle_data is None:
        return []

    rows = []

    # pandas DataFrame
    if hasattr(candle_data, "columns"):
        required_columns = {
            "high",
            "low",
            "close",
        }

        if required_columns.issubset(
            set(candle_data.columns)
        ):
            for _, row in candle_data.iterrows():
                high = _safe_float(
                    row["high"]
                )

                low = _safe_float(
                    row["low"]
                )

                close = _safe_float(
                    row["close"]
                )

                if (
                    high is not None
                    and low is not None
                    and close is not None
                    and high >= low
                    and close > 0
                ):
                    rows.append(
                        {
                            "high": high,
                            "low": low,
                            "close": close,
                        }
                    )

            return rows

    # MT5/numpy structured array
    if hasattr(candle_data, "dtype"):
        dtype_names = getattr(
            candle_data.dtype,
            "names",
            None,
        )

        if (
            dtype_names
            and {
                "high",
                "low",
                "close",
            }.issubset(set(dtype_names))
        ):
            for row in candle_data:
                high = _safe_float(
                    row["high"]
                )

                low = _safe_float(
                    row["low"]
                )

                close = _safe_float(
                    row["close"]
                )

                if (
                    high is not None
                    and low is not None
                    and close is not None
                    and high >= low
                    and close > 0
                ):
                    rows.append(
                        {
                            "high": high,
                            "low": low,
                            "close": close,
                        }
                    )

            return rows

    try:
        candle_rows = list(
            candle_data
        )
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

        elif (
            hasattr(row, "high")
            and hasattr(row, "low")
            and hasattr(row, "close")
        ):
            high = row.high
            low = row.low
            close = row.close

        elif (
            isinstance(row, (list, tuple))
            and len(row) >= 5
        ):
            high = row[2]
            low = row[3]
            close = row[4]

        high = _safe_float(
            high
        )

        low = _safe_float(
            low
        )

        close = _safe_float(
            close
        )

        if (
            high is not None
            and low is not None
            and close is not None
            and high >= low
            and close > 0
        ):
            rows.append(
                {
                    "high": high,
                    "low": low,
                    "close": close,
                }
            )

    return rows


def _calculate_atr(
    ohlc_rows: list[dict],
    period: int = ATR_PERIOD,
):
    """
    Calculates simple Average True Range.
    """

    if len(ohlc_rows) < period + 1:
        return None

    true_ranges = []

    for index in range(
        1,
        len(ohlc_rows),
    ):
        current_high = (
            ohlc_rows[index]["high"]
        )

        current_low = (
            ohlc_rows[index]["low"]
        )

        previous_close = (
            ohlc_rows[index - 1]["close"]
        )

        true_range = max(
            current_high - current_low,
            abs(
                current_high
                - previous_close
            ),
            abs(
                current_low
                - previous_close
            ),
        )

        true_ranges.append(
            true_range
        )

    recent_ranges = true_ranges[
        -period:
    ]

    if len(recent_ranges) < period:
        return None

    return (
        sum(recent_ranges)
        / period
    )


def _normalize_atr_percent(
    timeframe: str,
    atr_percent: float,
) -> float:
    """
    Converts raw ATR percentage to an M1-equivalent rate.

    Raw H1 ATR is naturally larger than raw M1 ATR because H1 covers
    sixty minutes. Dividing by the square root of timeframe duration
    makes the timeframes comparable before combining them.
    """

    minutes = TIMEFRAME_MINUTES.get(
        timeframe,
        1,
    )

    return (
        atr_percent
        / math.sqrt(
            max(1, minutes)
        )
    )


def _classify_volatility(
    normalized_atr_percent: float,
) -> tuple[str, str, float]:
    """
    Classifies normalized multi-timeframe ATR percentage.

    Optional settings may override the default thresholds:

    VOLATILITY_LOW_MAX_NORMALIZED_ATR_PERCENT
    VOLATILITY_NORMAL_MAX_NORMALIZED_ATR_PERCENT
    VOLATILITY_HIGH_MAX_NORMALIZED_ATR_PERCENT
    """

    low_max = _setting_float(
        "VOLATILITY_LOW_MAX_NORMALIZED_ATR_PERCENT",
        0.015,
    )

    normal_max = _setting_float(
        "VOLATILITY_NORMAL_MAX_NORMALIZED_ATR_PERCENT",
        0.050,
    )

    high_max = _setting_float(
        "VOLATILITY_HIGH_MAX_NORMALIZED_ATR_PERCENT",
        0.100,
    )

    if not (
        0
        <= low_max
        < normal_max
        < high_max
    ):
        low_max = 0.015
        normal_max = 0.050
        high_max = 0.100

    if normalized_atr_percent < low_max:
        return (
            "LOW",
            "LOW_RISK",
            0.40,
        )

    if normalized_atr_percent < normal_max:
        return (
            "NORMAL",
            "NORMAL_RISK",
            0.70,
        )

    if normalized_atr_percent < high_max:
        return (
            "HIGH",
            "HIGH_RISK",
            0.60,
        )

    return (
        "EXTREME",
        "DANGEROUS_RISK",
        0.30,
    )


def detect_volatility(
    snapshot: MarketSnapshot,
) -> VolatilityState:
    """
    Detects comparable volatility across M1, M5, M15 and H1.

    Raw ATR percentages are retained for reporting.

    Only normalized ATR percentages are combined for the final
    volatility classification.
    """

    atr_period = max(
        2,
        _safe_int(
            getattr(
                settings,
                "VOLATILITY_ATR_PERIOD",
                ATR_PERIOD,
            ),
            ATR_PERIOD,
        ),
    )

    minimum_valid_timeframes = max(
        1,
        _safe_int(
            getattr(
                settings,
                "VOLATILITY_MIN_VALID_TIMEFRAMES",
                MIN_VALID_TIMEFRAMES,
            ),
            MIN_VALID_TIMEFRAMES,
        ),
    )

    atr_values = {}
    atr_percent_values = {}
    normalized_values = {}
    reasons = []

    weighted_normalized_total = 0.0
    total_weight = 0
    valid_timeframes = 0

    candles = (
        getattr(
            snapshot,
            "candles",
            {},
        )
        or {}
    )

    for (
        timeframe,
        weight,
    ) in TIMEFRAME_WEIGHTS.items():
        candle_data = candles.get(
            timeframe
        )

        ohlc_rows = _get_ohlc_rows(
            candle_data
        )

        atr = _calculate_atr(
            ohlc_rows,
            period=atr_period,
        )

        if atr is None:
            atr_values[timeframe] = 0.0

            atr_percent_values[
                timeframe
            ] = 0.0

            normalized_values[
                timeframe
            ] = 0.0

            reasons.append(
                f"{timeframe}: Not enough valid "
                f"candles for ATR({atr_period})."
            )

            continue

        last_close = (
            ohlc_rows[-1]["close"]
        )

        if last_close <= 0:
            atr_values[timeframe] = 0.0

            atr_percent_values[
                timeframe
            ] = 0.0

            normalized_values[
                timeframe
            ] = 0.0

            reasons.append(
                f"{timeframe}: Invalid close price."
            )

            continue

        raw_atr_percent = (
            atr
            / last_close
        ) * 100.0

        normalized_atr_percent = (
            _normalize_atr_percent(
                timeframe,
                raw_atr_percent,
            )
        )

        atr_values[
            timeframe
        ] = round(
            atr,
            4,
        )

        atr_percent_values[
            timeframe
        ] = round(
            raw_atr_percent,
            5,
        )

        normalized_values[
            timeframe
        ] = round(
            normalized_atr_percent,
            5,
        )

        weighted_normalized_total += (
            normalized_atr_percent
            * weight
        )

        total_weight += weight
        valid_timeframes += 1

        reasons.append(
            f"{timeframe}: "
            f"ATR={atr:.4f}, "
            f"raw ATR%={raw_atr_percent:.5f}, "
            f"normalized ATR%="
            f"{normalized_atr_percent:.5f}, "
            f"weight={weight}."
        )

    if (
        valid_timeframes
        < minimum_valid_timeframes
        or total_weight == 0
    ):
        reasons.append(
            f"Only {valid_timeframes} valid "
            f"timeframe(s) available. "
            f"{minimum_valid_timeframes} required."
        )

        return VolatilityState(
            overall_volatility="UNKNOWN",
            atr_values=atr_values,
            atr_percent_values=(
                atr_percent_values
            ),
            confidence=0.0,
            trade_risk_level=(
                "UNKNOWN_RISK"
            ),
            reasons=reasons,
        )

    weighted_normalized_percent = (
        weighted_normalized_total
        / total_weight
    )

    (
        overall_volatility,
        trade_risk_level,
        base_confidence,
    ) = _classify_volatility(
        weighted_normalized_percent
    )

    coverage_ratio = (
        valid_timeframes
        / len(TIMEFRAME_WEIGHTS)
    )

    confidence = round(
        base_confidence
        * coverage_ratio,
        4,
    )

    reasons.append(
        "Normalized ATR percentages: "
        f"{normalized_values}"
    )

    reasons.append(
        "Weighted normalized ATR%: "
        f"{weighted_normalized_percent:.5f}"
    )

    reasons.append(
        f"Valid timeframes: "
        f"{valid_timeframes}/"
        f"{len(TIMEFRAME_WEIGHTS)}"
    )

    reasons.append(
        f"Overall volatility: "
        f"{overall_volatility}"
    )

    reasons.append(
        f"Trade risk level: "
        f"{trade_risk_level}"
    )

    return VolatilityState(
        overall_volatility=(
            overall_volatility
        ),
        atr_values=atr_values,
        atr_percent_values=(
            atr_percent_values
        ),
        confidence=confidence,
        trade_risk_level=(
            trade_risk_level
        ),
        reasons=reasons,
    )