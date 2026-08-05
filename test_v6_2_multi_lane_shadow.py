from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.research.v6_candidate_gate import (
    apply_v6_candidate_gate,
    evaluate_v6_shadow_lane_gates,
)
from services.research.v6_shadow_engine import update_v6_shadow_lanes
from services.research.v6_feed_guard import evaluate_v6_feed_guard


def snapshot(*, spread: float = 0.24, quote_age: float = 0.1) -> ScalpingSnapshotState:
    return ScalpingSnapshotState(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        bid=4000.0,
        ask=4000.0 + spread,
        spread=spread,
        mid=4000.0 + spread / 2,
        session="NEW_YORK",
        active_sessions=["NEW_YORK"],
        contract_size=100.0,
        quote_age_seconds=quote_age,
        tick_time_msc=123456,
    )


def signal(
    *,
    direction: str = "SELL",
    winner: float = 40.0,
    margin: float = 25.0,
    micro_direction: str = "SELL",
    micro_confidence: float = 0.52,
    vwap: float = 1.2,
    rel_volume: float = 1.0,
    cycles: int = 3,
    seconds: float = 0.8,
    structure_direction: str = "SELL",
    buy_votes: int = 0,
    sell_votes: int = 2,
) -> ScalpSignalState:
    ratios = (-0.20, -0.18, 0.02) if direction == "SELL" else (0.20, 0.18, -0.02)
    velocities = (-0.02, -0.015, 0.001) if direction == "SELL" else (0.02, 0.015, -0.001)
    return ScalpSignalState(
        action=direction,
        direction=direction,
        allowed=False,
        score=winner,
        confidence=0.6,
        target_profit_usd=0.85,
        stop_loss_usd=1.25,
        signal_key="lane-test",
        pattern="DIRECT_SCORE",
        metrics={
            "M1": {"atr": 2.0, "rsi": 50.0, "momentum": -1.0},
            "score_diagnostics": {
                "direct_score_decision": {
                    "passed": True,
                    "winner_direction": direction,
                    "winner_score": winner,
                    "margin": margin,
                },
                "entry_quality_decision": {"economics": {"barrier_asymmetry_ok": True}},
            },
            "signal_persistence": {
                "direction": direction,
                "consecutive_cycles": cycles,
                "elapsed_seconds": seconds,
            },
            "microstructure": {
                "direction": micro_direction,
                "confidence": micro_confidence,
                "data_quality": 0.80,
                "micro_regime": "IMPULSE",
                "windows": {
                    "1": {"directional_tick_ratio": ratios[0], "velocity_atr_per_second": velocities[0]},
                    "3": {"directional_tick_ratio": ratios[1], "velocity_atr_per_second": velocities[1],
                          "quote_flow_imbalance_proxy": -0.25 if direction == "SELL" else 0.25,
                          "spread_expansion": 0.01},
                    "5": {"directional_tick_ratio": ratios[2], "velocity_atr_per_second": velocities[2]},
                },
            },
            "verified_market_context": {
                "vwap_distance_atr": vwap,
                "relative_volume": rel_volume,
            },
            "meta_controller": {"hard_signal_blocks": []},
            "v6_market_structure": {
                "valid": True,
                "consensus_direction": structure_direction,
                "consensus_votes": max(buy_votes, sell_votes),
                "buy_votes": buy_votes,
                "sell_votes": sell_votes,
                "confidence": 0.7,
                "location_safe": True,
                "room_to_target_usd": 2.0,
                "reason": "test structure",
            },
        },
        reasons=[],
        block_reasons=[],
    )


class V62MultiLaneTests(unittest.TestCase):
    def test_balanced_collects_when_strict_is_too_narrow(self) -> None:
        gates = evaluate_v6_shadow_lane_gates(snapshot(), signal())
        self.assertFalse(gates["STRICT"]["allowed"])
        self.assertIn("winner_score", gates["STRICT"]["failed_checks"])
        self.assertTrue(gates["BALANCED"]["allowed"], gates["BALANCED"])
        self.assertTrue(gates["EXPLORATORY"]["allowed"], gates["EXPLORATORY"])
        self.assertTrue(gates["STRICT"]["demo_eligible"])
        self.assertFalse(gates["BALANCED"]["demo_eligible"])

    def test_exploratory_never_accepts_opposite_structural_consensus(self) -> None:
        gates = evaluate_v6_shadow_lane_gates(
            snapshot(),
            signal(
                direction="BUY",
                micro_direction="BUY",
                structure_direction="SELL",
                buy_votes=0,
                sell_votes=2,
            ),
        )
        self.assertFalse(gates["EXPLORATORY"]["allowed"])
        self.assertIn("structure_consensus", gates["EXPLORATORY"]["failed_checks"])

    def test_fast_lane_requires_one_and_five_second_tick_alignment(self) -> None:
        aligned = signal(winner=46.0, margin=30.0, micro_confidence=0.65)
        aligned.metrics["microstructure"]["windows"]["5"]["directional_tick_ratio"] = -0.20
        aligned.metrics["microstructure"]["windows"]["5"]["velocity_atr_per_second"] = -0.015
        gates = evaluate_v6_shadow_lane_gates(
            snapshot(spread=0.15), aligned
        )
        self.assertTrue(gates["FAST"]["allowed"], gates["FAST"])
        self.assertTrue(gates["FAST"]["fast_horizons_aligned"])
        self.assertEqual(gates["FAST"]["max_hold_seconds"], 15.0)
        broken = aligned
        broken.metrics["microstructure"]["windows"]["5"]["directional_tick_ratio"] = 0.20
        blocked = evaluate_v6_shadow_lane_gates(snapshot(spread=0.15), broken)["FAST"]
        self.assertIn("fast_horizon_alignment", blocked["failed_checks"])

    def test_non_strict_lane_cannot_be_applied_to_demo(self) -> None:
        gates = evaluate_v6_shadow_lane_gates(snapshot(), signal())
        with self.assertRaises(ValueError):
            apply_v6_candidate_gate(signal(), gates["BALANCED"])

    def test_multi_lane_engine_keeps_independent_books(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patches = [
                patch.object(scalping_settings, "SCALPING_V6_SHADOW_LANE_STATE_PATH", str(root / "lanes.json")),
                patch.object(scalping_settings, "SCALPING_V6_SHADOW_HISTORY_PATH", str(root / "strict_history.jsonl")),
                patch.object(scalping_settings, "SCALPING_V6_SHADOW_CANDIDATES_PATH", str(root / "strict_candidates.jsonl")),
                patch.object(scalping_settings, "SCALPING_V6_SHADOW_LANE_HISTORY_FOLDER", str(root / "histories")),
                patch.object(scalping_settings, "SCALPING_V6_SHADOW_LANE_CANDIDATES_FOLDER", str(root / "candidates")),
                patch.object(scalping_settings, "SCALPING_V6_CANDIDATE_DEDUP_SECONDS", 0),
            ]
            for item in patches:
                item.start()
            try:
                gates = evaluate_v6_shadow_lane_gates(snapshot(), signal())
                result = update_v6_shadow_lanes(snapshot(), signal(), gates)
                self.assertNotIn("STRICT", result["opened_lanes"])
                self.assertIn("BALANCED", result["opened_lanes"])
                self.assertIn("EXPLORATORY", result["opened_lanes"])
                self.assertIsNone(result["lanes"]["STRICT"]["open_trade"])
                self.assertIsNotNone(result["lanes"]["BALANCED"]["open_trade"])
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_stale_quote_pauses_before_expensive_signal_analysis(self) -> None:
        result = evaluate_v6_feed_guard(snapshot(quote_age=5.0))
        self.assertTrue(result["paused"])
        self.assertIn("stale", result["reason"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
