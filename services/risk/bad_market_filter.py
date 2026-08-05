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


def assess_bad_market_conditions(snapshot, conditions):
    """
    Checks if the market is bad enough to block BUY/SELL decisions.
    This does not place trades.
    """

    reasons = []
    block_reasons = []

    price_valid = _get_value(
        conditions,
        "price_valid",
        default=True,
    )

    candles_loaded = _get_value(
        conditions,
        "candles_loaded",
        default=True,
    )

    spread_safe = _get_value(
        conditions,
        "spread_safe",
        default=True,
    )

    session_active = _get_value(
        conditions,
        "session_active",
        "active_session",
        default=True,
    )

    trade_allowed = _get_value(
        conditions,
        "trade_allowed",
        "is_safe",
        default=True,
    )

    if price_valid:
        reasons.append("Price is valid.")
    elif getattr(settings, "BLOCK_INVALID_PRICE_TRADES", True):
        block_reasons.append("Blocked: invalid price.")

    if candles_loaded:
        reasons.append("Candles loaded.")
    elif getattr(settings, "BLOCK_MISSING_CANDLE_TRADES", True):
        block_reasons.append("Blocked: candles missing.")

    if spread_safe:
        reasons.append("Spread is safe.")
    elif getattr(settings, "BLOCK_UNSAFE_SPREAD_TRADES", True):
        block_reasons.append("Blocked: spread is unsafe.")

    if session_active:
        reasons.append("Trading session is active.")
    elif getattr(settings, "BLOCK_INACTIVE_SESSION_TRADES", True):
        block_reasons.append("Blocked: trading session is inactive.")

    if trade_allowed:
        reasons.append("Market condition checker allows trading.")
    else:
        block_reasons.append("Blocked: market condition checker does not allow trading.")

    return {
        "passed": len(block_reasons) == 0,
        "reasons": reasons,
        "block_reasons": block_reasons,
        "price_valid": price_valid,
        "candles_loaded": candles_loaded,
        "spread_safe": spread_safe,
        "session_active": session_active,
        "trade_allowed": trade_allowed,
    }