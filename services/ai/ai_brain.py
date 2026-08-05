
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
    Reads the first available value from either:
    - a dictionary;
    - a dataclass;
    - a regular object.
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


def _to_bool(
    value: Any,
    default: bool = False,
) -> bool:
    """
    Safely converts common values to Boolean.
    """

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
            "enabled",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "blocked",
            "rejected",
            "disabled",
        }:
            return False

    if value is None:
        return default

    return bool(value)


def _to_confidence(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Normalizes confidence into the 0.0–1.0 range.

    Supports values such as:
    - 0.75
    - 75
    - "75"
    """

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default

    if confidence > 1.0:
        confidence = confidence / 100.0

    return max(
        0.0,
        min(1.0, confidence),
    )


def _normalize_text(
    value: Any,
    default: str = "",
) -> str:
    """
    Converts a value to normalized uppercase text.
    """

    if value is None:
        return default

    normalized = str(value).strip().upper()

    return normalized or default


def _setting_enabled(
    name: str,
    default: bool,
) -> bool:
    """
    Reads a Boolean configuration setting safely.
    """

    return _to_bool(
        getattr(
            settings,
            name,
            default,
        ),
        default=default,
    )


def _get_minimum_ai_confidence() -> float:
    """
    Returns the configured minimum AI confidence.
    """

    return _to_confidence(
        getattr(
            settings,
            "MIN_AI_CONFIDENCE",
            0.60,
        ),
        default=0.60,
    )


def _deduplicate_reasons(
    reasons: list[Any],
) -> list[str]:
    """
    Removes blank and duplicate reason messages.
    """

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
# DECISION EXTRACTION
# ======================================================================

def _get_nested_decision(
    signal_package: Any,
) -> Any:
    """
    Supports older signal packages that contained a nested
    decision object.
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
    Extracts decision information from the current flattened
    SignalPackageState format.

    Current flattened fields:
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
        "trade_allowed": _to_bool(
            trade_allowed,
            default=False,
        ),
        "confidence": _to_confidence(
            confidence,
            default=0.0,
        ),
    }


# ======================================================================
# MARKET CONTEXT EXTRACTION
# ======================================================================

def _extract_market_context(
    signal_package: Any,
) -> dict[str, Any]:
    """
    Extracts all technical and safety fields required by
    the AI confirmation layer.
    """

    return {
        "price_valid": _to_bool(
            _get_value(
                signal_package,
                "price_valid",
                default=False,
            ),
            default=False,
        ),
        "candles_loaded": _to_bool(
            _get_value(
                signal_package,
                "candles_loaded",
                default=False,
            ),
            default=False,
        ),
        "spread_safe": _to_bool(
            _get_value(
                signal_package,
                "spread_safe",
                default=False,
            ),
            default=False,
        ),
        "session_active": _to_bool(
            _get_value(
                signal_package,
                "session_active",
                default=False,
            ),
            default=False,
        ),
        "trend": _normalize_text(
            _get_value(
                signal_package,
                "overall_trend",
                "trend",
                default="UNKNOWN",
            ),
            default="UNKNOWN",
        ),
        "trend_confidence": _to_confidence(
            _get_value(
                signal_package,
                "trend_confidence",
                default=0.0,
            )
        ),
        "trend_confirmed": _get_value(
            signal_package,
            "trend_confirmed",
            default=None,
        ),
        "structure_bias": _normalize_text(
            _get_value(
                signal_package,
                "structure_bias",
                "structure",
                default="UNKNOWN",
            ),
            default="UNKNOWN",
        ),
        "structure_confidence": _to_confidence(
            _get_value(
                signal_package,
                "structure_confidence",
                default=0.0,
            )
        ),
        "structure_confirmed": _get_value(
            signal_package,
            "structure_confirmed",
            default=None,
        ),
        "volatility": _normalize_text(
            _get_value(
                signal_package,
                "overall_volatility",
                "volatility",
                default="UNKNOWN",
            ),
            default="UNKNOWN",
        ),
        "trade_risk_level": _normalize_text(
            _get_value(
                signal_package,
                "trade_risk_level",
                "volatility_risk",
                default="UNKNOWN",
            ),
            default="UNKNOWN",
        ),
    }


# ======================================================================
# DIRECTION DETECTION
# ======================================================================

def _detect_requested_direction(
    decision_action: str,
) -> str | None:
    """
    Converts supported decision actions into BUY or SELL.
    """

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

    if decision_action in buy_actions:
        return "BUY"

    if decision_action in sell_actions:
        return "SELL"

    return None


# ======================================================================
# TREND VALIDATION
# ======================================================================

def _trend_supports_direction(
    trend: str,
    direction: str,
) -> bool:
    """
    Checks whether the detected trend supports BUY or SELL.

    This includes the detector labels currently used by the project,
    including WEAK_BULLISH and WEAK_BEARISH.
    """

    bullish_values = {
        "BULLISH",
        "WEAK_BULLISH",
        "STRONG_BULLISH",
        "UP",
        "UPTREND",
        "BUY",
        "LONG",
    }

    bearish_values = {
        "BEARISH",
        "WEAK_BEARISH",
        "STRONG_BEARISH",
        "DOWN",
        "DOWNTREND",
        "SELL",
        "SHORT",
    }

    if direction == "BUY":
        return trend in bullish_values

    if direction == "SELL":
        return trend in bearish_values

    return False


def _trend_is_neutral_or_unknown(
    trend: str,
) -> bool:
    return trend in {
        "",
        "UNKNOWN",
        "UNKNOWN_TREND",
        "UNAVAILABLE",
        "NONE",
        "NEUTRAL",
        "NEUTRAL_TREND",
        "SIDEWAYS",
        "RANGING",
        "MIXED",
    }


def _trend_contradicts_direction(
    trend: str,
    direction: str,
) -> bool:
    """
    Neutral or unknown trends do not count as direct contradictions.

    A recognized opposite trend does count as a contradiction.
    """

    if _trend_is_neutral_or_unknown(trend):
        return False

    return not _trend_supports_direction(
        trend,
        direction,
    )


# ======================================================================
# STRUCTURE VALIDATION
# ======================================================================

def _structure_supports_direction(
    structure_bias: str,
    direction: str,
) -> bool:
    """
    Checks whether market structure supports BUY or SELL.

    This includes the detector labels currently used by the project:
    - BULLISH_STRUCTURE
    - WEAK_BULLISH_STRUCTURE
    - BEARISH_STRUCTURE
    - WEAK_BEARISH_STRUCTURE
    """

    bullish_values = {
        "BULLISH",
        "WEAK_BULLISH",
        "BULLISH_STRUCTURE",
        "WEAK_BULLISH_STRUCTURE",
        "BUY_STRUCTURE",
        "BUY",
        "UP",
        "LONG",
    }

    bearish_values = {
        "BEARISH",
        "WEAK_BEARISH",
        "BEARISH_STRUCTURE",
        "WEAK_BEARISH_STRUCTURE",
        "SELL_STRUCTURE",
        "SELL",
        "DOWN",
        "SHORT",
    }

    if direction == "BUY":
        return structure_bias in bullish_values

    if direction == "SELL":
        return structure_bias in bearish_values

    return False


def _structure_is_neutral(
    structure_bias: str,
) -> bool:
    return structure_bias in {
        "NEUTRAL",
        "NEUTRAL_STRUCTURE",
        "SIDEWAYS",
        "SIDEWAYS_STRUCTURE",
        "RANGING",
        "MIXED",
    }


def _structure_is_unknown(
    structure_bias: str,
) -> bool:
    return structure_bias in {
        "",
        "UNKNOWN",
        "UNKNOWN_STRUCTURE",
        "UNAVAILABLE",
        "NONE",
    }


def _structure_contradicts_direction(
    structure_bias: str,
    direction: str,
) -> bool:
    """
    Neutral or unknown structures do not count as direct contradictions.

    A recognized opposite structure does count as a contradiction.
    """

    if (
        _structure_is_neutral(structure_bias)
        or _structure_is_unknown(structure_bias)
    ):
        return False

    return not _structure_supports_direction(
        structure_bias,
        direction,
    )


# ======================================================================
# AI RESULT BUILDERS
# ======================================================================

def _no_trade_result(
    confidence: float,
    reason: str,
    block_reasons: list[str],
    decision_action: str,
) -> dict[str, Any]:
    cleaned_reasons = _deduplicate_reasons(
        block_reasons
    )

    return {
        "action": "NO_TRADE",
        "can_trade": False,
        "confidence": _to_confidence(
            confidence
        ),
        "reason": reason,
        "block_reasons": cleaned_reasons,
        "confirmation_reasons": [],
        "decision_action_received": decision_action,
        "ai_rule_based": True,
    }


def _confirmed_result(
    direction: str,
    confidence: float,
    reasons: list[str],
    decision_action: str,
) -> dict[str, Any]:
    normalized_direction = direction.upper()

    cleaned_reasons = _deduplicate_reasons(
        reasons
    )

    return {
        "action": f"CONFIRMED_{normalized_direction}",
        "can_trade": True,
        "confidence": _to_confidence(
            confidence
        ),
        "reason": " ".join(cleaned_reasons),
        "confirmation_reasons": cleaned_reasons,
        "block_reasons": [],
        "decision_action_received": decision_action,
        "ai_rule_based": True,
    }


# ======================================================================
# RULE-BASED AI BRAIN
# ======================================================================

def run_ai_brain(
    signal_package: Any,
) -> dict[str, Any]:
    """
    Runs the safe rule-based AI confirmation layer.

    Possible outputs:
    - CONFIRMED_BUY
    - CONFIRMED_SELL
    - NO_TRADE

    This layer independently checks:
    - decision direction;
    - decision trade permission;
    - decision confidence;
    - market-price validity;
    - candle availability;
    - spread safety;
    - trading-session status;
    - trend contradiction;
    - structure contradiction;
    - neutral structure configuration;
    - explicit trend/structure confirmation failures;
    - extreme or unknown volatility;
    - dangerous volatility risk levels.

    This function never places a trade.
    """

    decision = _extract_decision_data(
        signal_package
    )

    context = _extract_market_context(
        signal_package
    )

    decision_action = decision["action"]
    decision_trade_allowed = decision[
        "trade_allowed"
    ]
    decision_confidence = decision[
        "confidence"
    ]

    minimum_ai_confidence = (
        _get_minimum_ai_confidence()
    )

    requested_direction = (
        _detect_requested_direction(
            decision_action
        )
    )

    block_reasons: list[str] = []

    # ==================================================================
    # DECISION VALIDATION
    # ==================================================================

    if requested_direction is None:
        block_reasons.append(
            "Decision did not request a valid BUY or SELL analysis."
        )

    if not decision_trade_allowed:
        block_reasons.append(
            "Decision engine did not allow trading."
        )

    if decision_confidence < minimum_ai_confidence:
        block_reasons.append(
            "Decision confidence "
            f"{decision_confidence:.2f} is below the required "
            f"{minimum_ai_confidence:.2f}."
        )

    # ==================================================================
    # MARKET DATA SAFETY
    # ==================================================================

    if not context["price_valid"]:
        block_reasons.append(
            "Market price is invalid."
        )

    if not context["candles_loaded"]:
        block_reasons.append(
            "Required candle data is unavailable."
        )

    if not context["spread_safe"]:
        block_reasons.append(
            "Current spread is unsafe."
        )

    if not context["session_active"]:
        block_reasons.append(
            "Trading session is inactive."
        )

    # ==================================================================
    # EXPLICIT CONFIRMATION FLAGS
    # ==================================================================

    trend_confirmed = context[
        "trend_confirmed"
    ]

    if (
        trend_confirmed is not None
        and not _to_bool(
            trend_confirmed,
            default=False,
        )
    ):
        block_reasons.append(
            "Trend confirmation explicitly failed."
        )

    structure_confirmed = context[
        "structure_confirmed"
    ]

    if (
        structure_confirmed is not None
        and not _to_bool(
            structure_confirmed,
            default=False,
        )
    ):
        block_reasons.append(
            "Structure confirmation explicitly failed."
        )

    # ==================================================================
    # DIRECTIONAL CONTRADICTION CHECKS
    # ==================================================================

    if requested_direction is not None:
        if _trend_contradicts_direction(
            context["trend"],
            requested_direction,
        ):
            block_reasons.append(
                f"Trend {context['trend']} contradicts "
                f"{requested_direction}."
            )

        if _structure_contradicts_direction(
            context["structure_bias"],
            requested_direction,
        ):
            block_reasons.append(
                "Market structure "
                f"{context['structure_bias']} contradicts "
                f"{requested_direction}."
            )

    # ==================================================================
    # NEUTRAL OR UNKNOWN STRUCTURE
    # ==================================================================

    if (
        _structure_is_neutral(
            context["structure_bias"]
        )
        and _setting_enabled(
            "BLOCK_NEUTRAL_STRUCTURE_TRADES",
            True,
        )
    ):
        block_reasons.append(
            "Market structure is neutral and neutral "
            "structure trades are blocked."
        )

    if _structure_is_unknown(
        context["structure_bias"]
    ):
        block_reasons.append(
            "Market structure is unknown."
        )

    # ==================================================================
    # VOLATILITY AND RISK CHECKS
    # ==================================================================

    unknown_volatility_values = {
        "",
        "UNKNOWN",
        "UNKNOWN_VOLATILITY",
        "UNAVAILABLE",
        "NONE",
    }

    extreme_volatility_values = {
        "EXTREME",
        "EXTREME_VOLATILITY",
        "DANGEROUS",
        "CRITICAL",
    }

    high_volatility_values = {
        "HIGH",
        "HIGH_VOLATILITY",
    }

    extreme_risk_values = {
        "EXTREME",
        "EXTREME_RISK",
        "CRITICAL",
        "DANGEROUS",
        "DO_NOT_TRADE",
    }

    if (
        context["volatility"]
        in unknown_volatility_values
        and _setting_enabled(
            "BLOCK_UNKNOWN_VOLATILITY_TRADES",
            True,
        )
    ):
        block_reasons.append(
            "Volatility state is unknown."
        )

    if (
        context["volatility"]
        in extreme_volatility_values
        and _setting_enabled(
            "BLOCK_EXTREME_VOLATILITY_TRADES",
            True,
        )
    ):
        block_reasons.append(
            "Volatility is extreme."
        )

    if (
        context["volatility"]
        in high_volatility_values
        and _setting_enabled(
            "BLOCK_HIGH_VOLATILITY_TRADES",
            False,
        )
    ):
        block_reasons.append(
            "High-volatility trades are blocked by configuration."
        )

    if (
        context["trade_risk_level"]
        in extreme_risk_values
    ):
        block_reasons.append(
            "Trade risk level is extreme or unsafe."
        )

    # ==================================================================
    # BLOCKED RESULT
    # ==================================================================

    block_reasons = _deduplicate_reasons(
        block_reasons
    )

    if block_reasons:
        return _no_trade_result(
            confidence=decision_confidence,
            reason=(
                "AI confirmation blocked the trade. "
                + " ".join(block_reasons)
            ),
            block_reasons=block_reasons,
            decision_action=decision_action,
        )

    # ==================================================================
    # CONFIDENCE ADJUSTMENT
    # ==================================================================

    adjusted_confidence = (
        decision_confidence
    )

    confirmation_reasons: list[str] = [
        (
            "Decision engine approved "
            f"{requested_direction}."
        ),
        (
            "Decision confidence met the minimum "
            f"requirement of {minimum_ai_confidence:.2f}."
        ),
        (
            "Market price, candles, spread, and "
            "trading session are valid."
        ),
    ]

    # Trend support bonus.
    if _trend_supports_direction(
        context["trend"],
        requested_direction,
    ):
        adjusted_confidence += 0.02

        confirmation_reasons.append(
            f"Trend {context['trend']} supports "
            f"{requested_direction}."
        )
    else:
        confirmation_reasons.append(
            "Trend is neutral and does not contradict "
            f"{requested_direction}."
        )

    # Structure support bonus.
    if _structure_supports_direction(
        context["structure_bias"],
        requested_direction,
    ):
        adjusted_confidence += 0.02

        confirmation_reasons.append(
            "Market structure "
            f"{context['structure_bias']} supports "
            f"{requested_direction}."
        )
    else:
        confirmation_reasons.append(
            "Market structure does not contradict "
            f"{requested_direction}."
        )

    confirmation_reasons.append(
        "Volatility and trade-risk checks passed."
    )

    adjusted_confidence = _to_confidence(
        adjusted_confidence
    )

    return _confirmed_result(
        direction=requested_direction,
        confidence=adjusted_confidence,
        reasons=confirmation_reasons,
        decision_action=decision_action,
    )

