from __future__ import annotations

import unittest
from datetime import datetime, timezone

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.research.v6_candidate_gate import evaluate_v6_candidate_gate


def snapshot(*, spread: float = 0.25, quote_age: float = 0.1) -> ScalpingSnapshotState:
    return ScalpingSnapshotState(
        symbol="XAUUSD", timestamp=datetime.now(timezone.utc), bid=4000.00,
        ask=4000.00 + spread, spread=spread, mid=4000.00 + spread / 2,
        session="NEW_YORK", active_sessions=["NEW_YORK"], contract_size=100.0,
        quote_age_seconds=quote_age,
    )


def signal(*, direction: str = "SELL", winner: float = 55.0, margin: float = 30.0,
           micro_direction: str = "SELL", micro_confidence: float = 0.65,
           vwap: float = 0.50, rel_volume: float = 1.0,
           cycles: int = 5, seconds: float = 1.5, quote_flow: float | None = None,
           spread_expansion: float = 0.01, micro_regime: str = "IMPULSE",
           data_quality: float = 0.85, context_mode: str = "TREND",
           context_direction: str | None = None) -> ScalpSignalState:
    ratios = (-0.25, -0.22, -0.20) if direction == "SELL" else (0.25, 0.22, 0.20)
    velocities = (-0.02, -0.018, -0.015) if direction == "SELL" else (0.02, 0.018, 0.015)
    return ScalpSignalState(
        action=direction, direction=direction, allowed=True, score=winner, confidence=0.7,
        target_profit_usd=0.85, stop_loss_usd=1.25, signal_key="v6-test", pattern="DIRECT_SCORE",
        metrics={
            "M1": {"atr": 2.0, "rsi": 50, "momentum": -1 if direction == "SELL" else 1},
            "score_diagnostics": {
                "direct_score_decision": {"passed": True, "winner_direction": direction, "winner_score": winner, "margin": margin},
                "entry_quality_decision": {"economics": {"barrier_asymmetry_ok": True}},
            },
            "signal_persistence": {"direction": direction, "consecutive_cycles": cycles, "elapsed_seconds": seconds},
            "microstructure": {
                "direction": micro_direction, "confidence": micro_confidence,
                "data_quality": data_quality, "micro_regime": micro_regime,
                "windows": {
                    "1": {"directional_tick_ratio": ratios[0], "velocity_atr_per_second": velocities[0]},
                    "3": {"directional_tick_ratio": ratios[1], "velocity_atr_per_second": velocities[1],
                          "quote_flow_imbalance_proxy": quote_flow if quote_flow is not None else (-0.25 if direction == "SELL" else 0.25),
                          "spread_expansion": spread_expansion},
                    "5": {"directional_tick_ratio": ratios[2], "velocity_atr_per_second": velocities[2]},
                },
            },
            "verified_market_context": {"vwap_distance_atr": vwap, "relative_volume": rel_volume},
            "regime": {"mode": context_mode, "direction": context_direction or direction},
            "meta_controller": {"hard_signal_blocks": []},
            "v6_market_structure": {
                "valid": True,
                "consensus_direction": direction,
                "consensus_votes": 2,
                "confidence": 0.72,
                "location_safe": True,
                "room_to_target_usd": 2.0,
                "reason": f"{direction} structural consensus 2/3.",
            },
        }, reasons=[], block_reasons=[],
    )


class V6CandidateGateTests(unittest.TestCase):
    def test_high_quality_candidate_passes(self) -> None:
        result = evaluate_v6_candidate_gate(snapshot(), signal())
        self.assertTrue(result["allowed"], result)

    def test_spread_above_data_backed_limit_blocks(self) -> None:
        result = evaluate_v6_candidate_gate(snapshot(spread=0.28), signal())
        self.assertFalse(result["allowed"])
        self.assertIn("spread", result["failed_checks"])

    def test_far_from_vwap_blocks(self) -> None:
        result = evaluate_v6_candidate_gate(snapshot(), signal(vwap=1.01))
        self.assertFalse(result["allowed"])
        self.assertIn("vwap_location", result["failed_checks"])

    def test_neutral_or_weak_tape_blocks(self) -> None:
        result = evaluate_v6_candidate_gate(snapshot(), signal(micro_direction="NEUTRAL", micro_confidence=0.0))
        self.assertFalse(result["allowed"])
        self.assertIn("micro_alignment", result["failed_checks"])

    def test_persistence_and_stale_quote_are_hard_requirements(self) -> None:
        result = evaluate_v6_candidate_gate(snapshot(quote_age=2.1), signal(cycles=4, seconds=1.0))
        self.assertFalse(result["allowed"])
        self.assertIn("quote_fresh", result["failed_checks"])
        self.assertIn("persistence_cycles", result["failed_checks"])
        self.assertIn("persistence_seconds", result["failed_checks"])

    def test_real_micro_window_schema_passes_and_adverse_quote_flow_blocks(self) -> None:
        passed = evaluate_v6_candidate_gate(snapshot(), signal())
        self.assertTrue(passed["allowed"], passed)
        self.assertEqual(passed["directional_micro_windows"], 3)
        blocked = evaluate_v6_candidate_gate(snapshot(), signal(quote_flow=0.30))
        self.assertFalse(blocked["allowed"])
        self.assertIn("quote_flow_alignment", blocked["failed_checks"])

    def test_spread_expansion_and_dislocated_tape_block(self) -> None:
        expanding = evaluate_v6_candidate_gate(snapshot(), signal(spread_expansion=0.10))
        self.assertIn("spread_stability", expanding["failed_checks"])
        dislocated = evaluate_v6_candidate_gate(snapshot(), signal(micro_regime="DISLOCATED"))
        self.assertIn("micro_regime_safe", dislocated["failed_checks"])

    def test_strict_blocks_explicit_no_trade_or_opposite_context_regime(self) -> None:
        no_trade = evaluate_v6_candidate_gate(snapshot(), signal(context_mode="NO_TRADE"))
        self.assertIn("context_regime_safe", no_trade["failed_checks"])
        opposite = evaluate_v6_candidate_gate(snapshot(), signal(context_direction="BUY"))
        self.assertIn("context_regime_alignment", opposite["failed_checks"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
