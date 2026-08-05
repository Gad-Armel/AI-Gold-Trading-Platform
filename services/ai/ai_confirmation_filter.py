
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

    return str(value).strip().upper()


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
    Normalizes confidence into the 0.0–1.0 range.

    Supports:
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


def _get_minimum_confidence() -> float:
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


def _deduplicate_reasons(
    reasons: list[Any],
) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for reason in reasons:
        text = str(reason).strip()

        if not text:
            continue

        if text not in seen:
            cleaned.append(text)
            seen.add(text)

    return cleaned


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
# AI CONFIRMATION FILTER
# ======================================================================

def apply_ai_confirmation_filter(
    decision: Any,
    ai_result: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Applies the final AI confirmation safety filter.

    A trade passes only when:
    - the decision engine requested BUY or SELL;
    - the decision engine allowed trading;
    - the AI explicitly allowed trading;
    - the AI returned CONFIRMED_BUY or CONFIRMED_SELL;
    - the AI direction matches the decision direction;
    - AI confidence meets the configured minimum.

    This filter never places a trade directly.
    """

    decision_action = _normalize_text(
        _get_value(
            decision,
            "action",
            "decision",
            "trade_action",
            default="WAIT",
        ),
        default="WAIT",
    )

    decision_trade_allowed = _normalize_bool(
        _get_value(
            decision,
            "trade_allowed",
            "can_trade",
            "allowed",
            default=False,
        ),
        default=False,
    )

    decision_confidence = _normalize_confidence(
        _get_value(
            decision,
            "confidence",
            "decision_confidence",
            default=0.0,
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

    minimum_confidence = _get_minimum_confidence()

    decision_direction = _get_decision_direction(
        decision_action
    )

    ai_direction = _get_ai_direction(
        ai_action
    )

    block_reasons: list[str] = []

    # Preserve any block reasons already produced by the AI brain.
    existing_block_reasons = _get_value(
        ai_result,
        "block_reasons",
        default=[],
    )

    if isinstance(existing_block_reasons, (list, tuple, set)):
        block_reasons.extend(
            str(reason)
            for reason in existing_block_reasons
        )

    elif existing_block_reasons:
        block_reasons.append(
            str(existing_block_reasons)
        )

    # ------------------------------------------------------------------
    # DECISION VALIDATION
    # ------------------------------------------------------------------

    if decision_direction is None:
        block_reasons.append(
            "Decision engine did not request a valid BUY or SELL."
        )

    if not decision_trade_allowed:
        block_reasons.append(
            "Decision engine did not allow trading."
        )

    # ------------------------------------------------------------------
    # AI VALIDATION
    # ------------------------------------------------------------------

    if ai_action == "NO_TRADE":
        block_reasons.append(
            "AI returned NO_TRADE."
        )

    if not ai_can_trade:
        block_reasons.append(
            "AI did not allow trading."
        )

    if ai_direction is None:
        block_reasons.append(
            "AI did not return CONFIRMED_BUY or CONFIRMED_SELL."
        )

    if ai_confidence < minimum_confidence:
        block_reasons.append(
            "AI confidence is too low: "
            f"{ai_confidence:.4f}. "
            f"Required: {minimum_confidence:.4f}."
        )

    # ------------------------------------------------------------------
    # DIRECTION AGREEMENT
    # ------------------------------------------------------------------

    if (
        decision_direction is not None
        and ai_direction is not None
        and decision_direction != ai_direction
    ):
        block_reasons.append(
            "AI direction mismatch. "
            f"Decision requested {decision_direction}, "
            f"but AI confirmed {ai_direction}."
        )

    block_reasons = _deduplicate_reasons(
        block_reasons
    )

    passed = len(block_reasons) == 0

    # Preserve useful metadata produced by the AI brain.
    if isinstance(ai_result, Mapping):
        filtered_ai_result = dict(ai_result)
    else:
        filtered_ai_result = {}

    original_ai_reason = _get_value(
        ai_result,
        "reason",
        default="",
    )

    # ==================================================================
    # BLOCKED RESULT
    # ==================================================================

    if not passed:
        filtered_ai_result.update(
            {
                "action": "NO_TRADE",
                "can_trade": False,
                "confidence": ai_confidence,
                "reason": (
                    "AI confirmation filter blocked the trade. "
                    + " ".join(block_reasons)
                ),
                "original_ai_action": ai_action,
                "original_ai_reason": original_ai_reason,
                "decision_action": decision_action,
                "decision_direction": decision_direction,
                "decision_trade_allowed": (
                    decision_trade_allowed
                ),
                "decision_confidence": decision_confidence,
                "ai_direction": ai_direction,
                "minimum_ai_confidence": (
                    minimum_confidence
                ),
                "confirmation_filter_passed": False,
                "block_reasons": block_reasons,
            }
        )

        quality_result = {
            "passed": False,
            "decision_action": decision_action,
            "decision_direction": decision_direction,
            "decision_trade_allowed": decision_trade_allowed,
            "decision_confidence": decision_confidence,
            "ai_confidence": ai_confidence,
            "minimum_ai_confidence": minimum_confidence,
            "original_ai_action": ai_action,
            "ai_direction": ai_direction,
            "filtered_ai_action": "NO_TRADE",
            "block_reasons": block_reasons,
        }

        return filtered_ai_result, quality_result

    # ==================================================================
    # APPROVED RESULT
    # ==================================================================

    approval_reasons = _get_value(
        ai_result,
        "confirmation_reasons",
        default=[],
    )

    if not isinstance(approval_reasons, list):
        approval_reasons = [str(approval_reasons)]

    approval_reasons = _deduplicate_reasons(
        approval_reasons
        + [
            (
                "AI direction matches the decision "
                f"direction: {decision_direction}."
            ),
            (
                "AI confidence met the required "
                f"minimum of {minimum_confidence:.4f}."
            ),
            "Decision engine and AI both allowed trading.",
        ]
    )

    filtered_ai_result.update(
        {
            "action": ai_action,
            "can_trade": True,
            "confidence": ai_confidence,
            "reason": (
                "AI confirmation filter approved the trade. "
                + " ".join(approval_reasons)
            ),
            "original_ai_action": ai_action,
            "original_ai_reason": original_ai_reason,
            "decision_action": decision_action,
            "decision_direction": decision_direction,
            "decision_trade_allowed": decision_trade_allowed,
            "decision_confidence": decision_confidence,
            "ai_direction": ai_direction,
            "minimum_ai_confidence": minimum_confidence,
            "confirmation_filter_passed": True,
            "confirmation_reasons": approval_reasons,
            "block_reasons": [],
        }
    )

    quality_result = {
        "passed": True,
        "decision_action": decision_action,
        "decision_direction": decision_direction,
        "decision_trade_allowed": decision_trade_allowed,
        "decision_confidence": decision_confidence,
        "ai_confidence": ai_confidence,
        "minimum_ai_confidence": minimum_confidence,
        "original_ai_action": ai_action,
        "ai_direction": ai_direction,
        "filtered_ai_action": ai_action,
        "block_reasons": [],
    }

    return filtered_ai_result, quality_result

