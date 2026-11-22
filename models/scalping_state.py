from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScalpingSnapshotState:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    spread: float
    mid: float
    session: str
    active_sessions: list[str]
    candles: dict[str, Any] = field(default_factory=dict)
    contract_size: float = 100.0
    point: float = 0.01
    candle_cache_hit: bool = False
    candle_cache_details: dict[str, Any] = field(default_factory=dict)
    system_timestamp: datetime | None = None
    market_clock_source: str = "SYSTEM_UTC"
    market_clock_offset_seconds: float = 0.0
    tick_time_msc: int = 0
    tick_flags: int = 0
    tick_volume: float = 0.0
    tick_volume_real: float = 0.0
    last_price: float = 0.0
    quote_age_seconds: float = 0.0
    intermarket_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScalpSignalState:
    action: str
    direction: str
    allowed: bool
    score: float
    confidence: float
    target_profit_usd: float
    stop_loss_usd: float
    signal_key: str
    pattern: str
    metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)


@dataclass
class ScalpingCycleState:
    success: bool
    symbol: str
    started_at: datetime
    finished_at: datetime
    runtime_ms: float
    snapshot: ScalpingSnapshotState | None = None
    signal: ScalpSignalState | None = None
    news_risk: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    paper: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    timing_ms: dict[str, float] = field(default_factory=dict)
    tick_recorder: dict[str, Any] = field(default_factory=dict)
    microstructure: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, Any] = field(default_factory=dict)
    meta_controller: dict[str, Any] = field(default_factory=dict)
    execution_audit: dict[str, Any] = field(default_factory=dict)
