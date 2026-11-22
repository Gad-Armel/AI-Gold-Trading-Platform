from __future__ import annotations

from typing import Any

from .features.market_state import build_market_features
from .schema import Snapshot
from .data.snapshot_store import append_snapshot


def build_candidate_profile(*, snapshot: Any, consensus: dict[str, Any] | None = None, horizon_decision: dict[str, Any] | None = None,
                            verified_context: dict[str, Any] | None = None, structure: dict[str, Any] | None = None,
                            micro: dict[str, Any] | None = None, news: dict[str, Any] | None = None, macro: dict[str, Any] | None = None,
                            direction: str | None = None, source_lane: str = "EXPLORATORY") -> dict[str, Any]:
    direction = (direction or (horizon_decision or {}).get("direction") or (consensus or {}).get("direction") or "WAIT").upper()
    features = build_market_features(snapshot=snapshot, candles=getattr(snapshot, "candles", {}), ticks=getattr(snapshot, "ticks", None),
                                     verified_context=verified_context, structure=structure, news=news, macro=macro)
    features.update({
        "direction": direction, "source_lane": source_lane,
        "winner_score": float((horizon_decision or {}).get("evidence", (consensus or {}).get("average_evidence", 0.0)) or 0.0),
        "score_margin": float((consensus or {}).get("score_margin", 0.0) or 0.0),
    })
    return features


def record_candidate(*, snapshot: Any, profile: dict[str, Any], direction: str, source_lane: str = "EXPLORATORY", news_mode: str = "UNKNOWN", macro_mode: str = "UNKNOWN"):
    row = Snapshot.now(symbol=str(getattr(snapshot, "symbol", "XAUUSD")), bid=float(getattr(snapshot, "bid", 0.0)), ask=float(getattr(snapshot, "ask", 0.0)),
                       mid=float(getattr(snapshot, "mid", 0.0)), spread=float(getattr(snapshot, "spread", 0.0)), point=float(getattr(snapshot, "point", 0.01)),
                       session=str(getattr(snapshot, "session", "UNKNOWN")), direction=direction, source_lane=source_lane,
                       feature_payload=profile, data_quality=float(profile.get("verified_data_quality", 0.0)), news_mode=news_mode, macro_mode=macro_mode)
    return append_snapshot(row)
