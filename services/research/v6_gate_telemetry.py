from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import scalping_settings

_LOCK = threading.Lock()
_LAST_RECORDED_EPOCH = 0.0


def record_v6_gate_telemetry(
    snapshot: Any,
    lane_gates: dict[str, dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Persist sampled gate diagnostics without generating broker activity."""
    global _LAST_RECORDED_EPOCH
    now = time.time()
    interval = float(scalping_settings.SCALPING_V6_GATE_TELEMETRY_INTERVAL_SECONDS)
    with _LOCK:
        if not force and now - _LAST_RECORDED_EPOCH < interval:
            return {"recorded": False, "reason": "throttled"}
        _LAST_RECORDED_EPOCH = now
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "symbol": getattr(snapshot, "symbol", "XAUUSD"),
        "bid": float(getattr(snapshot, "bid", 0.0) or 0.0),
        "ask": float(getattr(snapshot, "ask", 0.0) or 0.0),
        "spread": float(getattr(snapshot, "spread", 0.0) or 0.0),
        "quote_age_seconds": float(getattr(snapshot, "quote_age_seconds", 0.0) or 0.0),
        "tick_time_msc": int(getattr(snapshot, "tick_time_msc", 0) or 0),
        "lanes": {
            name: {
                "allowed": bool(gate.get("allowed", False)),
                "direction": gate.get("direction"),
                "failed_checks": list(gate.get("failed_checks", [])),
                "winner_score": gate.get("winner_score"),
                "score_margin": gate.get("score_margin"),
                "spread_atr": gate.get("spread_atr"),
                "vwap_distance_atr": gate.get("vwap_distance_atr"),
                "relative_volume": gate.get("relative_volume"),
                "micro_direction": gate.get("micro_direction"),
                "micro_confidence": gate.get("micro_confidence"),
                "directional_micro_windows": gate.get("directional_micro_windows"),
                "micro_data_quality": gate.get("micro_data_quality"),
                "micro_quote_flow_imbalance": gate.get("micro_quote_flow_imbalance"),
                "micro_spread_expansion_atr": gate.get("micro_spread_expansion_atr"),
                "micro_regime": gate.get("micro_regime"),
                "context_regime_mode": gate.get("context_regime_mode"),
                "context_regime_direction": gate.get("context_regime_direction"),
                "fast_horizons_aligned": gate.get("fast_horizons_aligned"),
                "max_hold_seconds": gate.get("max_hold_seconds"),
                "persistence_cycles": gate.get("persistence_cycles"),
                "persistence_seconds": gate.get("persistence_seconds"),
                "structure_direction": gate.get("structure_direction"),
                "structure_votes": gate.get("structure_votes"),
                "structure_location_safe": gate.get("structure_location_safe"),
            }
            for name, gate in lane_gates.items()
        },
    }
    path = Path(scalping_settings.SCALPING_V6_GATE_TELEMETRY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, default=str) + "\n"
    for attempt in range(8):
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return {"recorded": True, "path": str(path)}
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    return {"recorded": False, "reason": "temporarily_unavailable", "path": str(path)}
