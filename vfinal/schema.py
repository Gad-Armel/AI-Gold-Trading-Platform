from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "vfinal-1.0"


@dataclass
class Snapshot:
    timestamp: str
    symbol: str
    bid: float
    ask: float
    mid: float
    spread: float
    point: float
    session: str
    direction: str
    source_lane: str
    feature_payload: dict[str, Any]
    data_quality: float = 1.0
    news_mode: str = "UNKNOWN"
    macro_mode: str = "UNKNOWN"
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def now(cls, **kwargs: Any) -> "Snapshot":
        kwargs.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Label:
    snapshot_timestamp: str
    symbol: str
    direction: str
    horizon: str
    horizon_seconds: int
    entry_price: float
    target_price: float
    stop_price: float
    target_hit: bool
    stop_hit: bool
    time_expired: bool
    outcome: int
    barrier_outcome: int
    horizon_pnl: float
    pnl_if_exit: float
    mfe: float
    mae: float
    holding_seconds: float
    estimated_cost: float
    label_quality: str = "VALID"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
