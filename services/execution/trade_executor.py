
from collections.abc import Mapping
from typing import Any

from config import settings

from services.execution.order_manager import (
    open_buy,
    open_sell,
)


# ======================================================================
# SAFE VALUE HELPERS
# ======================================================================

def _get_value(
    source: Any,
    *keys: str,
    default: Any = None,
) -> Any:
    """
    Returns the first available value from a dictionary or object.
    """

    if source is None:
        return default

    for key in keys:
        if isinstance(source, Mapping):
            value = source.get(key)
        else:
            value = getattr(source, key, None)

        if value is not None:
            return value

    return default


def _normalize_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    normalized = str(value).strip().upper()
    return normalized or default


def _normalize_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "yes",
            "1",
            "allowed",
            "approved",
            "success",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "blocked",
            "rejected",
            "failed",
        }:
            return False

    if value is None:
        return default

    return bool(value)


def _normalize_confidence(
    value: Any,
) -> float:
    """
    Normalizes confidence into the 0.0–1.0 range.
    """

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    if confidence > 1.0:
        confidence = confidence / 100.0

    return max(
        0.0,
        min(1.0, confidence),
    )


def _get_minimum_ai_confidence() -> float:
    try:
        minimum = float(
            getattr(
                settings,
                "MIN_AI_CONFIDENCE",
                0.60,
            )
        )
    except (TypeError, ValueError):
        minimum = 0.60

    return max(
        0.0,
        min(1.0, minimum),
    )


# ======================================================================
# SIGNAL EXTRACTION
# ======================================================================

def _get_nested_decision(
    signal_package: Any,
) -> Any:
    """
    Supports older signal packages containing a nested decision.
    """

    return _get_value(
        signal_package,
        "decision",
        "trade_decision",
        "decision_result",
        default={},
    )


def _extract_decision_data(
    signal_package: Any,
) -> dict[str, Any]:
    """
    Reads the current flattened SignalPackageState fields first.

    Current fields:
    - decision_action
    - decision_trade_allowed
    - decision_confidence
    """

    nested_decision = _get_nested_decision(
        signal_package
    )

    action = _get_value(
        signal_package,
        "decision_action",
        default=None,
    )

    if action is None:
        action = _get_value(
            nested_decision,
            "action",
            "decision",
            "trade_action",
            default="WAIT",
        )

    trade_allowed = _get_value(
        signal_package,
        "decision_trade_allowed",
        default=None,
    )

    if trade_allowed is None:
        trade_allowed = _get_value(
            nested_decision,
            "trade_allowed",
            "can_trade",
            "allowed",
            default=False,
        )

    confidence = _get_value(
        signal_package,
        "decision_confidence",
        default=None,
    )

    if confidence is None:
        confidence = _get_value(
            nested_decision,
            "confidence",
            "decision_confidence",
            default=0.0,
        )

    return {
        "action": _normalize_text(
            action,
            default="WAIT",
        ),
        "trade_allowed": _normalize_bool(
            trade_allowed,
            default=False,
        ),
        "confidence": _normalize_confidence(
            confidence
        ),
    }


def _extract_symbol(
    signal_package: Any,
) -> str:
    symbol = _get_value(
        signal_package,
        "symbol",
        default=None,
    )

    if symbol:
        return _normalize_text(symbol)

    snapshot = _get_value(
        signal_package,
        "snapshot",
        "market_snapshot",
        default={},
    )

    return _normalize_text(
        _get_value(
            snapshot,
            "symbol",
            default=getattr(
                settings,
                "SYMBOL",
                "XAUUSD",
            ),
        ),
        default="XAUUSD",
    )


# ======================================================================
# DIRECTION VALIDATION
# ======================================================================

def _get_decision_direction(
    action: str,
) -> str | None:
    buy_actions = {
        "BUY",
        "BUY_READY",
        "BUY_SIGNAL",
        "READY_FOR_BUY_ANALYSIS",
        "CONFIRMED_BUY",
    }

    sell_actions = {
        "SELL",
        "SELL_READY",
        "SELL_SIGNAL",
        "READY_FOR_SELL_ANALYSIS",
        "CONFIRMED_SELL",
    }

    if action in buy_actions:
        return "BUY"

    if action in sell_actions:
        return "SELL"

    return None


def _get_ai_direction(
    ai_action: str,
) -> str | None:
    if ai_action == "CONFIRMED_BUY":
        return "BUY"

    if ai_action == "CONFIRMED_SELL":
        return "SELL"

    return None


def _resolve_trade_direction(
    decision_action: str,
    ai_action: str,
    execution_gate: Any,
) -> str | None:
    decision_direction = _get_decision_direction(
        decision_action
    )

    ai_direction = _get_ai_direction(
        ai_action
    )

    gate_direction = _normalize_text(
        _get_value(
            execution_gate,
            "direction",
            default="",
        )
    )

    if decision_direction is None:
        return None

    if ai_direction is None:
        return None

    if decision_direction != ai_direction:
        return None

    if gate_direction and gate_direction not in {
        "BUY",
        "SELL",
    }:
        return None

    if (
        gate_direction
        and gate_direction != decision_direction
    ):
        return None

    return decision_direction


# ======================================================================
# RESULT BUILDERS
# ======================================================================

def _no_execution_result(
    *,
    action: str,
    message: str,
    symbol: str,
    direction: str | None,
    gate_allowed: bool,
    gate_action: str,
    gate_reason: str,
    attempted: bool = False,
    **extra_fields: Any,
) -> dict[str, Any]:
    result = {
        "attempted": attempted,
        "success": False,
        "action": action,
        "direction": direction or "NONE",
        "symbol": symbol,
        "message": message,
        "gate_allowed": gate_allowed,
        "gate_action": gate_action,
        "gate_reason": gate_reason,
    }

    result.update(extra_fields)

    return result


# ======================================================================
# LOT-SIZE VALIDATION
# ======================================================================

def _get_lot_size() -> float | None:
    try:
        lot_size = float(
            getattr(
                settings,
                "LOT_SIZE",
                0.01,
            )
        )
    except (TypeError, ValueError):
        return None

    if lot_size <= 0:
        return None

    return lot_size


# ======================================================================
# LIVE-READINESS DEFENSE-IN-DEPTH
# ======================================================================

def _verify_live_readiness(
    symbol: str,
) -> dict[str, Any]:
    """
    Rechecks live readiness immediately before sending an MT5 order.

    The execution gate already performs this check. Repeating it here
    protects against direct or accidental calls to the trade executor.
    """

    if (
        getattr(
            settings,
            "REQUIRE_LIVE_READINESS_BEFORE_TRADING",
            True,
        )
        is not True
    ):
        return {
            "allowed": True,
            "message": (
                "Live-readiness requirement is disabled."
            ),
            "blockers": [],
        }

    try:
        from services.bot.live_readiness_checker import (
            check_live_readiness,
        )

        readiness = check_live_readiness(symbol)

        if not isinstance(readiness, Mapping):
            return {
                "allowed": False,
                "message": (
                    "Live-readiness checker returned an "
                    "invalid result."
                ),
                "blockers": [
                    "Invalid live-readiness response."
                ],
            }

        if readiness.get(
            "ready_for_review",
            False,
        ):
            return {
                "allowed": True,
                "message": "Live-readiness check passed.",
                "blockers": [],
                "readiness": dict(readiness),
            }

        blockers = readiness.get(
            "blockers",
            [],
        )

        if not isinstance(blockers, list):
            blockers = [str(blockers)]

        return {
            "allowed": False,
            "message": "Live-readiness check failed.",
            "blockers": blockers,
            "readiness": dict(readiness),
        }

    except Exception as error:
        return {
            "allowed": False,
            "message": (
                f"Live-readiness check failed: {error}"
            ),
            "blockers": [str(error)],
        }


# ======================================================================
# MT5 RESULT INTERPRETATION
# ======================================================================

def _get_successful_mt5_retcodes() -> set[int]:
    """
    Reads successful trade return codes from the installed MT5 package.

    No network request is made.
    """

    try:
        import MetaTrader5 as mt5

        names = (
            "TRADE_RETCODE_PLACED",
            "TRADE_RETCODE_DONE",
            "TRADE_RETCODE_DONE_PARTIAL",
        )

        return {
            int(getattr(mt5, name))
            for name in names
            if hasattr(mt5, name)
        }

    except Exception:
        return set()


def _interpret_order_result(
    order_result: Any,
) -> dict[str, Any]:
    """
    Determines whether MT5 actually accepted the order.

    A returned object is not automatically treated as successful.
    """

    if order_result is None:
        return {
            "success": False,
            "message": (
                "Order manager returned no MT5 result."
            ),
            "retcode": None,
        }

    explicit_success = _get_value(
        order_result,
        "success",
        "trade_success",
        "accepted",
        default=None,
    )

    retcode = _get_value(
        order_result,
        "retcode",
        "return_code",
        default=None,
    )

    comment = _get_value(
        order_result,
        "comment",
        "message",
        "reason",
        "error",
        default="",
    )

    if explicit_success is not None:
        success = _normalize_bool(
            explicit_success,
            default=False,
        )

        return {
            "success": success,
            "message": (
                str(comment)
                if comment
                else (
                    "MT5 order accepted."
                    if success
                    else "MT5 order rejected."
                )
            ),
            "retcode": retcode,
        }

    if retcode is not None:
        try:
            numeric_retcode = int(retcode)
        except (TypeError, ValueError):
            return {
                "success": False,
                "message": (
                    "MT5 returned an invalid trade retcode."
                ),
                "retcode": retcode,
            }

        successful_codes = (
            _get_successful_mt5_retcodes()
        )

        if not successful_codes:
            return {
                "success": False,
                "message": (
                    "Unable to verify the MT5 trade retcode."
                ),
                "retcode": numeric_retcode,
            }

        success = (
            numeric_retcode in successful_codes
        )

        return {
            "success": success,
            "message": (
                str(comment)
                if comment
                else (
                    "MT5 accepted the order."
                    if success
                    else (
                        "MT5 rejected the order with "
                        f"retcode {numeric_retcode}."
                    )
                )
            ),
            "retcode": numeric_retcode,
        }

    if isinstance(order_result, bool):
        return {
            "success": order_result,
            "message": (
                "Order manager reported success."
                if order_result
                else "Order manager reported failure."
            ),
            "retcode": None,
        }

    return {
        "success": False,
        "message": (
            "Order manager returned an unrecognized "
            "result, so success could not be verified."
        ),
        "retcode": None,
    }


# ======================================================================
# TRADE EXECUTOR
# ======================================================================

def execute_trade_from_gate(
    signal_package: Any,
    execution_gate: Any,
    ai_result: Any = None,
) -> dict[str, Any]:
    """
    Sends an MT5 order only after all safety checks pass.

    Defense-in-depth checks:
    - execution gate approval;
    - recognized gate action;
    - emergency stop;
    - valid decision permission;
    - AI permission and direction;
    - minimum AI confidence;
    - safe-mode status;
    - exact live-risk confirmation;
    - live-readiness verification;
    - valid symbol, direction, and lot size;
    - actual MT5 response validation.

    With ENABLE_LIVE_TRADING=False, no MT5 order is sent.
    """

    if ai_result is None:
        ai_result = {}

    decision = _extract_decision_data(
        signal_package
    )

    decision_action = decision["action"]
    decision_trade_allowed = decision[
        "trade_allowed"
    ]
    decision_confidence = decision[
        "confidence"
    ]

    ai_action = _normalize_text(
        _get_value(
            ai_result,
            "action",
            "ai_action",
            default="NO_TRADE",
        ),
        default="NO_TRADE",
    )

    ai_can_trade = _normalize_bool(
        _get_value(
            ai_result,
            "can_trade",
            "trade_allowed",
            default=False,
        ),
        default=False,
    )

    ai_confidence = _normalize_confidence(
        _get_value(
            ai_result,
            "confidence",
            "ai_confidence",
            default=0.0,
        )
    )

    gate_allowed = _normalize_bool(
        _get_value(
            execution_gate,
            "allowed",
            "gate_allowed",
            "can_execute",
            default=False,
        ),
        default=False,
    )

    gate_action = _normalize_text(
        _get_value(
            execution_gate,
            "action",
            default="",
        )
    )

    gate_reason = str(
        _get_value(
            execution_gate,
            "reason",
            "message",
            "gate_reason",
            default="No gate reason provided.",
        )
    )

    symbol = _extract_symbol(
        signal_package
    )

    direction = _resolve_trade_direction(
        decision_action=decision_action,
        ai_action=ai_action,
        execution_gate=execution_gate,
    )

    minimum_ai_confidence = (
        _get_minimum_ai_confidence()
    )

    # ==================================================================
    # EXECUTION GATE
    # ==================================================================

    if not gate_allowed:
        return _no_execution_result(
            action="NO_EXECUTION",
            message=(
                "Execution gate blocked the trade. "
                f"Reason: {gate_reason}"
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            decision_action=decision_action,
            ai_action=ai_action,
        )

    if (
        gate_action
        and gate_action != "ALLOWED"
    ):
        return _no_execution_result(
            action="INVALID_GATE_APPROVAL",
            message=(
                "Execution gate reported allowed=True, "
                f"but its action was {gate_action}."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
        )

    # ==================================================================
    # EMERGENCY STOP
    # ==================================================================

    if (
        getattr(
            settings,
            "EMERGENCY_STOP",
            False,
        )
        is True
    ):
        return _no_execution_result(
            action="EMERGENCY_STOP_BLOCKED",
            message=(
                "Emergency stop is active. "
                "No MT5 order was sent."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
        )

    # ==================================================================
    # DECISION AND AI REVALIDATION
    # ==================================================================

    if not decision_trade_allowed:
        return _no_execution_result(
            action="DECISION_PERMISSION_BLOCKED",
            message=(
                "Decision engine did not allow trading."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            decision_action=decision_action,
            decision_confidence=decision_confidence,
        )

    if not ai_can_trade:
        return _no_execution_result(
            action="AI_PERMISSION_BLOCKED",
            message="AI did not allow trading.",
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            ai_action=ai_action,
            ai_confidence=ai_confidence,
        )

    if ai_confidence < minimum_ai_confidence:
        return _no_execution_result(
            action="AI_CONFIDENCE_BLOCKED",
            message=(
                "AI confidence is below the required "
                f"minimum. Confidence: {ai_confidence:.4f}. "
                f"Required: {minimum_ai_confidence:.4f}."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            ai_action=ai_action,
            ai_confidence=ai_confidence,
        )

    if direction not in {"BUY", "SELL"}:
        return _no_execution_result(
            action="INVALID_DIRECTION",
            message=(
                "Decision, AI, and execution-gate "
                "directions did not produce one matching "
                "BUY or SELL direction."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            decision_action=decision_action,
            ai_action=ai_action,
        )

    # ==================================================================
    # SAFE MODE
    # ==================================================================

    if (
        getattr(
            settings,
            "ENABLE_LIVE_TRADING",
            False,
        )
        is not True
    ):
        return _no_execution_result(
            action="LIVE_TRADING_DISABLED",
            message=(
                "Live trading is disabled. "
                "No MT5 order was sent."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            safe_mode=True,
        )

    # ==================================================================
    # EXACT LIVE CONFIRMATION
    # ==================================================================

    live_confirmation = str(
        getattr(
            settings,
            "LIVE_TRADING_CONFIRMATION",
            "",
        )
        or ""
    )

    required_confirmation = str(
        getattr(
            settings,
            "REQUIRED_LIVE_TRADING_CONFIRMATION",
            "I_ACCEPT_LIVE_TRADING_RISK",
        )
        or ""
    )

    if (
        not required_confirmation
        or live_confirmation
        != required_confirmation
    ):
        return _no_execution_result(
            action="LIVE_CONFIRMATION_MISSING",
            message=(
                "Live-trading confirmation is missing "
                "or invalid. No MT5 order was sent."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
        )

    # ==================================================================
    # LIVE READINESS
    # ==================================================================

    readiness = _verify_live_readiness(
        symbol
    )

    if not readiness.get(
        "allowed",
        False,
    ):
        return _no_execution_result(
            action="LIVE_READINESS_BLOCKED",
            message=readiness.get(
                "message",
                "Live-readiness check failed.",
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            live_readiness_blockers=readiness.get(
                "blockers",
                [],
            ),
            live_readiness=readiness.get(
                "readiness",
                {},
            ),
        )

    # ==================================================================
    # ORDER PARAMETERS
    # ==================================================================

    if not symbol:
        return _no_execution_result(
            action="INVALID_SYMBOL",
            message=(
                "Trading symbol is missing or invalid."
            ),
            symbol="UNKNOWN",
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
        )

    lot_size = _get_lot_size()

    if lot_size is None:
        return _no_execution_result(
            action="INVALID_LOT_SIZE",
            message=(
                "LOT_SIZE must be a positive number. "
                "No MT5 order was sent."
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
        )

    # ==================================================================
    # MT5 ORDER ATTEMPT
    # ==================================================================

    try:
        if direction == "BUY":
            mt5_result = open_buy(
                symbol,
                lot_size,
            )
        else:
            mt5_result = open_sell(
                symbol,
                lot_size,
            )

    except Exception as error:
        return _no_execution_result(
            action="TRADE_EXCEPTION",
            message=(
                f"MT5 order attempt raised an error: {error}"
            ),
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            attempted=True,
            lot_size=lot_size,
            exception_type=type(error).__name__,
        )

    # ==================================================================
    # VERIFY ACTUAL MT5 RESPONSE
    # ==================================================================

    interpretation = _interpret_order_result(
        mt5_result
    )

    order_success = interpretation[
        "success"
    ]

    if not order_success:
        return _no_execution_result(
            action="TRADE_REJECTED",
            message=interpretation["message"],
            symbol=symbol,
            direction=direction,
            gate_allowed=gate_allowed,
            gate_action=gate_action,
            gate_reason=gate_reason,
            attempted=True,
            lot_size=lot_size,
            mt5_retcode=interpretation.get(
                "retcode"
            ),
            mt5_result=mt5_result,
        )

    return {
        "attempted": True,
        "success": True,
        "action": "TRADE_SENT",
        "direction": direction,
        "symbol": symbol,
        "lot_size": lot_size,
        "message": interpretation["message"],
        "gate_allowed": gate_allowed,
        "gate_action": gate_action,
        "gate_reason": gate_reason,
        "decision_action": decision_action,
        "decision_confidence": decision_confidence,
        "ai_action": ai_action,
        "ai_confidence": ai_confidence,
        "mt5_retcode": interpretation.get(
            "retcode"
        ),
        "mt5_result": mt5_result,
    }

