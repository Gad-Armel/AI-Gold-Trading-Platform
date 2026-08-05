
from collections.abc import Mapping
from typing import Any

from models.market_state import (
    MarketSnapshot,
    MarketConditionState,
    TrendState,
    VolatilityState,
    StructureState,
    TradeDecisionState,
    SignalPackageState,
)


def _get_decision_value(
    decision: TradeDecisionState | Mapping[str, Any] | None,
    field_name: str,
    default: Any = None,
) -> Any:
    """
    Safely retrieves a value from a trade decision.

    The decision engine may return either:
    - a TradeDecisionState object
    - a dictionary-like mapping

    This helper allows the signal package builder to support both formats.
    """

    if decision is None:
        return default

    if isinstance(decision, Mapping):
        return decision.get(field_name, default)

    return getattr(decision, field_name, default)


def build_signal_package(
    snapshot: MarketSnapshot,
    conditions: MarketConditionState,
    trend: TrendState,
    volatility: VolatilityState,
    structure: StructureState,
    decision: TradeDecisionState | Mapping[str, Any],
) -> SignalPackageState:
    """
    Builds one clean signal package for the future AI brain.

    This object is the clean summary of the full market situation.

    The decision argument may be either a TradeDecisionState object
    or a dictionary returned by the decision engine.
    """

    decision_action = str(
        _get_decision_value(
            decision=decision,
            field_name="action",
            default="WAIT",
        )
        or "WAIT"
    ).upper()

    decision_trade_allowed = bool(
        _get_decision_value(
            decision=decision,
            field_name="trade_allowed",
            default=False,
        )
    )

    try:
        decision_confidence = float(
            _get_decision_value(
                decision=decision,
                field_name="confidence",
                default=0.0,
            )
            or 0.0
        )
    except (TypeError, ValueError):
        decision_confidence = 0.0

    decision_reasons = _get_decision_value(
        decision=decision,
        field_name="reasons",
        default=None,
    )

    # Support decision engines that use the singular key "reason".
    if decision_reasons is None:
        decision_reasons = _get_decision_value(
            decision=decision,
            field_name="reason",
            default=[],
        )

    if decision_reasons is None:
        decision_reasons = []

    return SignalPackageState(
        symbol=snapshot.symbol,
        timestamp=snapshot.last_update,
        price=snapshot.price,
        primary_session=snapshot.session.primary_session,
        active_sessions=snapshot.session.active_sessions,

        price_valid=conditions.price_valid,
        candles_loaded=conditions.candles_loaded,
        spread_safe=conditions.spread_safe,
        session_active=conditions.session_active,

        overall_trend=trend.overall_trend,
        trend_confidence=trend.confidence,
        timeframe_trends=trend.timeframe_trends,

        overall_volatility=volatility.overall_volatility,
        volatility_confidence=volatility.confidence,
        trade_risk_level=volatility.trade_risk_level,

        structure_bias=structure.structure_bias,
        structure_confidence=structure.confidence,
        nearest_support=structure.nearest_support,
        nearest_resistance=structure.nearest_resistance,
        distance_to_support=structure.distance_to_support,
        distance_to_resistance=structure.distance_to_resistance,

        decision_action=decision_action,
        decision_trade_allowed=decision_trade_allowed,
        decision_confidence=decision_confidence,

        reasons={
            "conditions": conditions.reasons,
            "trend": trend.reasons,
            "volatility": volatility.reasons,
            "structure": structure.reasons,
            "decision": decision_reasons,
        },
    )

