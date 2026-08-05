
from collections.abc import Mapping
from typing import Any

from config import settings
from models.market_state import TradeDecisionState

from services.decision.trade_score_calculator import (
    calculate_trade_score,
)
from services.risk.bad_market_filter import (
    assess_bad_market_conditions,
)
from services.risk.volatility_risk_filter import (
    assess_volatility_risk,
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
    Reads the first available value from a dictionary or object.
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
    Converts confidence into the 0.0–1.0 range.
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


def _normalize_score(
    value: Any,
) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(
        0.0,
        min(100.0, score),
    )


def _get_minimum_trade_score() -> float:
    try:
        minimum_score = float(
            getattr(
                settings,
                "MIN_TRADE_SCORE",
                70,
            )
        )
    except (TypeError, ValueError):
        minimum_score = 70.0

    return max(
        0.0,
        min(100.0, minimum_score),
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
# SAFE FILTER EXECUTION
# ======================================================================

def _run_trade_score_calculator(
    conditions: Any,
    trend: Any,
    volatility: Any,
    structure: Any,
    decision: Any,
) -> dict[str, Any]:
    """
    Runs the score calculator safely.

    A calculator failure blocks the trade instead of crashing the cycle.
    """

    try:
        result = calculate_trade_score(
            conditions=conditions,
            trend=trend,
            volatility=volatility,
            structure=structure,
            decision=decision,
        )

        if isinstance(result, Mapping):
            return dict(result)

        return {
            "score": 0.0,
            "quality": "BAD",
            "passed": False,
            "reasons": [],
            "block_reasons": [
                "Trade score calculator returned an invalid result."
            ],
        }

    except Exception as error:
        return {
            "score": 0.0,
            "quality": "BAD",
            "passed": False,
            "reasons": [],
            "block_reasons": [
                f"Trade score calculation failed: {error}"
            ],
            "error": str(error),
        }


def _run_market_filter(
    snapshot: Any,
    conditions: Any,
) -> dict[str, Any]:
    try:
        result = assess_bad_market_conditions(
            snapshot,
            conditions,
        )

        if isinstance(result, Mapping):
            return dict(result)

        return {
            "passed": False,
            "block_reasons": [
                "Bad-market filter returned an invalid result."
            ],
        }

    except Exception as error:
        return {
            "passed": False,
            "block_reasons": [
                f"Bad-market filter failed: {error}"
            ],
            "error": str(error),
        }


def _run_volatility_filter(
    volatility: Any,
) -> dict[str, Any]:
    try:
        result = assess_volatility_risk(
            volatility
        )

        if isinstance(result, Mapping):
            return dict(result)

        return {
            "passed": False,
            "block_reasons": [
                "Volatility risk filter returned an invalid result."
            ],
        }

    except Exception as error:
        return {
            "passed": False,
            "block_reasons": [
                f"Volatility risk filter failed: {error}"
            ],
            "error": str(error),
        }


# ======================================================================
# DECISION HELPERS
# ======================================================================

def _get_decision_action(
    decision: Any,
) -> str:
    return _normalize_text(
        _get_value(
            decision,
            "action",
            "decision",
            "trade_action",
            default="WAIT",
        ),
        default="WAIT",
    )


def _get_decision_trade_allowed(
    decision: Any,
) -> bool:
    return _normalize_bool(
        _get_value(
            decision,
            "trade_allowed",
            "can_trade",
            "allowed",
            default=False,
        ),
        default=False,
    )


def _get_decision_confidence(
    decision: Any,
) -> float:
    return _normalize_confidence(
        _get_value(
            decision,
            "confidence",
            "decision_confidence",
            default=0.0,
        )
    )


def _get_decision_reasons(
    decision: Any,
) -> list[str]:
    reasons = _get_value(
        decision,
        "reasons",
        "reason",
        default=[],
    )

    return _to_reason_list(reasons)


def _is_directional_action(
    action: str,
) -> bool:
    return action in {
        "BUY",
        "SELL",
        "READY_FOR_BUY_ANALYSIS",
        "READY_FOR_SELL_ANALYSIS",
        "BUY_READY",
        "SELL_READY",
        "BUY_SIGNAL",
        "SELL_SIGNAL",
    }


def _is_neutral_structure(
    structure: Any,
) -> bool:
    structure_bias = _normalize_text(
        _get_value(
            structure,
            "structure_bias",
            "bias",
            default="UNKNOWN",
        ),
        default="UNKNOWN",
    )

    return structure_bias in {
        "NEUTRAL",
        "NEUTRAL_STRUCTURE",
        "SIDEWAYS",
        "SIDEWAYS_STRUCTURE",
        "RANGING",
        "MIXED",
    }


# ======================================================================
# DECISION RESULT BUILDERS
# ======================================================================

def _force_wait(
    original_decision: Any,
    block_reasons: list[str],
) -> TradeDecisionState:
    """
    Returns a consistent TradeDecisionState instead of a dictionary.
    """

    original_action = _get_decision_action(
        original_decision
    )

    original_confidence = (
        _get_decision_confidence(
            original_decision
        )
    )

    original_reasons = _get_decision_reasons(
        original_decision
    )

    final_reasons = _deduplicate_reasons(
        original_reasons
        + [
            "Decision quality filter blocked the trade.",
            f"Original decision action: {original_action}.",
        ]
        + block_reasons
    )

    return TradeDecisionState(
        action="WAIT",
        trade_allowed=False,
        confidence=original_confidence,
        reasons=final_reasons,
    )


def _approve_decision(
    original_decision: Any,
    approval_reasons: list[str],
) -> TradeDecisionState:
    """
    Preserves the original directional action in a TradeDecisionState.
    """

    action = _get_decision_action(
        original_decision
    )

    confidence = _get_decision_confidence(
        original_decision
    )

    original_reasons = _get_decision_reasons(
        original_decision
    )

    final_reasons = _deduplicate_reasons(
        original_reasons
        + [
            "Decision quality filter approved the trade."
        ]
        + approval_reasons
    )

    return TradeDecisionState(
        action=action,
        trade_allowed=True,
        confidence=confidence,
        reasons=final_reasons,
    )


# ======================================================================
# DECISION QUALITY FILTER
# ======================================================================

def apply_decision_quality_filter(
    conditions: Any,
    trend: Any,
    volatility: Any,
    structure: Any,
    decision: Any,
    snapshot: Any = None,
) -> tuple[TradeDecisionState, dict[str, Any]]:
    """
    Blocks weak or dangerous BUY/SELL decisions before AI confirmation.

    The returned decision is always a TradeDecisionState. This maintains
    compatibility with signal_package_builder.py and prevents dictionary
    versus object interface errors.
    """

    decision_action = _get_decision_action(
        decision
    )

    decision_trade_allowed = (
        _get_decision_trade_allowed(
            decision
        )
    )

    decision_confidence = (
        _get_decision_confidence(
            decision
        )
    )

    # ------------------------------------------------------------------
    # RUN ALL QUALITY CHECKS
    # ------------------------------------------------------------------

    score_result = _run_trade_score_calculator(
        conditions=conditions,
        trend=trend,
        volatility=volatility,
        structure=structure,
        decision=decision,
    )

    market_filter = _run_market_filter(
        snapshot=snapshot,
        conditions=conditions,
    )

    volatility_filter = _run_volatility_filter(
        volatility=volatility,
    )

    score = _normalize_score(
        score_result.get(
            "score",
            0.0,
        )
    )

    quality = str(
        score_result.get(
            "quality",
            "BAD",
        )
        or "BAD"
    ).upper()

    score_passed = _normalize_bool(
        score_result.get(
            "passed",
            True,
        ),
        default=True,
    )

    market_passed = _normalize_bool(
        market_filter.get(
            "passed",
            False,
        ),
        default=False,
    )

    volatility_passed = _normalize_bool(
        volatility_filter.get(
            "passed",
            False,
        ),
        default=False,
    )

    minimum_trade_score = (
        _get_minimum_trade_score()
    )

    # ------------------------------------------------------------------
    # COLLECT ALL REASONS
    # ------------------------------------------------------------------

    quality_reasons = _to_reason_list(
        score_result.get(
            "reasons",
            [],
        )
    )

    block_reasons = _to_reason_list(
        score_result.get(
            "block_reasons",
            [],
        )
    )

    block_reasons.extend(
        _to_reason_list(
            market_filter.get(
                "block_reasons",
                [],
            )
        )
    )

    block_reasons.extend(
        _to_reason_list(
            volatility_filter.get(
                "block_reasons",
                [],
            )
        )
    )

    # ------------------------------------------------------------------
    # ORIGINAL DECISION SAFETY
    # ------------------------------------------------------------------

    if decision_action == "WAIT":
        block_reasons.append(
            "Original decision is WAIT."
        )

    elif not _is_directional_action(
        decision_action
    ):
        block_reasons.append(
            "Original decision action is not recognized as "
            f"a valid BUY or SELL action: {decision_action}."
        )

    if not decision_trade_allowed:
        block_reasons.append(
            "Original decision did not allow trading."
        )

    # ------------------------------------------------------------------
    # FILTER RESULTS
    # ------------------------------------------------------------------

    if not score_passed:
        block_reasons.append(
            "Trade score calculator did not pass the trade."
        )

    if not market_passed:
        block_reasons.append(
            "Bad-market filter did not pass the trade."
        )

    if not volatility_passed:
        block_reasons.append(
            "Volatility risk filter did not pass the trade."
        )

    if (
        getattr(
            settings,
            "BLOCK_NEUTRAL_STRUCTURE_TRADES",
            True,
        )
        and _is_neutral_structure(structure)
    ):
        block_reasons.append(
            "Trade blocked because market structure is neutral."
        )

    if score < minimum_trade_score:
        block_reasons.append(
            "Trade score is below the configured minimum. "
            f"Score: {score:.2f}. "
            f"Required: {minimum_trade_score:.2f}."
        )

    block_reasons = _deduplicate_reasons(
        block_reasons
    )

    passed = len(block_reasons) == 0

    # ------------------------------------------------------------------
    # COMPLETE SCORE RESULT FOR LOGGING
    # ------------------------------------------------------------------

    score_result = dict(score_result)

    score_result.update(
        {
            "score": score,
            "quality": quality,
            "passed": passed,
            "minimum_trade_score": minimum_trade_score,
            "decision_action": decision_action,
            "decision_trade_allowed": (
                decision_trade_allowed
            ),
            "decision_confidence": (
                decision_confidence
            ),
            "market_filter": market_filter,
            "volatility_filter": volatility_filter,
            "market_filter_passed": market_passed,
            "volatility_filter_passed": (
                volatility_passed
            ),
            "quality_reasons": quality_reasons,
            "block_reasons": block_reasons,
        }
    )

    # ------------------------------------------------------------------
    # BLOCKED DECISION
    # ------------------------------------------------------------------

    if not passed:
        filtered_decision = _force_wait(
            original_decision=decision,
            block_reasons=block_reasons,
        )

        return filtered_decision, score_result

    # ------------------------------------------------------------------
    # APPROVED DECISION
    # ------------------------------------------------------------------

    approval_reasons = _deduplicate_reasons(
        quality_reasons
        + [
            (
                "Trade score passed: "
                f"{score:.2f}/{minimum_trade_score:.2f}."
            ),
            "Bad-market filter passed.",
            "Volatility risk filter passed.",
        ]
    )

    filtered_decision = _approve_decision(
        original_decision=decision,
        approval_reasons=approval_reasons,
    )

    return filtered_decision, score_result

