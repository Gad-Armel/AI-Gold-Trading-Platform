from __future__ import annotations

from datetime import datetime, timezone
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.analysis.v6_market_structure import _CACHE, _LAST_RENDER_EPOCH, build_v6_market_structure, maybe_render_v6_market_map
from services.research.v6_candidate_gate import evaluate_v6_candidate_gate


def frame(*, step: float, wave: float, end: float = 4000.0, periods: int = 121) -> pd.DataFrame:
    x = np.arange(periods, dtype=float)
    raw = step * x + wave * np.sin(x / 3.0)
    raw = raw - raw[-1] + end
    opened = np.r_[raw[0] - step, raw[:-1]]
    return pd.DataFrame(
        {
            "time": pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=periods, freq="15min"),
            "open": opened,
            "high": np.maximum(opened, raw) + 0.30,
            "low": np.minimum(opened, raw) - 0.30,
            "close": raw,
            "tick_volume": 100.0,
        }
    )


def snapshot(direction: str) -> ScalpingSnapshotState:
    sign = 1.0 if direction == "BUY" else -1.0
    mid = 4000.0
    frames = {
        "M15": frame(step=0.18 * sign, wave=0.45, end=mid),
        "H1": frame(step=0.50 * sign, wave=1.00, end=mid),
        "H4": frame(step=1.20 * sign, wave=2.00, end=mid),
    }
    return ScalpingSnapshotState(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        bid=mid - 0.12,
        ask=mid + 0.12,
        spread=0.24,
        mid=mid,
        session="London",
        active_sessions=["London"],
        candles=frames,
    )


def signal_for(direction: str, structure: dict) -> ScalpSignalState:
    return ScalpSignalState(
        action=direction,
        direction=direction,
        allowed=True,
        score=55.0,
        confidence=0.8,
        target_profit_usd=0.85,
        stop_loss_usd=1.25,
        signal_key="test",
        pattern="TEST",
        metrics={
            "M1": {"atr": 2.0},
            "signal_persistence": {"direction": direction, "consecutive_cycles": 5, "elapsed_seconds": 1.5},
            "microstructure": {
                "direction": direction,
                "confidence": 0.62,
                "data_quality": 0.85,
                "micro_regime": "IMPULSE",
                "windows": {
                    "1": {"directional_tick_ratio": 0.2 if direction == "BUY" else -0.2, "velocity_atr_per_second": 0.02 if direction == "BUY" else -0.02},
                    "3": {"directional_tick_ratio": 0.2 if direction == "BUY" else -0.2, "velocity_atr_per_second": 0.02 if direction == "BUY" else -0.02,
                          "quote_flow_imbalance_proxy": 0.25 if direction == "BUY" else -0.25,
                          "spread_expansion": 0.01},
                },
            },
            "verified_market_context": {"vwap_distance_atr": 0.4, "relative_volume": 1.0},
            "score_diagnostics": {
                "direct_score_decision": {"passed": True, "winner_direction": direction, "winner_score": 55.0, "margin": 25.0},
                "entry_quality_decision": {"economics": {"barrier_asymmetry_ok": True}},
            },
            "meta_controller": {"hard_signal_blocks": []},
            "v6_market_structure": structure,
        },
    )


def test_buy_and_sell_consensus() -> None:
    for direction in ("BUY", "SELL"):
        _CACHE.clear()
        result = build_v6_market_structure(snapshot(direction))
        assert result["valid"] is True
        assert result["consensus_direction"] == direction
        assert result["consensus_votes"] >= 2
        assert result["location_safe"] is True


def test_candidate_gate_requires_matching_two_of_three() -> None:
    snap = snapshot("BUY")
    _CACHE.clear()
    structure = build_v6_market_structure(snap)
    passed = evaluate_v6_candidate_gate(snap, signal_for("BUY", structure))
    assert passed["checks"]["structure_consensus"] is True
    assert passed["checks"]["structure_location_safe"] is True
    assert passed["allowed"] is True

    failed = evaluate_v6_candidate_gate(snap, signal_for("SELL", structure))
    assert failed["checks"]["structure_consensus"] is False
    assert "structure_consensus" in failed["failed_checks"]


def test_no_consensus_blocks() -> None:
    snap = snapshot("BUY")
    _CACHE.clear()
    structure = build_v6_market_structure(snap)
    structure = dict(structure)
    structure["consensus_direction"] = "NEUTRAL"
    structure["consensus_votes"] = 1
    gate = evaluate_v6_candidate_gate(snap, signal_for("BUY", structure))
    assert gate["allowed"] is False
    assert "structure_consensus" in gate["failed_checks"]



def test_graphical_market_map_is_rendered() -> None:
    snap = snapshot("BUY")
    _CACHE.clear()
    _LAST_RENDER_EPOCH.clear()
    structure = build_v6_market_structure(snap)
    with tempfile.TemporaryDirectory() as temp, patch.object(
        scalping_settings, "SCALPING_V6_CHART_EXPORT_FOLDER", temp
    ):
        result = maybe_render_v6_market_map(snap, structure, force=True)
        assert result["rendered"] is True, result
        path = Path(result["path"])
        assert path.exists()
        assert path.stat().st_size > 1000


def test_settings_are_shadow_first() -> None:
    assert scalping_settings.SCALPING_V6_SHADOW_MODE_DEFAULT is True
    assert scalping_settings.SCALPING_V6_DEMO_APPROVAL_REQUIRED is True
    assert scalping_settings.SCALPING_V6_STRUCTURE_MIN_VOTES == 2
    assert scalping_settings.SCALPING_V6_MAX_OPEN_POSITIONS == 1


if __name__ == "__main__":
    tests = [
        test_buy_and_sell_consensus,
        test_candidate_gate_requires_matching_two_of_three,
        test_no_consensus_blocks,
        test_graphical_market_map_is_rendered,
        test_settings_are_shadow_first,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"V6.2 market-structure tests passed: {len(tests)}/{len(tests)}")
