from config import settings


def _get_value(source, *keys, default=None):
    if source is None:
        return default

    for key in keys:
        if isinstance(source, dict):
            value = source.get(key)
        else:
            value = getattr(source, key, None)

        if value is not None:
            return value

    return default


def _normalize_confidence(value):
    try:
        value = float(value)

        if value > 1:
            return value / 100

        return value

    except Exception:
        return 0.0


def _safe_upper(value):
    if value is None:
        return "UNKNOWN"

    return str(value).upper()


def confirm_trend(trend):
    """
    Confirms whether the detected trend is strong enough to trust.

    This does not place trades.
    It only adds another quality layer before BUY/SELL decisions.
    """

    trend_direction = _safe_upper(
        _get_value(
            trend,
            "overall_trend",
            "direction",
            "trend",
            default="UNKNOWN",
        )
    )

    trend_confidence = _normalize_confidence(
        _get_value(
            trend,
            "trend_confidence",
            "confidence",
            "strength",
            default=0,
        )
    )

    min_confidence = float(getattr(settings, "MIN_TREND_CONFIDENCE", 0.60))

    if trend_direction not in ["BULLISH", "BEARISH"]:
        return {
            "confirmed": False,
            "direction": trend_direction,
            "confidence": trend_confidence,
            "message": "Trend is not clearly bullish or bearish.",
        }

    if trend_confidence < min_confidence:
        return {
            "confirmed": False,
            "direction": trend_direction,
            "confidence": trend_confidence,
            "message": f"Trend confidence too low: {trend_confidence}. Required: {min_confidence}.",
        }

    return {
        "confirmed": True,
        "direction": trend_direction,
        "confidence": trend_confidence,
        "message": f"{trend_direction} trend confirmed.",
    }


def attach_trend_confirmation(trend, trend_confirmation):
    """
    Adds confirmation result into the trend object/dict.
    """

    if isinstance(trend, dict):
        trend["trend_confirmed"] = trend_confirmation.get("confirmed", False)
        trend["trend_confirmation_direction"] = trend_confirmation.get("direction", "UNKNOWN")
        trend["trend_confirmation_message"] = trend_confirmation.get("message", "")
        return trend

    try:
        setattr(trend, "trend_confirmed", trend_confirmation.get("confirmed", False))
        setattr(trend, "trend_confirmation_direction", trend_confirmation.get("direction", "UNKNOWN"))
        setattr(trend, "trend_confirmation_message", trend_confirmation.get("message", ""))
    except Exception:
        pass

    return trend