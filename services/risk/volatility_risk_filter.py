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


def _safe_upper(value):
    if value is None:
        return "UNKNOWN"

    return str(value).upper()


def assess_volatility_risk(volatility):
    """
    Decides if volatility is tradable or dangerous.

    LOW / NORMAL / MEDIUM = tradable
    HIGH = caution
    EXTREME = blocked
    UNKNOWN = blocked if setting says so
    """

    level = _safe_upper(
        _get_value(
            volatility,
            "overall_volatility",
            "level",
            "risk_level",
            default="UNKNOWN",
        )
    )

    reasons = []
    block_reasons = []

    if level in ["LOW", "NORMAL", "MEDIUM"]:
        reasons.append(f"Volatility is tradable: {level}.")

    elif level == "HIGH":
        if getattr(settings, "BLOCK_HIGH_VOLATILITY_TRADES", False):
            block_reasons.append("Blocked: volatility is HIGH.")
        else:
            reasons.append("Volatility is HIGH. Trade allowed but caution required.")

    elif level == "EXTREME":
        if getattr(settings, "BLOCK_EXTREME_VOLATILITY_TRADES", True):
            block_reasons.append("Blocked: volatility is EXTREME.")
        else:
            reasons.append("Volatility is EXTREME but blocking is disabled.")

    else:
        if getattr(settings, "BLOCK_UNKNOWN_VOLATILITY_TRADES", True):
            block_reasons.append(f"Blocked: volatility is unknown: {level}.")
        else:
            reasons.append(f"Unknown volatility allowed: {level}.")

    return {
        "passed": len(block_reasons) == 0,
        "volatility_level": level,
        "reasons": reasons,
        "block_reasons": block_reasons,
    }