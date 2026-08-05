from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SessionState:
    active_sessions: list[str]
    primary_session: str
    is_asian: bool
    is_london: bool
    is_new_york: bool
    utc_time: datetime


@dataclass
class MarketState:
    symbol: str
    price: Any = None
    candles: dict[str, Any] = field(default_factory=dict)
    last_update: datetime | None = None
    session: SessionState | None = None


@dataclass
class MarketSnapshot:
    symbol: str
    price: Any
    candles: dict[str, Any]
    last_update: datetime
    session: SessionState

@dataclass
class MarketConditionState:
    price_valid: bool
    candles_loaded: bool
    spread_safe: bool
    session_active: bool
    trade_allowed: bool
    reasons: list[str]

@dataclass
class TradeDecisionState:
    action: str
    trade_allowed: bool
    confidence: float
    reasons: list[str]

@dataclass
class TrendState:
    overall_trend: str
    timeframe_trends: dict[str, str]
    trend_scores: dict[str, int]
    confidence: float
    reasons: list[str]

@dataclass
class VolatilityState:
    overall_volatility: str
    atr_values: dict[str, float]
    atr_percent_values: dict[str, float]
    confidence: float
    trade_risk_level: str
    reasons: list[str]

@dataclass
class StructureState:
    structure_bias: str
    nearest_support: float | None
    nearest_resistance: float | None
    distance_to_support: float | None
    distance_to_resistance: float | None
    timeframe_structure: dict[str, str]
    key_levels: dict[str, dict[str, float]]
    confidence: float
    reasons: list[str]

@dataclass
class SignalPackageState:
    symbol: str
    timestamp: datetime
    price: Any
    primary_session: str
    active_sessions: list[str]

    price_valid: bool
    candles_loaded: bool
    spread_safe: bool
    session_active: bool

    overall_trend: str
    trend_confidence: float
    timeframe_trends: dict[str, str]

    overall_volatility: str
    volatility_confidence: float
    trade_risk_level: str

    structure_bias: str
    structure_confidence: float
    nearest_support: float | None
    nearest_resistance: float | None
    distance_to_support: float | None
    distance_to_resistance: float | None

    decision_action: str
    decision_trade_allowed: bool
    decision_confidence: float

    reasons: dict[str, list[str]]

@dataclass
class AIBrainState:
    ai_action: str
    bias: str
    can_trade: bool
    confidence: float
    source_decision: str
    explanation: str
    warnings: list[str]

@dataclass
class ExecutionGateState:
    allowed_to_execute: bool
    requested_action: str
    order_type: str
    lot_size: float
    confidence: float
    live_trading_enabled: bool
    open_positions_count: int
    reasons: list[str]
    warnings: list[str]

@dataclass
class TradeExecutionResultState:
    executed: bool
    order_type: str
    symbol: str
    lot_size: float
    message: str
    raw_result: Any
    reasons: list[str]

@dataclass
class ProfitManagerState:
    checked_positions: int
    target_profit_usd: float
    closed_positions: int
    blocked_closures: int
    total_profit_usd: float
    messages: list[str]

@dataclass
class BotCycleState:
    success: bool
    snapshot: MarketSnapshot | None = None
    conditions: MarketConditionState | None = None
    trend: TrendState | None = None
    volatility: VolatilityState | None = None
    structure: StructureState | None = None
    decision: TradeDecisionState | None = None
    signal_package: SignalPackageState | None = None
    formatted_signal: str | None = None
    ai_result: AIBrainState | None = None
    execution_gate: ExecutionGateState | None = None
    trade_execution: TradeExecutionResultState | None = None
    profit_manager: ProfitManagerState | None = None
    error_message: str | None = None