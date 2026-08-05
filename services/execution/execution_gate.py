
from collections.abc import Mapping
from typing import Any

from config import settings


# ======================================================================
# SAFE VALUE HELPERS
# ======================================================================

def _get_value(
    source: Any,
    *keys: str,
    default: Any = None,
) -> Any:
    """
    Returns the first available field from a dictionary or object.
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
    """
    Normalizes confidence to the 0.0–1.0 range.

    Supports values such as:
    - 0.75
    - 75
    - "75"
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


def _to_reason_list(
    value: Any,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    text = str(value).strip()

    if text:
        return [text]

    return []


# ======================================================================
# SIGNAL-PACKAGE EXTRACTION
# ======================================================================

def _get_nested_decision(
    signal_package: Any,
) -> Any:
    """
    Supports older signal packages containing a nested decision object.
    """

    return _get_value(
        signal_package,
        "decision",
        "trade_decision",
        "decision_result",
        default={},
    )


def _extract_decision(
    signal_package: Any,
) -> dict[str, Any]:
    """
    Reads the current flattened SignalPackageState fields first.

    Current fields:
    - decision_action
    - decision_trade_allowed
    - decision_confidence

    Older nested-decision formats remain supported.
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


# ======================================================================
# DIRECTION HELPERS
# ======================================================================

def _get_decision_direction(
    decision_action: str,
) -> str | None:
    buy_actions = {
        "BUY",
        "READY_FOR_BUY_ANALYSIS",
        "BUY_READY",
        "BUY_SIGNAL",
        "CONFIRMED_BUY",
    }

    sell_actions = {
        "SELL",
        "READY_FOR_SELL_ANALYSIS",
        "SELL_READY",
        "SELL_SIGNAL",
        "CONFIRMED_SELL",
    }

    if decision_action in buy_actions:
        return "BUY"

    if decision_action in sell_actions:
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


# ======================================================================
# GATE RESULT BUILDERS
# ======================================================================

def _blocked_result(
    action: str,
    reason: str,
    decision_action: str,
    decision_trade_allowed: bool,
    decision_confidence: float,
    ai_action: str,
    ai_can_trade: bool,
    ai_confidence: float,
    block_reasons: list[str] | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    result = {
        "allowed": False,
        "action": action,
        "reason": reason,
        "decision_action": decision_action,
        "decision_trade_allowed": decision_trade_allowed,
        "decision_confidence": decision_confidence,
        "ai_action": ai_action,
        "ai_can_trade": ai_can_trade,
        "ai_confidence": ai_confidence,
        "block_reasons": block_reasons or [reason],
    }

    result.update(extra_fields)

    return result


def _allowed_result(
    decision_action: str,
    decision_trade_allowed: bool,
    decision_confidence: float,
    ai_action: str,
    ai_can_trade: bool,
    ai_confidence: float,
    direction: str,
) -> dict[str, Any]:
    return {
        "allowed": True,
        "action": "ALLOWED",
        "reason": (
            "Execution gate approved the trade after all "
            "decision, AI, safety, confirmation, and live-readiness "
            "checks passed."
        ),
        "direction": direction,
        "decision_action": decision_action,
        "decision_trade_allowed": decision_trade_allowed,
        "decision_confidence": decision_confidence,
        "ai_action": ai_action,
        "ai_can_trade": ai_can_trade,
        "ai_confidence": ai_confidence,
        "block_reasons": [],
    }


# ======================================================================
# LIVE-READINESS PROTECTION
# ======================================================================

def _check_live_readiness_if_required(
    symbol: str,
) -> dict[str, Any]:
    """
    Blocks live execution unless the live-readiness checker passes.

    This check is only reached after live trading has been explicitly
    enabled and all earlier safety requirements have passed.
    """

    requirement_enabled = (
        getattr(
            settings,
            "REQUIRE_LIVE_READINESS_BEFORE_TRADING",
            True,
        )
        is True
    )

    if not requirement_enabled:
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
                    "Invalid live-readiness result."
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

        blockers = _to_reason_list(
            readiness.get(
                "blockers",
                [],
            )
        )

        if not blockers:
            blockers = [
                "Live-readiness requirements have not been met."
            ]

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
                f"Live-readiness check error: {error}"
            ),
            "blockers": [str(error)],
        }


# ======================================================================
# EXECUTION GATE
# ======================================================================

def evaluate_execution_gate(
    signal_package: Any,
    ai_result: Any,
) -> dict[str, Any]:
    """
    Final safety gate before the trade executor.

    Required conditions:
    - emergency stop is clear;
    - decision requested a recognized BUY or SELL;
    - decision engine allowed trading;
    - AI returned CONFIRMED_BUY or CONFIRMED_SELL;
    - AI explicitly allowed trading;
    - AI direction matches the decision direction;
    - AI confidence meets the configured minimum;
    - live trading is explicitly enabled;
    - live confirmation text is exact;
    - live-readiness check passes.

    In the current safe configuration, ENABLE_LIVE_TRADING=False,
    so real execution remains blocked.
    """

    decision = _extract_decision(
        signal_package
    )

    decision_action = decision["action"]
    decision_trade_allowed = decision[
        "trade_allowed"
    ]
    decision_confidence = decision[
        "confidence"
    ]

    decision_direction = (
        _get_decision_direction(
            decision_action
        )
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

    ai_direction = _get_ai_direction(
        ai_action
    )

    minimum_ai_confidence = (
        _get_minimum_ai_confidence()
    )

    symbol = _normalize_text(
        _get_value(
            signal_package,
            "symbol",
            default=getattr(
                settings,
                "SYMBOL",
                "XAUUSD",
            ),
        ),
        default="XAUUSD",
    )

    # ==================================================================
    # EMERGENCY STOP — HIGHEST PRIORITY
    # ==================================================================

    if (
        getattr(
            settings,
            "EMERGENCY_STOP",
            False,
        )
        is True
    ):
        return _blocked_result(
            action="EMERGENCY_STOP_BLOCKED",
            reason=(
                "Emergency stop is active. All trade execution "
                "is blocked."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
        )

    # ==================================================================
    # DECISION VALIDATION
    # ==================================================================

    if decision_direction is None:
        return _blocked_result(
            action="DECISION_BLOCKED",
            reason=(
                "Decision did not request a recognized BUY or SELL."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
        )

    if not decision_trade_allowed:
        return _blocked_result(
            action="DECISION_BLOCKED",
            reason=(
                "Decision engine did not allow trading."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
        )

    # ==================================================================
    # AI VALIDATION
    # ==================================================================

    if not ai_can_trade:
        return _blocked_result(
            action="AI_BLOCKED",
            reason="AI did not approve trading.",
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
            block_reasons=_to_reason_list(
                _get_value(
                    ai_result,
                    "block_reasons",
                    default=[],
                )
            )
            or ["AI did not approve trading."],
        )

    if ai_direction is None:
        return _blocked_result(
            action="AI_ACTION_BLOCKED",
            reason=(
                "AI did not return CONFIRMED_BUY or "
                "CONFIRMED_SELL."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
        )

    if ai_confidence < minimum_ai_confidence:
        return _blocked_result(
            action="AI_CONFIDENCE_BLOCKED",
            reason=(
                "AI confidence is too low. "
                f"Confidence: {ai_confidence:.4f}. "
                f"Required: {minimum_ai_confidence:.4f}."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
            minimum_ai_confidence=minimum_ai_confidence,
        )

    if decision_direction != ai_direction:
        return _blocked_result(
            action="DIRECTION_MISMATCH_BLOCKED",
            reason=(
                "Decision and AI directions do not match. "
                f"Decision: {decision_direction}. "
                f"AI: {ai_direction}."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
            decision_direction=decision_direction,
            ai_direction=ai_direction,
        )

    confirmation_filter_passed = _get_value(
        ai_result,
        "confirmation_filter_passed",
        default=None,
    )

    if (
        confirmation_filter_passed is not None
        and not _normalize_bool(
            confirmation_filter_passed,
            default=False,
        )
    ):
        return _blocked_result(
            action="AI_CONFIRMATION_FILTER_BLOCKED",
            reason=(
                "AI confirmation filter did not pass."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
            block_reasons=_to_reason_list(
                _get_value(
                    ai_result,
                    "block_reasons",
                    default=[],
                )
            )
            or [
                "AI confirmation filter did not pass."
            ],
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
        return _blocked_result(
            action="SAFE_MODE_BLOCKED",
            reason=(
                "Live trading is disabled. Safe mode is active."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
            decision_direction=decision_direction,
            ai_direction=ai_direction,
            safe_mode=True,
        )

    # ==================================================================
    # LIVE CONFIRMATION
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
        return _blocked_result(
            action="LIVE_CONFIRMATION_BLOCKED",
            reason=(
                "Live-trading confirmation is missing or invalid."
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
        )

    # ==================================================================
    # LIVE READINESS
    # ==================================================================

    readiness_result = (
        _check_live_readiness_if_required(
            symbol
        )
    )

    if not readiness_result.get(
        "allowed",
        False,
    ):
        blockers = _to_reason_list(
            readiness_result.get(
                "blockers",
                [],
            )
        )

        return _blocked_result(
            action="LIVE_READINESS_BLOCKED",
            reason=readiness_result.get(
                "message",
                "Live-readiness check failed.",
            ),
            decision_action=decision_action,
            decision_trade_allowed=decision_trade_allowed,
            decision_confidence=decision_confidence,
            ai_action=ai_action,
            ai_can_trade=ai_can_trade,
            ai_confidence=ai_confidence,
            block_reasons=blockers,
            live_readiness_blockers=blockers,
            live_readiness=readiness_result.get(
                "readiness",
                {},
            ),
        )

    # ==================================================================
    # FINAL APPROVAL
    # ==================================================================

    return _allowed_result(
        decision_action=decision_action,
        decision_trade_allowed=decision_trade_allowed,
        decision_confidence=decision_confidence,
        ai_action=ai_action,
        ai_can_trade=ai_can_trade,
        ai_confidence=ai_confidence,
        direction=decision_direction,
    )

