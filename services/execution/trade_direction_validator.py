def _get(obj, key, default=None):
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def _get_decision_action(signal_package):
    decision_obj = _get(signal_package, "decision")

    action = _get(decision_obj, "action")
    if action:
        return action

    decision = _get(decision_obj, "decision")
    if decision:
        return decision

    return "UNKNOWN"


def _get_ai_action(ai_result):
    action = _get(ai_result, "ai_action")
    if action:
        return action

    action = _get(ai_result, "action")
    if action:
        return action

    return "UNKNOWN"


def validate_trade_direction(signal_package, ai_result):
    """
    Confirms that AI direction matches the original decision engine direction.

    BUY is allowed only when:
    - decision engine requested BUY analysis
    - AI confirmed BUY

    SELL is allowed only when:
    - decision engine requested SELL analysis
    - AI confirmed SELL
    """

    decision_action = _get_decision_action(signal_package)
    ai_action = _get_ai_action(ai_result)

    buy_decisions = [
        "READY_FOR_BUY_ANALYSIS",
        "BUY_ANALYSIS",
        "BUY",
    ]

    sell_decisions = [
        "READY_FOR_SELL_ANALYSIS",
        "SELL_ANALYSIS",
        "SELL",
    ]

    if ai_action == "CONFIRMED_BUY":
        if decision_action in buy_decisions:
            return {
                "valid": True,
                "direction": "BUY",
                "reason": "BUY direction validated.",
            }

        return {
            "valid": False,
            "direction": "NONE",
            "reason": (
                f"BUY rejected. AI said CONFIRMED_BUY, "
                f"but decision engine action was {decision_action}."
            ),
        }

    if ai_action == "CONFIRMED_SELL":
        if decision_action in sell_decisions:
            return {
                "valid": True,
                "direction": "SELL",
                "reason": "SELL direction validated.",
            }

        return {
            "valid": False,
            "direction": "NONE",
            "reason": (
                f"SELL rejected. AI said CONFIRMED_SELL, "
                f"but decision engine action was {decision_action}."
            ),
        }

    return {
        "valid": False,
        "direction": "NONE",
        "reason": f"No tradable AI action found: {ai_action}.",
    }