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
    default: str = "UNKNOWN",
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
            "confirmed",
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
    Converts confidence to the 0.0–1.0 range.

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
        confidence /= 100.0

    return max(
        0.0,
        min(1.0, confidence),
    )


def _get_float_setting(
    name: str,
    default: float,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    try:
        value = float(
            getattr(
                settings,
                name,
                default,
            )
        )
    except (TypeError, ValueError):
        value = default

    value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


def _deduplicate_reasons(
    reasons: list[Any],
) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for reason in reasons:
        text = str(reason).strip()

        if not text or text in seen:
            continue

        cleaned.append(text)
        seen.add(text)

    return cleaned


# ======================================================================
# CONFIGURATION
# ======================================================================

def _minimum_trade_score() -> float:
    return _get_float_setting(
        "MIN_TRADE_SCORE",
        70.0,
        minimum=0.0,
        maximum=100.0,
    )


def _minimum_trend_confidence() -> float:
    return _get_float_setting(
        "MIN_TREND_CONFIDENCE",
        0.60,
        minimum=0.0,
        maximum=1.0,
    )


def _minimum_structure_confidence() -> float:
    return _get_float_setting(
        "MIN_STRUCTURE_CONFIDENCE",
        0.50,
        minimum=0.0,
        maximum=1.0,
    )


def _minimum_high_volatility_trend_confidence() -> float:
    configured_value = _get_float_setting(
        "MIN_HIGH_VOLATILITY_TREND_CONFIDENCE",
        0.70,
        minimum=0.0,
        maximum=1.0,
    )

    return max(
        configured_value,
        _minimum_trend_confidence(),
    )


# ======================================================================
# DIRECTION HELPERS
# ======================================================================

def _decision_direction(
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


def _trend_direction(
    trend_value: str,
) -> str | None:
    bullish_values = {
        "BULLISH",
        "WEAK_BULLISH",
        "STRONG_BULLISH",
        "UP",
        "UPTREND",
        "BUY",
    }

    bearish_values = {
        "BEARISH",
        "WEAK_BEARISH",
        "STRONG_BEARISH",
        "DOWN",
        "DOWNTREND",
        "SELL",
    }

    if trend_value in bullish_values:
        return "BUY"

    if trend_value in bearish_values:
        return "SELL"

    return None


def _structure_direction(
    structure_value: str,
) -> str | None:
    bullish_values = {
        "BULLISH",
        "WEAK_BULLISH",
        "BULLISH_STRUCTURE",
        "WEAK_BULLISH_STRUCTURE",
        "BUY_STRUCTURE",
        "BUY",
        "LONG",
    }

    bearish_values = {
        "BEARISH",
        "WEAK_BEARISH",
        "BEARISH_STRUCTURE",
        "WEAK_BEARISH_STRUCTURE",
        "SELL_STRUCTURE",
        "SELL",
        "SHORT",
    }

    if structure_value in bullish_values:
        return "BUY"

    if structure_value in bearish_values:
        return "SELL"

    return None


def _is_neutral_structure(
    structure_value: str,
) -> bool:
    return structure_value in {
        "NEUTRAL",
        "NEUTRAL_STRUCTURE",
        "SIDEWAYS",
        "SIDEWAYS_STRUCTURE",
        "RANGING",
        "MIXED",
    }


def _is_unknown_structure(
    structure_value: str,
) -> bool:
    return structure_value in {
        "",
        "UNKNOWN",
        "UNKNOWN_STRUCTURE",
        "UNAVAILABLE",
        "NONE",
    }


# ======================================================================
# QUALITY CLASSIFICATION
# ======================================================================

def _classify_quality(
    score: float,
    passed: bool,
) -> str:
    if not passed:
        if score >= 70:
            return "BLOCKED"

        if score >= 50:
            return "WEAK"

        return "BAD"

    if score >= 90:
        return "STRONG"

    if score >= 75:
        return "ACCEPTABLE"

    return "MINIMUM"


# ======================================================================
# TRADE SCORE CALCULATOR
# ======================================================================

def calculate_trade_score(
    conditions: Any,
    trend: Any,
    volatility: Any,
    structure: Any,
    decision: Any,
) -> dict[str, Any]:
    """
    Calculates a normalized trade-quality score from 0 to 100.

    Maximum score allocation:

    - Decision permission:       10 points
    - Market conditions:        15 points
    - Spread safety:            10 points
    - Active session:            5 points
    - Trend alignment:          20 points
    - Trend confidence:         15 points
    - Structure alignment:      15 points
    - Structure confidence:      5 points
    - Volatility suitability:    5 points

    Total:                      100 points

    A trade passes only when:
    - its score meets MIN_TRADE_SCORE; and
    - no hard safety blocker is present.
    """

    score = 0.0
    maximum_score = 100.0

    reasons: list[str] = []
    block_reasons: list[str] = []
    component_scores: dict[str, float] = {}

    # ==================================================================
    # EXTRACT DECISION
    # ==================================================================

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

    requested_direction = _decision_direction(
        decision_action
    )

    if decision_action == "WAIT":
        return {
            "score": 0.0,
            "maximum_score": maximum_score,
            "score_percentage": 0.0,
            "quality": "NO_TRADE",
            "passed": False,
            "minimum_trade_score": _minimum_trade_score(),
            "decision_action": decision_action,
            "decision_direction": None,
            "component_scores": {},
            "reasons": [
                "Decision engine returned WAIT."
            ],
            "block_reasons": [
                "No directional trade setup was approved."
            ],
        }

    if requested_direction is None:
        block_reasons.append(
            "Decision action is not a recognized BUY or SELL action: "
            f"{decision_action}."
        )

    if decision_trade_allowed:
        score += 10.0
        component_scores["decision_permission"] = 10.0

        reasons.append(
            "Decision engine allowed trading."
        )
    else:
        component_scores["decision_permission"] = 0.0

        block_reasons.append(
            "Decision engine did not allow trading."
        )

    # ==================================================================
    # MARKET CONDITIONS
    # ==================================================================

    market_trade_allowed = _normalize_bool(
        _get_value(
            conditions,
            "trade_allowed",
            "is_safe",
            default=False,
        ),
        default=False,
    )

    spread_safe = _normalize_bool(
        _get_value(
            conditions,
            "spread_safe",
            default=False,
        ),
        default=False,
    )

    session_active = _normalize_bool(
        _get_value(
            conditions,
            "session_active",
            "active_session",
            default=False,
        ),
        default=False,
    )

    if market_trade_allowed:
        score += 15.0
        component_scores["market_conditions"] = 15.0

        reasons.append(
            "Market conditions allow trading."
        )
    else:
        component_scores["market_conditions"] = 0.0

        block_reasons.append(
            "Market conditions do not allow trading."
        )

    if spread_safe:
        score += 10.0
        component_scores["spread_safety"] = 10.0

        reasons.append(
            "Spread is within the allowed range."
        )
    else:
        component_scores["spread_safety"] = 0.0

        block_reasons.append(
            "Spread is not safe."
        )

    if session_active:
        score += 5.0
        component_scores["active_session"] = 5.0

        reasons.append(
            "Trading session is active."
        )
    else:
        component_scores["active_session"] = 0.0

        block_reasons.append(
            "No active trading session."
        )

    # ==================================================================
    # TREND
    # ==================================================================

    trend_value = _normalize_text(
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
            default=0.0,
        )
    )

    trend_confirmed_raw = _get_value(
        trend,
        "trend_confirmed",
        default=None,
    )

    detected_trend_direction = _trend_direction(
        trend_value
    )

    if (
        requested_direction is not None
        and detected_trend_direction
        == requested_direction
    ):
        score += 20.0
        component_scores["trend_alignment"] = 20.0

        reasons.append(
            f"Trend supports {requested_direction}."
        )

    else:
        component_scores["trend_alignment"] = 0.0

        if detected_trend_direction is None:
            block_reasons.append(
                f"Trend has no recognized direction: {trend_value}."
            )
        else:
            block_reasons.append(
                "Trend direction contradicts the decision. "
                f"Decision: {requested_direction}. "
                f"Trend: {detected_trend_direction}."
            )

    minimum_trend_confidence = (
        _minimum_trend_confidence()
    )

    if trend_confidence >= minimum_trend_confidence:
        score += 15.0
        component_scores["trend_confidence"] = 15.0

        reasons.append(
            "Trend confidence is acceptable: "
            f"{trend_confidence:.2f}."
        )
    else:
        component_scores["trend_confidence"] = 0.0

        block_reasons.append(
            "Trend confidence is too low. "
            f"Confidence: {trend_confidence:.2f}. "
            f"Required: {minimum_trend_confidence:.2f}."
        )

    if trend_confirmed_raw is not None:
        trend_confirmed = _normalize_bool(
            trend_confirmed_raw,
            default=False,
        )

        if trend_confirmed:
            reasons.append(
                "Trend confirmation passed."
            )
        else:
            block_reasons.append(
                "Trend confirmation explicitly failed."
            )

    # ==================================================================
    # STRUCTURE
    # ==================================================================

    structure_value = _normalize_text(
        _get_value(
            structure,
            "structure_bias",
            "bias",
            default="UNKNOWN",
        )
    )

    structure_confidence = _normalize_confidence(
        _get_value(
            structure,
            "structure_confidence",
            "confidence",
            default=0.0,
        )
    )

    structure_confirmed_raw = _get_value(
        structure,
        "structure_confirmed",
        default=None,
    )

    detected_structure_direction = (
        _structure_direction(
            structure_value
        )
    )

    neutral_structure = _is_neutral_structure(
        structure_value
    )

    unknown_structure = _is_unknown_structure(
        structure_value
    )

    if (
        requested_direction is not None
        and detected_structure_direction
        == requested_direction
    ):
        score += 15.0
        component_scores["structure_alignment"] = 15.0

        reasons.append(
            f"Market structure supports {requested_direction}."
        )

    elif neutral_structure:
        component_scores["structure_alignment"] = 0.0

        if getattr(
            settings,
            "BLOCK_NEUTRAL_STRUCTURE_TRADES",
            True,
        ):
            block_reasons.append(
                "Market structure is neutral and neutral "
                "structure trades are blocked."
            )
        else:
            reasons.append(
                "Market structure is neutral but permitted "
                "by configuration."
            )

    elif unknown_structure:
        component_scores["structure_alignment"] = 0.0

        block_reasons.append(
            "Market structure is unknown."
        )

    else:
        component_scores["structure_alignment"] = 0.0

        block_reasons.append(
            "Market structure contradicts the decision. "
            f"Decision: {requested_direction}. "
            f"Structure: {detected_structure_direction}."
        )

    minimum_structure_confidence = (
        _minimum_structure_confidence()
    )

    if detected_structure_direction is not None:
        if (
            structure_confidence
            >= minimum_structure_confidence
        ):
            score += 5.0
            component_scores[
                "structure_confidence"
            ] = 5.0

            reasons.append(
                "Structure confidence is acceptable: "
                f"{structure_confidence:.2f}."
            )
        else:
            component_scores[
                "structure_confidence"
            ] = 0.0

            block_reasons.append(
                "Structure confidence is too low. "
                f"Confidence: {structure_confidence:.2f}. "
                "Required: "
                f"{minimum_structure_confidence:.2f}."
            )
    else:
        component_scores[
            "structure_confidence"
        ] = 0.0

    if structure_confirmed_raw is not None:
        structure_confirmed = _normalize_bool(
            structure_confirmed_raw,
            default=False,
        )

        if structure_confirmed:
            reasons.append(
                "Structure confirmation passed."
            )
        else:
            block_reasons.append(
                "Structure confirmation explicitly failed."
            )

    # ==================================================================
    # VOLATILITY
    # ==================================================================

    volatility_level = _normalize_text(
        _get_value(
            volatility,
            "overall_volatility",
            "level",
            default="UNKNOWN",
        )
    )

    volatility_risk = _normalize_text(
        _get_value(
            volatility,
            "trade_risk_level",
            "risk_level",
            "risk",
            default="UNKNOWN",
        )
    )

    tradable_volatility = {
        "NORMAL",
        "MEDIUM",
        "MODERATE",
    }

    low_volatility = {
        "LOW",
        "LOW_VOLATILITY",
    }

    high_volatility = {
        "HIGH",
        "HIGH_VOLATILITY",
    }

    extreme_volatility = {
        "EXTREME",
        "EXTREME_VOLATILITY",
        "CRITICAL",
        "DANGEROUS",
    }

    unknown_volatility = {
        "",
        "UNKNOWN",
        "UNAVAILABLE",
        "NONE",
    }

    unsafe_risk_levels = {
        "EXTREME",
        "CRITICAL",
        "DANGEROUS",
        "DO_NOT_TRADE",
    }

    if volatility_risk in unsafe_risk_levels:
        component_scores["volatility"] = 0.0

        block_reasons.append(
            "Volatility risk level is unsafe: "
            f"{volatility_risk}."
        )

    elif volatility_level in tradable_volatility:
        score += 5.0
        component_scores["volatility"] = 5.0

        reasons.append(
            f"Volatility is tradable: {volatility_level}."
        )

    elif volatility_level in high_volatility:
        if getattr(
            settings,
            "BLOCK_HIGH_VOLATILITY_TRADES",
            False,
        ):
            component_scores["volatility"] = 0.0

            block_reasons.append(
                "High-volatility trades are blocked "
                "by configuration."
            )

        elif (
            trend_confidence
            >= _minimum_high_volatility_trend_confidence()
        ):
            score += 2.5
            component_scores["volatility"] = 2.5

            reasons.append(
                "Volatility is high, but trend confidence "
                "is strong enough for cautious analysis."
            )

        else:
            component_scores["volatility"] = 0.0

            block_reasons.append(
                "Volatility is high and trend confidence "
                "is not strong enough. "
                f"Required trend confidence: "
                f"{_minimum_high_volatility_trend_confidence():.2f}."
            )

    elif volatility_level in low_volatility:
        component_scores["volatility"] = 0.0

        block_reasons.append(
            "Volatility is too low for a reliable trade."
        )

    elif volatility_level in extreme_volatility:
        component_scores["volatility"] = 0.0

        if getattr(
            settings,
            "BLOCK_EXTREME_VOLATILITY_TRADES",
            True,
        ):
            block_reasons.append(
                "Volatility is extreme."
            )
        else:
            reasons.append(
                "Extreme volatility is permitted by configuration, "
                "but no volatility score was awarded."
            )

    elif volatility_level in unknown_volatility:
        component_scores["volatility"] = 0.0

        if getattr(
            settings,
            "BLOCK_UNKNOWN_VOLATILITY_TRADES",
            True,
        ):
            block_reasons.append(
                "Volatility is unknown."
            )
        else:
            reasons.append(
                "Unknown volatility is permitted by configuration, "
                "but no volatility score was awarded."
            )

    else:
        component_scores["volatility"] = 0.0

        block_reasons.append(
            "Volatility level is not recognized: "
            f"{volatility_level}."
        )

    # ==================================================================
    # FINAL RESULT
    # ==================================================================

    score = round(
        max(
            0.0,
            min(maximum_score, score),
        ),
        2,
    )

    minimum_score = _minimum_trade_score()

    if score < minimum_score:
        block_reasons.append(
            "Trade score is below the configured minimum. "
            f"Score: {score:.2f}. "
            f"Required: {minimum_score:.2f}."
        )

    reasons = _deduplicate_reasons(
        reasons
    )

    block_reasons = _deduplicate_reasons(
        block_reasons
    )

    passed = (
        score >= minimum_score
        and len(block_reasons) == 0
    )

    quality = _classify_quality(
        score,
        passed,
    )

    return {
        "score": score,
        "maximum_score": maximum_score,
        "score_percentage": score,
        "quality": quality,
        "passed": passed,
        "minimum_trade_score": minimum_score,
        "decision_action": decision_action,
        "decision_direction": requested_direction,
        "decision_trade_allowed": decision_trade_allowed,
        "trend": trend_value,
        "trend_direction": detected_trend_direction,
        "trend_confidence": trend_confidence,
        "structure": structure_value,
        "structure_direction": detected_structure_direction,
        "structure_confidence": structure_confidence,
        "volatility": volatility_level,
        "volatility_risk": volatility_risk,
        "component_scores": component_scores,
        "reasons": reasons,
        "block_reasons": block_reasons,
    }