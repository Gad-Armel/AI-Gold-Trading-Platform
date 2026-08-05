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


def _extract_mid_price(price_data):
    if price_data is None:
        return None

    if isinstance(price_data, (int, float)):
        return float(price_data)

    if isinstance(price_data, dict):
        bid = price_data.get("bid")
        ask = price_data.get("ask")

        try:
            if bid is not None and ask is not None:
                return round((float(bid) + float(ask)) / 2, 3)
        except Exception:
            return None

        for key in ["price", "current_price", "last", "close"]:
            value = price_data.get(key)
            if value is not None:
                try:
                    return float(value)
                except Exception:
                    pass

    try:
        return float(price_data)
    except Exception:
        return None


def _extract_snapshot_price(snapshot):
    price_data = _get_value(
        snapshot,
        "price",
        "current_price",
        default=None,
    )

    return _extract_mid_price(price_data)


def evaluate_slippage_guard(snapshot, latest_price_data):
    """
    Checks price movement between snapshot price and latest execution price.

    This does not place trades.
    It only blocks unsafe execution if price moved too much.
    """

    snapshot_price = _extract_snapshot_price(snapshot)
    latest_price = _extract_mid_price(latest_price_data)

    max_slippage = float(getattr(settings, "MAX_SLIPPAGE_USD", 0.50))
    block_on_error = bool(getattr(settings, "BLOCK_ON_SLIPPAGE_CHECK_ERROR", True))

    if snapshot_price is None or latest_price is None:
        allowed = not block_on_error

        return {
            "allowed": allowed,
            "action": "SLIPPAGE_CHECK_FAILED",
            "snapshot_price": snapshot_price,
            "latest_price": latest_price,
            "slippage": None,
            "max_slippage": max_slippage,
            "message": "Slippage check failed because a price was missing.",
            "block_reasons": ["Missing snapshot price or latest price."] if not allowed else [],
        }

    slippage = abs(latest_price - snapshot_price)

    if slippage > max_slippage:
        return {
            "allowed": False,
            "action": "SLIPPAGE_BLOCKED",
            "snapshot_price": snapshot_price,
            "latest_price": latest_price,
            "slippage": round(slippage, 3),
            "max_slippage": max_slippage,
            "message": "Trade blocked because slippage is too high.",
            "block_reasons": [
                f"Slippage too high: {round(slippage, 3)} > {max_slippage}"
            ],
        }

    return {
        "allowed": True,
        "action": "SLIPPAGE_ALLOWED",
        "snapshot_price": snapshot_price,
        "latest_price": latest_price,
        "slippage": round(slippage, 3),
        "max_slippage": max_slippage,
        "message": "Slippage check passed.",
        "block_reasons": [],
    }


def apply_slippage_guard_to_ai(ai_result, slippage_result):
    """
    If slippage is unsafe, force AI result to NO_TRADE.
    """

    if slippage_result.get("allowed", False):
        return ai_result

    return {
        "action": "NO_TRADE",
        "can_trade": False,
        "confidence": 0.0,
        "reason": "Slippage guard blocked trading.",
        "original_ai_result": ai_result,
        "slippage_block_reasons": slippage_result.get("block_reasons", []),
    }