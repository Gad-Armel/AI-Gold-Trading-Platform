
from collections.abc import Mapping
from typing import Any

from config import settings

from models.market_state import (
    MarketSnapshot,
    MarketConditionState,
    TrendState,
    VolatilityState,
    StructureState,
    TradeDecisionState,
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
    default: str = "UNKNOWN",
) -> str:
    if value is None:
        return default

    normalized = str(value).strip().upper()

    return normalized or default


def _normalize_confidence(
    value: Any,
) -> float:
    """
    Converts confidence to a safe 0.0–1.0 value.

    Supports values such as:
    - 0.72
    - 72
    - "72"
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


def _safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_float_setting(
    name: str,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = _safe_float(
        getattr(settings, name, default),
        default,
    )

    if value is None:
        value = default

    if minimum is not None:
        value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


# ======================================================================
# DECISION RESULT BUILDERS
# ======================================================================

def _wait_decision(
    reasons: list[str],
    confidence: float = 0.0,
) -> TradeDecisionState:
    """
    Builds a safe WAIT decision.
    """

    return TradeDecisionState(
        action="WAIT",
        trade_allowed=False,
        confidence=_normalize_confidence(confidence),
        reasons=reasons,
    )


def _approved_decision(
    direction: str,
    reasons: list[str],
    confidence: float,
) -> TradeDecisionState:
    """
    Builds an approved BUY-side or SELL-side analysis decision.
    """

    normalized_direction = direction.upper()

    return TradeDecisionState(
        action=f"READY_FOR_{normalized_direction}_ANALYSIS",
        trade_allowed=True,
        confidence=_normalize_confidence(confidence),
        reasons=reasons,
    )


# ======================================================================
# CONFIGURATION
# ======================================================================

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
    """
    High volatility requires stronger trend confirmation.

    The value is never allowed to be lower than the normal configured
    trend-confidence requirement.
    """

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


def _minimum_distance_from_key_level() -> float:
    return _get_float_setting(
        "MIN_DISTANCE_FROM_KEY_LEVEL",
        1.00,
        minimum=0.0,
    )


# ======================================================================
# STATE EXTRACTION
# ======================================================================

def _get_condition_reasons(
    conditions: Any,
) -> list[str]:
    reasons = _get_value(
        conditions,
        "reasons",
        default=[],
    )

    if isinstance(reasons, list):
        return [str(reason) for reason in reasons]

    if isinstance(reasons, (tuple, set)):
        return [str(reason) for reason in reasons]

    if reasons:
        return [str(reasons)]

    return []


def _get_timeframe_structure(
    structure: Any,
) -> dict[str, Any]:
    timeframe_structure = _get_value(
        structure,
        "timeframe_structure",
        default={},
    )

    if isinstance(timeframe_structure, Mapping):
        return dict(timeframe_structure)

    return {}


# ======================================================================
# STRUCTURE HELPERS
# ======================================================================

def _has_timeframe_structure(
    structure: Any,
    blocked_structures: set[str],
) -> bool:
    timeframe_structure = _get_timeframe_structure(
        structure
    )

    for structure_value in timeframe_structure.values():
        normalized_value = _normalize_text(
            structure_value
        )

        if normalized_value in blocked_structures:
            return True

    return False


def _is_too_close_to_resistance(
    structure: Any,
) -> bool:
    distance = _safe_float(
        _get_value(
            structure,
            "distance_to_resistance",
            default=None,
        ),
        default=None,
    )

    if distance is None:
        return False

    return (
        0.0
        <= distance
        <= _minimum_distance_from_key_level()
    )


def _is_too_close_to_support(
    structure: Any,
) -> bool:
    distance = _safe_float(
        _get_value(
            structure,
            "distance_to_support",
            default=None,
        ),
        default=None,
    )

    if distance is None:
        return False

    return (
        0.0
        <= distance
        <= _minimum_distance_from_key_level()
    )


def _is_neutral_structure(
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


def _is_unknown_structure(
    structure_bias: str,
) -> bool:
    return structure_bias in {
        "",
        "UNKNOWN",
        "UNKNOWN_STRUCTURE",
        "UNAVAILABLE",
        "NONE",
    }


def _is_bullish_structure(
    structure_bias: str,
) -> bool:
    return structure_bias in {
        "BULLISH",
        "BULLISH_STRUCTURE",
        "WEAK_BULLISH",
        "WEAK_BULLISH_STRUCTURE",
        "BUY",
        "LONG",
    }


def _is_bearish_structure(
    structure_bias: str,
) -> bool:
    return structure_bias in {
        "BEARISH",
        "BEARISH_STRUCTURE",
        "WEAK_BEARISH",
        "WEAK_BEARISH_STRUCTURE",
        "SELL",
        "SHORT",
    }


def _structure_confidence_blocks(
    structure: Any,
    reasons: list[str],
) -> bool:
    """
    Requires adequate confidence when structure has a directional bias.

    Neutral structure is handled separately.
    """

    structure_bias = _normalize_text(
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
            "confidence",
            "structure_confidence",
            default=0.0,
        )
    )

    directional_structure = (
        _is_bullish_structure(structure_bias)
        or _is_bearish_structure(structure_bias)
    )

    if (
        directional_structure
        and structure_confidence
        < _minimum_structure_confidence()
    ):
        reasons.append(
            "Structure confidence is too low: "
            f"{structure_confidence:.2f}. Required: "
            f"{_minimum_structure_confidence():.2f}."
        )
        return True

    return False


def _structure_blocks_buy(
    structure: Any,
    reasons: list[str],
) -> bool:
    """
    Blocks BUY-side analysis when structure is dangerous for buying.
    """

    structure_bias = _normalize_text(
        _get_value(
            structure,
            "structure_bias",
            "bias",
            default="UNKNOWN",
        )
    )

    if _is_unknown_structure(structure_bias):
        reasons.append(
            "Structure is unknown. BUY analysis blocked."
        )
        return True

    if (
        getattr(
            settings,
            "BLOCK_NEUTRAL_STRUCTURE_TRADES",
            True,
        )
        and _is_neutral_structure(structure_bias)
    ):
        reasons.append(
            "Structure is neutral. BUY analysis blocked by configuration."
        )
        return True

    if _is_bearish_structure(structure_bias):
        reasons.append(
            "Structure bias is bearish. BUY analysis blocked."
        )
        return True

    if _structure_confidence_blocks(
        structure,
        reasons,
    ):
        return True

    if _has_timeframe_structure(
        structure,
        {
            "NEAR_RESISTANCE",
            "AT_RESISTANCE",
            "BREAKDOWN_DOWN",
            "BEARISH_BREAKDOWN",
        },
    ):
        reasons.append(
            "Price is near resistance or breaking down. "
            "BUY analysis blocked."
        )
        return True

    if _is_too_close_to_resistance(structure):
        distance = _get_value(
            structure,
            "distance_to_resistance",
            default="N/A",
        )

        reasons.append(
            "Price is too close to resistance. "
            f"Distance: {distance}."
        )
        return True

    return False


def _structure_blocks_sell(
    structure: Any,
    reasons: list[str],
) -> bool:
    """
    Blocks SELL-side analysis when structure is dangerous for selling.
    """

    structure_bias = _normalize_text(
        _get_value(
            structure,
            "structure_bias",
            "bias",
            default="UNKNOWN",
        )
    )

    if _is_unknown_structure(structure_bias):
        reasons.append(
            "Structure is unknown. SELL analysis blocked."
        )
        return True

    if (
        getattr(
            settings,
            "BLOCK_NEUTRAL_STRUCTURE_TRADES",
            True,
        )
        and _is_neutral_structure(structure_bias)
    ):
        reasons.append(
            "Structure is neutral. SELL analysis blocked by configuration."
        )
        return True

    if _is_bullish_structure(structure_bias):
        reasons.append(
            "Structure bias is bullish. SELL analysis blocked."
        )
        return True

    if _structure_confidence_blocks(
        structure,
        reasons,
    ):
        return True

    if _has_timeframe_structure(
        structure,
        {
            "NEAR_SUPPORT",
            "AT_SUPPORT",
            "BREAKOUT_UP",
            "BULLISH_BREAKOUT",
        },
    ):
        reasons.append(
            "Price is near support or breaking upward. "
            "SELL analysis blocked."
        )
        return True

    if _is_too_close_to_support(structure):
        distance = _get_value(
            structure,
            "distance_to_support",
            default="N/A",
        )

        reasons.append(
            "Price is too close to support. "
            f"Distance: {distance}."
        )
        return True

    return False


# ======================================================================
# CONFIDENCE CALCULATION
# ======================================================================

def _combine_confidence(
    trend: Any,
    volatility: Any,
    structure: Any,
) -> float:
    """
    Calculates a conservative combined decision confidence.

    Weights:
    - trend: 55%
    - volatility: 25%
    - structure: 20%

    If structure confidence is unavailable or zero, the remaining
    weights are redistributed between trend and volatility.
    """

    trend_confidence = _normalize_confidence(
        _get_value(
            trend,
            "confidence",
            "trend_confidence",
            default=0.0,
        )
    )

    volatility_confidence = _normalize_confidence(
        _get_value(
            volatility,
            "confidence",
            "volatility_confidence",
            default=0.0,
        )
    )

    structure_confidence = _normalize_confidence(
        _get_value(
            structure,
            "confidence",
            "structure_confidence",
            default=0.0,
        )
    )

    if structure_confidence > 0.0:
        combined = (
            trend_confidence * 0.55
            + volatility_confidence * 0.25
            + structure_confidence * 0.20
        )
    else:
        combined = (
            trend_confidence * 0.70
            + volatility_confidence * 0.30
        )

    # The combined confidence must not become unrealistically higher
    # than the directional trend confidence.
    combined = min(
        combined,
        trend_confidence,
    )

    return round(
        max(0.0, min(1.0, combined)),
        4,
    )


# ======================================================================
# DECISION ENGINE
# ======================================================================

def make_trade_decision(
    snapshot: MarketSnapshot,
    conditions: MarketConditionState,
    trend: TrendState,
    volatility: VolatilityState,
    structure: StructureState,
) -> TradeDecisionState:
    """
    Determines whether the market should proceed to BUY-side,
    SELL-side, or no-trade AI analysis.

    Possible actions:
    - READY_FOR_BUY_ANALYSIS
    - READY_FOR_SELL_ANALYSIS
    - WAIT

    This function never places a trade.
    """

    reasons: list[str] = []

    # ==================================================================
    # REQUIRED DATA CHECKS
    # ==================================================================

    if snapshot is None:
        return _wait_decision(
            ["Market snapshot is missing."]
        )

    if conditions is None:
        return _wait_decision(
            ["Market-condition state is missing."]
        )

    if trend is None:
        return _wait_decision(
            ["Trend data is missing."]
        )

    if volatility is None:
        return _wait_decision(
            ["Volatility data is missing."]
        )

    if structure is None:
        return _wait_decision(
            ["Structure data is missing."]
        )

    snapshot_price = _get_value(
        snapshot,
        "price",
        default=None,
    )

    if snapshot_price is None:
        return _wait_decision(
            ["Snapshot price is missing."]
        )

    session = _get_value(
        snapshot,
        "session",
        default=None,
    )

    if session is None:
        return _wait_decision(
            ["Session data is missing."]
        )

    # ==================================================================
    # MARKET-CONDITION SAFETY
    # ==================================================================

    market_trade_allowed = _normalize_bool(
        _get_value(
            conditions,
            "trade_allowed",
            "is_safe",
            default=False,
        )
    )

    if not market_trade_allowed:
        reasons.append(
            "Market conditions are not safe."
        )
        reasons.extend(
            _get_condition_reasons(conditions)
        )

        return _wait_decision(reasons)

    # ==================================================================
    # EXTRACT NORMALIZED MARKET STATES
    # ==================================================================

    primary_session = _get_value(
        session,
        "primary_session",
        "name",
        "primary",
        default="UNKNOWN",
    )

    trend_direction = _normalize_text(
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
            "confidence",
            "trend_confidence",
            default=0.0,
        )
    )

    volatility_level = _normalize_text(
        _get_value(
            volatility,
            "overall_volatility",
            "level",
            default="UNKNOWN",
        )
    )

    volatility_confidence = _normalize_confidence(
        _get_value(
            volatility,
            "confidence",
            "volatility_confidence",
            default=0.0,
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

    structure_bias = _normalize_text(
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
            "confidence",
            "structure_confidence",
            default=0.0,
        )
    )

    nearest_support = _get_value(
        structure,
        "nearest_support",
        default=None,
    )

    nearest_resistance = _get_value(
        structure,
        "nearest_resistance",
        default=None,
    )

    reasons.extend(
        [
            f"Primary session: {primary_session}.",
            f"Overall trend: {trend_direction}.",
            f"Trend confidence: {trend_confidence:.4f}.",
            f"Overall volatility: {volatility_level}.",
            f"Volatility confidence: {volatility_confidence:.4f}.",
            f"Volatility risk level: {volatility_risk}.",
            f"Structure bias: {structure_bias}.",
            f"Structure confidence: {structure_confidence:.4f}.",
            f"Nearest support: {nearest_support}.",
            f"Nearest resistance: {nearest_resistance}.",
        ]
    )

    # ==================================================================
    # TREND VALIDATION
    # ==================================================================

    minimum_trend_confidence = (
        _minimum_trend_confidence()
    )

    if trend_direction in {
        "",
        "UNKNOWN",
        "NEUTRAL",
        "SIDEWAYS",
        "RANGING",
        "MIXED",
    }:
        reasons.append(
            "Trend has no reliable directional bias."
        )

        return _wait_decision(
            reasons,
            confidence=trend_confidence,
        )

    if trend_confidence < minimum_trend_confidence:
        reasons.append(
            "Trend confidence is too low: "
            f"{trend_confidence:.2f}. Required: "
            f"{minimum_trend_confidence:.2f}."
        )

        return _wait_decision(
            reasons,
            confidence=trend_confidence,
        )

    # ==================================================================
    # VOLATILITY VALIDATION
    # ==================================================================

    unknown_volatility_values = {
        "",
        "UNKNOWN",
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

    low_volatility_values = {
        "LOW",
        "LOW_VOLATILITY",
    }

    if (
        volatility_level in unknown_volatility_values
        and getattr(
            settings,
            "BLOCK_UNKNOWN_VOLATILITY_TRADES",
            True,
        )
    ):
        reasons.append(
            "Volatility is unknown. Analysis blocked."
        )

        return _wait_decision(
            reasons,
            confidence=0.0,
        )

    if (
        volatility_level in extreme_volatility_values
        and getattr(
            settings,
            "BLOCK_EXTREME_VOLATILITY_TRADES",
            True,
        )
    ):
        reasons.append(
            "Volatility is extreme. Market is dangerous."
        )

        return _wait_decision(
            reasons,
            confidence=volatility_confidence,
        )

    if volatility_level in low_volatility_values:
        reasons.append(
            "Volatility is too low. Market movement is weak."
        )

        return _wait_decision(
            reasons,
            confidence=volatility_confidence,
        )

    if volatility_level in high_volatility_values:
        if getattr(
            settings,
            "BLOCK_HIGH_VOLATILITY_TRADES",
            False,
        ):
            reasons.append(
                "High-volatility trades are blocked by configuration."
            )

            return _wait_decision(
                reasons,
                confidence=volatility_confidence,
            )

        required_high_volatility_confidence = (
            _minimum_high_volatility_trend_confidence()
        )

        if (
            trend_confidence
            < required_high_volatility_confidence
        ):
            reasons.append(
                "Volatility is high and trend confidence "
                "is not strong enough. "
                f"Trend confidence: {trend_confidence:.2f}. "
                "Required: "
                f"{required_high_volatility_confidence:.2f}."
            )

            return _wait_decision(
                reasons,
                confidence=trend_confidence,
            )

        reasons.append(
            "Volatility is high, but trend confidence is "
            "strong enough for AI analysis."
        )

    if volatility_risk in {
        "EXTREME",
        "CRITICAL",
        "DANGEROUS",
        "DO_NOT_TRADE",
    }:
        reasons.append(
            f"Volatility risk level is unsafe: {volatility_risk}."
        )

        return _wait_decision(
            reasons,
            confidence=volatility_confidence,
        )

    # ==================================================================
    # FINAL CONFIDENCE
    # ==================================================================

    final_confidence = _combine_confidence(
        trend,
        volatility,
        structure,
    )

    if final_confidence < minimum_trend_confidence:
        reasons.append(
            "Combined decision confidence is too low: "
            f"{final_confidence:.2f}. Required: "
            f"{minimum_trend_confidence:.2f}."
        )

        return _wait_decision(
            reasons,
            confidence=final_confidence,
        )

    # ==================================================================
    # BUY DECISION
    # ==================================================================

    bullish_trends = {
        "BULLISH",
        "WEAK_BULLISH",
        "UP",
        "UPTREND",
        "STRONG_BULLISH",
    }

    if trend_direction in bullish_trends:
        if _structure_blocks_buy(
            structure,
            reasons,
        ):
            return _wait_decision(
                reasons,
                confidence=final_confidence,
            )

        reasons.append(
            "Trend and structure permit BUY-side AI analysis."
        )

        return _approved_decision(
            direction="BUY",
            reasons=reasons,
            confidence=final_confidence,
        )

    # ==================================================================
    # SELL DECISION
    # ==================================================================

    bearish_trends = {
        "BEARISH",
        "WEAK_BEARISH",
        "DOWN",
        "DOWNTREND",
        "STRONG_BEARISH",
    }

    if trend_direction in bearish_trends:
        if _structure_blocks_sell(
            structure,
            reasons,
        ):
            return _wait_decision(
                reasons,
                confidence=final_confidence,
            )

        reasons.append(
            "Trend and structure permit SELL-side AI analysis."
        )

        return _approved_decision(
            direction="SELL",
            reasons=reasons,
            confidence=final_confidence,
        )

    reasons.append(
        "Trend direction was not recognized as BUY or SELL."
    )

    return _wait_decision(
        reasons,
        confidence=final_confidence,
    )

