from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.research.v6_shadow_engine import update_v6_shadow


def snap(bid: float, ask: float) -> ScalpingSnapshotState:
    return ScalpingSnapshotState(
        symbol="XAUUSD", timestamp=datetime.now(timezone.utc), bid=bid, ask=ask,
        spread=round(ask-bid, 5), mid=(bid+ask)/2, session="NEW_YORK",
        active_sessions=["NEW_YORK"], contract_size=100.0, quote_age_seconds=0.0,
    )


def sig(micro_direction: str = "SELL", micro_confidence: float = 0.65) -> ScalpSignalState:
    return ScalpSignalState(
        action="SELL", direction="SELL", allowed=True, score=55, confidence=.8,
        target_profit_usd=.85, stop_loss_usd=1.25, signal_key="v6", pattern="V6",
        metrics={"M1": {"atr": 2.0}, "microstructure": {"direction": micro_direction, "confidence": micro_confidence},
                 "verified_market_context": {"relative_volume": 1.0, "vwap_distance_atr": 0.3, "adx_m5": 27.5}},
        reasons=[], block_reasons=[]
    )


def gate(allowed: bool = True, structure_direction: str = "SELL") -> dict:
    return {"allowed": allowed, "direction": "SELL", "winner_score": 55, "score_margin": 30,
            "spread_usd": .25, "spread_atr": .125, "vwap_distance_atr": .3,
            "relative_volume": 1.0, "micro_direction": "SELL", "micro_confidence": .65,
            "directional_micro_windows": 3, "persistence_cycles": 5, "persistence_seconds": 1.5,
            "structure_direction": structure_direction, "structure_votes": 2}


class V6ShadowEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patchers = [
            patch.object(scalping_settings, "SCALPING_V6_SHADOW_STATE_PATH", str(root / "state.json")),
            patch.object(scalping_settings, "SCALPING_V6_SHADOW_HISTORY_PATH", str(root / "history.jsonl")),
            patch.object(scalping_settings, "SCALPING_V6_SHADOW_CANDIDATES_PATH", str(root / "candidates.jsonl")),
            patch.object(scalping_settings, "SCALPING_V6_CANDIDATE_DEDUP_SECONDS", 0),
            patch.object(scalping_settings, "SCALPING_V63_DYNAMIC_BARRIERS_ENABLED", False),
        ]
        for item in self.patchers: item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patchers): item.stop()
        self.temp.cleanup()

    def test_shadow_path_never_calls_mt5_order_send(self) -> None:
        source = Path(__file__).parent.joinpath("services/research/v6_shadow_engine.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(", source)

    def test_open_and_target_close(self) -> None:
        opened = update_v6_shadow(snap(4000.00, 4000.25), sig(), gate())
        self.assertEqual(opened["action"], "OPEN_SHADOW")
        self.assertAlmostEqual(opened["open_trade"]["entry_profile"]["adx"], 27.5)
        # SELL entry at bid=4000.00; close at ask=3999.10 -> +$0.90 for 0.01*100.
        closed = update_v6_shadow(snap(3998.85, 3999.10), sig(), gate(False))
        self.assertEqual(closed["action"], "CLOSE_SHADOW")
        self.assertEqual(closed["closed_record"]["close_reason"], "TRIPLE_BARRIER_TARGET")
        self.assertAlmostEqual(closed["closed_record"]["final_profit_usd"], .85, places=4)
        self.assertAlmostEqual(closed["closed_record"]["observed_market_profit_usd"], .90, places=4)
        self.assertAlmostEqual(closed["closed_record"]["barrier_overshoot_usd"], .05, places=4)
        self.assertEqual(closed["closed_record"]["shadow_fill_model"], "PLANNED_TARGET_BARRIER")

    def test_target_gap_does_not_credit_polling_overshoot(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate())
        # The next poll observes a +$2.25 SELL profit, but the planned
        # broker-side target is only $0.85 in this static-barrier test.
        closed = update_v6_shadow(snap(3997.50, 3997.75), sig(), gate(False))
        record = closed["closed_record"]
        self.assertEqual(record["close_reason"], "TRIPLE_BARRIER_TARGET")
        self.assertAlmostEqual(record["observed_market_profit_usd"], 2.25, places=4)
        self.assertAlmostEqual(record["final_profit_usd"], .85, places=4)
        self.assertAlmostEqual(record["barrier_overshoot_usd"], 1.40, places=4)
        self.assertIn("target overshoot not credited", closed["message"])

    def test_hard_stop_keeps_adverse_observed_gap(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate())
        closed = update_v6_shadow(snap(4002.00, 4002.25), sig(), gate(False))
        record = closed["closed_record"]
        self.assertEqual(record["close_reason"], "TRIPLE_BARRIER_HARD_STOP")
        self.assertAlmostEqual(record["observed_market_profit_usd"], -2.25, places=4)
        self.assertAlmostEqual(record["final_profit_usd"], -2.25, places=4)
        self.assertEqual(record["shadow_fill_model"], "OBSERVED_EXECUTABLE_QUOTE")

    def test_long_process_gap_is_audit_only(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate())
        state_path = Path(scalping_settings.SCALPING_V6_SHADOW_STATE_PATH)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["open_trade"]["last_fresh_update_epoch"] = (
            time.time()
            - float(scalping_settings.SCALPING_V6_MAX_RESEARCH_MONITORING_GAP_SECONDS)
            - 10.0
        )
        state_path.write_text(json.dumps(state), encoding="utf-8")
        closed = update_v6_shadow(snap(4041.00, 4041.15), sig(), gate(False))
        record = closed["closed_record"]
        self.assertEqual(record["close_reason"], "UNMONITORED_SESSION_GAP")
        self.assertFalse(record["research_eligible"])
        self.assertAlmostEqual(record["observed_market_profit_usd"], -41.15, places=4)
        self.assertIn("audit-only", record["research_exclusion_reason"])

    def test_hard_stop_close(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate())
        closed = update_v6_shadow(snap(4001.20, 4001.50), sig(), gate(False))
        self.assertEqual(closed["action"], "CLOSE_SHADOW")
        self.assertEqual(closed["closed_record"]["close_reason"], "TRIPLE_BARRIER_HARD_STOP")

    def test_gate_failure_records_no_position(self) -> None:
        result = update_v6_shadow(snap(4000.00, 4000.25), sig(), gate(False))
        self.assertEqual(result["action"], "NO_ACTION")
        state = json.loads(Path(scalping_settings.SCALPING_V6_SHADOW_STATE_PATH).read_text())
        self.assertIsNone(state.get("open_trade"))

    def test_close_is_visible_and_cannot_reopen_same_cycle(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate(True))
        result = update_v6_shadow(snap(3998.85, 3999.10), sig(), gate(True))
        self.assertEqual(result["action"], "CLOSE_SHADOW")
        self.assertTrue(result["closed_this_cycle"])
        self.assertIsNotNone(result["closed_record"])
        self.assertIsNone(result["open_trade"])
        self.assertTrue(result["rearm"]["required"])

    def test_normal_exit_requires_invalid_episode_before_reentry(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate(True))
        update_v6_shadow(snap(3998.85, 3999.10), sig(), gate(True))
        blocked = update_v6_shadow(snap(3998.80, 3999.05), sig(), gate(True))
        self.assertEqual(blocked["action"], "REARM_BLOCKED")
        self.assertIsNone(blocked["open_trade"])
        rearmed = update_v6_shadow(snap(3998.80, 3999.05), sig(), gate(False))
        self.assertEqual(rearmed["action"], "EPISODE_REARMED")
        self.assertIsNone(rearmed["open_trade"])
        reopened = update_v6_shadow(snap(3998.70, 3998.95), sig(), gate(True))
        self.assertEqual(reopened["action"], "OPEN_SHADOW")

    def test_hard_stop_requires_structure_reset(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate(True))
        stopped = update_v6_shadow(snap(4001.20, 4001.50), sig(), gate(True))
        self.assertEqual(stopped["closed_record"]["close_reason"], "TRIPLE_BARRIER_HARD_STOP")
        still_locked = update_v6_shadow(snap(4001.10, 4001.35), sig(), gate(False, "SELL"))
        self.assertEqual(still_locked["action"], "REARM_BLOCKED")
        rearmed = update_v6_shadow(snap(4001.00, 4001.25), sig(), gate(False, "NEUTRAL"))
        self.assertEqual(rearmed["action"], "EPISODE_REARMED")
        reopened = update_v6_shadow(snap(4000.90, 4001.15), sig(), gate(True, "SELL"))
        self.assertEqual(reopened["action"], "OPEN_SHADOW")

    def test_no_progress_requires_direction_reset_not_one_noisy_gate_miss(self) -> None:
        update_v6_shadow(snap(4000.00, 4000.25), sig(), gate(True))
        # Force a no-progress exit after the configured active holding period.
        state_path = Path(scalping_settings.SCALPING_V6_SHADOW_STATE_PATH)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["open_trade"]["active_hold_seconds"] = float(
            scalping_settings.SCALPING_V6_NO_PROGRESS_CHECK_SECONDS
        )
        state["open_trade"]["last_fresh_update_epoch"] = 0.0
        state_path.write_text(json.dumps(state), encoding="utf-8")
        closed = update_v6_shadow(snap(4000.30, 4000.55), sig(), gate(False))
        self.assertEqual(closed["closed_record"]["close_reason"], "NO_PROGRESS_THESIS_EXIT")

        # The same SELL candidate remains locked even though its gate flickers
        # invalid. Only a genuine candidate-direction reset rearms the lane.
        blocked = update_v6_shadow(snap(4000.25, 4000.50), sig(), gate(False))
        self.assertEqual(blocked["action"], "REARM_BLOCKED")
        reset_gate = gate(False, "NEUTRAL")
        reset_gate["direction"] = "BUY"
        rearmed = update_v6_shadow(snap(4000.20, 4000.45), sig(), reset_gate)
        self.assertEqual(rearmed["action"], "EPISODE_REARMED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
