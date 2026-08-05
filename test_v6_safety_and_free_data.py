from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import scalping_settings
from services.execution.scalp_demo_execution_gate import evaluate_scalp_demo_execution_gate
from services.decision.demo_signal_persistence import apply_demo_signal_persistence, reset_demo_signal_persistence
from services.execution.scalp_demo_position_manager import _v6_thesis_exit_reason
from models.scalping_state import ScalpSignalState
from services.news.free_macro_context import build_free_macro_health


class V6SafetyAndFreeDataTests(unittest.TestCase):
    def test_shadow_import_graph_has_no_order_send(self) -> None:
        root = Path(__file__).parent
        for relative in ("run_scalping_shadow_loop.py", "services/bot/v6_shadow_loop_runner.py",
                         "services/bot/v6_shadow_cycle_runner.py", "services/research/v6_shadow_engine.py"):
            tree = ast.parse((root/relative).read_text(encoding="utf-8"))
            calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
            self.assertNotIn("order_send", calls, relative)

    def test_demo_execution_blocks_without_approval_before_mt5_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.object(
            scalping_settings, "SCALPING_V6_DEMO_APPROVAL_PATH", str(Path(temp)/"missing.json")
        ):
            result = evaluate_scalp_demo_execution_gate(symbol="XAUUSD", mt5_module=None)
        self.assertFalse(result["allowed"])
        self.assertTrue(any("approval" in reason.lower() for reason in result["reasons"]))

    def test_real_execution_is_disabled_and_one_position_only(self) -> None:
        self.assertFalse(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED)
        self.assertEqual(scalping_settings.SCALPING_V6_MAX_OPEN_POSITIONS, 1)
        self.assertFalse(scalping_settings.SCALPING_V6_PYRAMID_ENABLED)

    def test_free_macro_context_fail_open_without_keys_or_network(self) -> None:
        with patch("services.news.free_macro_context._get_json", side_effect=OSError("offline")):
            result = build_free_macro_health()
        self.assertIsInstance(result.get("providers"), list)
        self.assertEqual(result.get("success_count"), 0)
        names = {item.get("provider") for item in result.get("providers", [])}
        self.assertTrue({"BLS", "FRED", "BEA", "Finnhub", "AlphaVantage", "TwelveData"}.issubset(names))
        self.assertIn("MT5 remains authoritative", result.get("note", ""))


    def test_approved_demo_uses_exact_v6_structure_gate_not_legacy_policy(self) -> None:
        root = Path(__file__).parent
        source = (root / "services/bot/scalping_demo_cycle_runner.py").read_text(encoding="utf-8")
        for token in (
            "build_v6_market_structure",
            "evaluate_v6_candidate_gate",
            "apply_v6_candidate_gate",
            "maybe_render_v6_market_map",
        ):
            self.assertIn(token, source)
        self.assertNotIn("evaluate_demo_entry_policy", source)
        self.assertNotIn("apply_demo_entry_policy", source)


    def test_demo_risk_guard_has_no_legacy_entry_or_adaptive_spread_policy(self) -> None:
        root = Path(__file__).parent
        source = (root / "services/risk/scalping_demo_risk_guard.py").read_text(encoding="utf-8")
        self.assertIn("v6_candidate_gate", source)
        self.assertIn("return_to_shadow_required", source)
        self.assertNotIn("evaluate_adaptive_spread_policy", source)
        self.assertEqual(scalping_settings.SCALPING_DEMO_RECOVERY_MODE_AFTER_LOSSES, 0)


    def test_persistence_counts_unique_mt5_observations_not_polling_loops(self) -> None:
        signal = ScalpSignalState(
            action="SELL", direction="SELL", allowed=True, score=60, confidence=.8,
            target_profit_usd=.85, stop_loss_usd=1.25, signal_key="persist", pattern="DIRECT_SCORE",
            metrics={
                "score_diagnostics": {"direct_score_decision": {
                    "passed": True, "winner_direction": "SELL", "winner_score": 60, "margin": 30
                }},
                "microstructure": {"direction": "SELL", "confidence": .7},
                "meta_controller": {"checks": {
                    "news_safe": True, "execution_economics_acceptable": True,
                    "microstructure_data_ready": True,
                    "no_strong_microstructure_opposition": True,
                    "no_strong_intermarket_opposition": True,
                }, "hard_signal_blocks": []},
            }, reasons=[], block_reasons=[]
        )
        reset_demo_signal_persistence()
        _, first = apply_demo_signal_persistence(signal, now_monotonic=1.0, observation_id=100)
        _, duplicate = apply_demo_signal_persistence(signal, now_monotonic=1.4, observation_id=100)
        _, second = apply_demo_signal_persistence(signal, now_monotonic=1.5, observation_id=101)
        self.assertEqual(first["consecutive_cycles"], 1)
        self.assertEqual(duplicate["consecutive_cycles"], 1)
        self.assertFalse(duplicate["count_advanced"])
        self.assertEqual(second["consecutive_cycles"], 2)
        self.assertTrue(second["count_advanced"])

    def test_v6_thesis_exits_match_shadow_rules(self) -> None:
        signal = ScalpSignalState(
            action="WAIT", direction="SELL", allowed=False, score=0, confidence=0,
            target_profit_usd=.85, stop_loss_usd=1.25, signal_key="x", pattern="WAIT",
            metrics={"microstructure": {"direction": "BUY", "confidence": .70}},
            reasons=[], block_reasons=[]
        )
        self.assertEqual(
            _v6_thesis_exit_reason(signal, "SELL", 12, .05, -.35),
            "V6 no-progress thesis exit",
        )
        self.assertEqual(
            _v6_thesis_exit_reason(signal, "SELL", 5, .10, -.10),
            "V6 strong-opposite-tape thesis exit",
        )
        self.assertEqual(
            _v6_thesis_exit_reason(signal, "SELL", 5, .30, 0.0),
            "V6 break-even protection",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
