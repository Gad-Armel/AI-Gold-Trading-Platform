from collections.abc import Mapping
from typing import Any

from config import settings


# ======================================================================
# HELPERS
# ======================================================================

def _get_value(
    source: Any,
    *keys: str,
    default: Any = None,
) -> Any:
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

    value = str(value).strip().upper()
    return value or default


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
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "blocked",
            "rejected",
        }:
            return False

    if value is None:
        return default

    return bool(value)


def _normalize_confidence(
    value: Any,
) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    if confidence > 1.0:
        confidence /= 100.0

    return max(
        0.0,
        min(1.0, confidence),
    )


def _minimum_ai_confidence() -> float:
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
# DECISION EXTRACTION
# ======================================================================

def _extract_decision(
    signal_package: Any,
) -> dict[str, Any]:
    """
    Reads flattened SignalPackageState fields first while retaining
    compatibility with older nested decision objects.
    """

    nested_decision = _get_value(
        signal_package,
        "decision",
        "trade_decision",
        "decision_result",
        default={},
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


# ======================================================================
# DIRECTION HELPERS
# ======================================================================

def _decision_direction(
    action: str,
) -> str | None:
    if action in {
        "BUY",
        "BUY_READY",
        "BUY_SIGNAL",
        "READY_FOR_BUY_ANALYSIS",
        "CONFIRMED_BUY",
    }:
        return "BUY"

    if action in {
        "SELL",
        "SELL_READY",
        "SELL_SIGNAL",
        "READY_FOR_SELL_ANALYSIS",
        "CONFIRMED_SELL",
    }:
        return "SELL"

    return None


def _ai_direction(
    action: str,
) -> str | None:
    if action == "CONFIRMED_BUY":
        return "BUY"

    if action == "CONFIRMED_SELL":
        return "SELL"

    return None


def _gate_allows_dry_run(
    execution_gate: Any,
) -> bool:
    """
    A valid signal normally reaches SAFE_MODE_BLOCKED because real
    execution is disabled. That is still valid for a paper trade.

    Other gate failures remain blocking.
    """

    if execution_gate is None:
        return True

    allowed = _normalize_bool(
        _get_value(
            execution_gate,
            "allowed",
            "gate_allowed",
            default=False,
        )
    )

    if allowed:
        return True

    action = _normalize_text(
        _get_value(
            execution_gate,
            "action",
            default="",
        )
    )

    reason = str(
        _get_value(
            execution_gate,
            "reason",
            "message",
            default="",
        )
        or ""
    ).lower()

    if action in {
        "SAFE_MODE_BLOCKED",
        "LIVE_TRADING_DISABLED",
    }:
        return True

    # Compatibility with the older execution gate.
    if (
        "live trading disabled" in reason
        or "safe mode active" in reason
    ):
        return True

    return False


# ======================================================================
# RESULT BUILDER
# ======================================================================

def _build_result(
    *,
    action: str,
    direction: str,
    reason: str,
    decision: dict[str, Any],
    ai_action: str,
    ai_can_trade: bool,
    ai_confidence: float,
    gate_allowed: bool,
    gate_action: str,
    gate_reason: str,
    trade_execution: Any,
) -> dict[str, Any]:
    return {
        "action": action,
        "direction": direction,
        "reason": reason,
        "decision_action": decision["action"],
        "decision_trade_allowed": decision[
            "trade_allowed"
        ],
        "decision_confidence": decision[
            "confidence"
        ],
        "ai_action": ai_action,
        "ai_can_trade": ai_can_trade,
        "ai_confidence": ai_confidence,
        "minimum_ai_confidence": (
            _minimum_ai_confidence()
        ),
        "gate_allowed": gate_allowed,
        "gate_action": gate_action,
        "gate_reason": gate_reason,
        "trade_execution_action": _get_value(
            trade_execution,
            "action",
            default=None,
        ),
        "trade_execution_success": _normalize_bool(
            _get_value(
                trade_execution,
                "success",
                default=False,
            )
        ),
        "live_trading_enabled": bool(
            getattr(
                settings,
                "ENABLE_LIVE_TRADING",
                False,
            )
        ),
        "paper_trade_eligible": action in {
            "WOULD_BUY",
            "WOULD_SELL",
        },
    }


# ======================================================================
# DRY-RUN PLAN
# ======================================================================

def create_dry_run_trade_plan(
    signal_package: Any,
    ai_result: Any,
    execution_gate: Any = None,
    trade_execution: Any = None,
) -> dict[str, Any]:
    """
    Creates a safe simulated trade plan.

    Possible actions:
    - WOULD_BUY
    - WOULD_SELL
    - NO_TRADE
    - DRY_RUN_DISABLED

    This function never sends an MT5 order.
    """

    decision = _extract_decision(
        signal_package
    )

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
        )
    )

    ai_confidence = _normalize_confidence(
        _get_value(
            ai_result,
            "confidence",
            "ai_confidence",
            default=0.0,
        )
    )

    confirmation_filter_passed = _get_value(
        ai_result,
        "confirmation_filter_passed",
        default=None,
    )

    gate_allowed = _normalize_bool(
        _get_value(
            execution_gate,
            "allowed",
            "gate_allowed",
            default=False,
        )
    )

    gate_action = _normalize_text(
        _get_value(
            execution_gate,
            "action",
            default="NOT_PROVIDED",
        ),
        default="NOT_PROVIDED",
    )

    gate_reason = str(
        _get_value(
            execution_gate,
            "reason",
            "message",
            "gate_reason",
            default="No execution gate reason provided.",
        )
    )

    common = {
        "decision": decision,
        "ai_action": ai_action,
        "ai_can_trade": ai_can_trade,
        "ai_confidence": ai_confidence,
        "gate_allowed": gate_allowed,
        "gate_action": gate_action,
        "gate_reason": gate_reason,
        "trade_execution": trade_execution,
    }

    # ------------------------------------------------------------------
    # GLOBAL SAFETY
    # ------------------------------------------------------------------

    if getattr(
        settings,
        "EMERGENCY_STOP",
        False,
    ):
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "Emergency stop is active. "
                "Dry-run trade creation is blocked."
            ),
            **common,
        )

    if getattr(
        settings,
        "ENABLE_LIVE_TRADING",
        False,
    ):
        return _build_result(
            action="DRY_RUN_DISABLED",
            direction="NONE",
            reason=(
                "Dry-run planning is disabled because "
                "live trading is enabled."
            ),
            **common,
        )

    # ------------------------------------------------------------------
    # DECISION VALIDATION
    # ------------------------------------------------------------------

    decision_direction = _decision_direction(
        decision["action"]
    )

    if decision_direction is None:
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "Decision engine did not request "
                "a valid BUY or SELL."
            ),
            **common,
        )

    if not decision["trade_allowed"]:
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "Decision engine did not allow trading."
            ),
            **common,
        )

    # ------------------------------------------------------------------
    # AI VALIDATION
    # ------------------------------------------------------------------

    if not ai_can_trade:
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                f"AI did not approve trading. "
                f"AI action: {ai_action}."
            ),
            **common,
        )

    ai_direction = _ai_direction(
        ai_action
    )

    if ai_direction is None:
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "AI did not return CONFIRMED_BUY "
                "or CONFIRMED_SELL."
            ),
            **common,
        )

    if ai_confidence < _minimum_ai_confidence():
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "AI confidence is below the required "
                f"minimum. Confidence: {ai_confidence:.4f}. "
                f"Required: {_minimum_ai_confidence():.4f}."
            ),
            **common,
        )

    if (
        confirmation_filter_passed is not None
        and not _normalize_bool(
            confirmation_filter_passed
        )
    ):
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "AI confirmation filter did not pass."
            ),
            **common,
        )

    if decision_direction != ai_direction:
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "Decision and AI directions do not match. "
                f"Decision: {decision_direction}. "
                f"AI: {ai_direction}."
            ),
            **common,
        )

    # ------------------------------------------------------------------
    # EXECUTION-GATE VALIDATION
    # ------------------------------------------------------------------

    if not _gate_allows_dry_run(
        execution_gate
    ):
        return _build_result(
            action="NO_TRADE",
            direction="NONE",
            reason=(
                "Execution gate blocked the signal for "
                f"a reason other than safe mode: {gate_reason}"
            ),
            **common,
        )

    # ------------------------------------------------------------------
    # APPROVED PAPER PLAN
    # ------------------------------------------------------------------

    if decision_direction == "BUY":
        return _build_result(
            action="WOULD_BUY",
            direction="BUY",
            reason=(
                "Decision and AI confirmed BUY. "
                "A simulated BUY may be opened."
            ),
            **common,
        )

    return _build_result(
        action="WOULD_SELL",
        direction="SELL",
        reason=(
            "Decision and AI confirmed SELL. "
            "A simulated SELL may be opened."
        ),
        **common,
    )


def build_dry_run_trade_plan(
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Backward-compatible alias.
    """

    return create_dry_run_trade_plan(
        *args,
        **kwargs,
    )