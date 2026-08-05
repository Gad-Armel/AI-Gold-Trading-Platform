from __future__ import annotations

import json

import joblib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.research.v63_barrier_policy import build_v63_barrier_plan
from services.research.v63_learned_gate import evaluate_v63_learned_gate
from services.research.v63_self_learning import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    load_v63_champion_status,
    load_v63_training_frame,
    score_v63_profile,
    train_v63_self_learner,
)


class V63SelfLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.history = root / "strict.jsonl"
        self.lane_folder = root / "lanes"
        self.model_folder = root / "models"
        self.patchers = [
            patch.object(scalping_settings, "SCALPING_V6_SHADOW_HISTORY_PATH", str(self.history)),
            patch.object(scalping_settings, "SCALPING_V6_SHADOW_LANE_HISTORY_FOLDER", str(self.lane_folder)),
            patch.object(scalping_settings, "SCALPING_V63_CHAMPION_MODEL_PATH", str(self.model_folder / "champion.joblib")),
            patch.object(scalping_settings, "SCALPING_V63_CHALLENGER_MODEL_PATH", str(self.model_folder / "challenger.joblib")),
            patch.object(scalping_settings, "SCALPING_V63_MODEL_REPORT_PATH", str(self.model_folder / "report.json")),
            patch.object(scalping_settings, "SCALPING_V63_DRIFT_REPORT_PATH", str(self.model_folder / "drift.json")),
            patch.object(scalping_settings, "SCALPING_V63_MODEL_REGISTRY_PATH", str(self.model_folder / "registry.json")),
            patch.object(scalping_settings, "SCALPING_V63_MIN_CLOSED_TRADES_TO_TRAIN", 80),
            patch.object(scalping_settings, "SCALPING_V63_MIN_TRAIN_TRADES_PER_FOLD", 40),
            patch.object(scalping_settings, "SCALPING_V63_MIN_OOS_SELECTED_TRADES", 15),
            patch.object(scalping_settings, "SCALPING_V63_MIN_WALK_FORWARD_FOLDS", 4),
            patch.object(scalping_settings, "SCALPING_V63_MIN_REGIME_SAMPLES", 10),
            patch.object(scalping_settings, "SCALPING_V63_DRIFT_RECENT_TRADES", 30),
            patch.object(scalping_settings, "SCALPING_V63_MAX_OOS_CALIBRATION_ERROR", 0.15),
            patch.object(scalping_settings, "SCALPING_V632_MIN_SELECTED_FOLDS", 2),
            patch.object(scalping_settings, "SCALPING_V632_MAX_NEGATIVE_SELECTED_FOLDS", 1),
            patch.object(scalping_settings, "SCALPING_V632_MIN_SELECTED_TRADES_PER_FOLD", 2),
            patch.object(scalping_settings, "SCALPING_V632_MIN_OOS_WIN_RATE_LOWER_BOUND", 0.45),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patchers):
            item.stop()
        self.temp.cleanup()

    @staticmethod
    def _profile(strength: float) -> dict:
        direction = "SELL"
        return {
            "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
            "shadow_lane": "EXPLORATORY",
            "session": "NEW_YORK",
            "direction": direction,
            "winner_score": 30 + 32 * strength,
            "score_margin": 10 + 35 * strength,
            "spread_usd": 0.20 + 0.03 * (1 - strength),
            "spread_atr": 0.10 + 0.04 * (1 - strength),
            "vwap_distance_atr": 1.8 - 1.5 * strength,
            "relative_volume": 0.8 + 0.4 * strength,
            "micro_direction": direction if strength >= 0.35 else "NEUTRAL",
            "micro_confidence": 0.45 + 0.30 * strength,
            "directional_micro_windows": 1 + int(strength >= 0.55),
            "micro_data_quality": 0.75 + 0.20 * strength,
            "micro_regime": "IMPULSE" if strength >= 0.55 else "ROTATION",
            "micro_regime_confidence": 0.50 + 0.40 * strength,
            "micro_quote_flow_imbalance": -0.20 - 0.60 * strength,
            "micro_efficiency_ratio": 0.30 + 0.60 * strength,
            "micro_stall_ratio": 0.55 - 0.40 * strength,
            "micro_spread_expansion_atr": 0.03 * (1 - strength),
            "micro_arrival_acceleration": 0.10 + 0.50 * strength,
            "micro_velocity_atr_s": -0.01 - 0.08 * strength,
            "micro_reversal_ratio": 0.50 * (1 - strength),
            "persistence_cycles": 2 + int(strength * 5),
            "persistence_seconds": 0.4 + strength * 1.6,
            "m1_atr": 1.5,
            "m1_rsi": 40.0,
            "m1_momentum": -0.5 - strength,
            "adx": 18 + 20 * strength,
            "regime": "TREND",
            "pattern": "DIRECT_SCORE",
            "structure_direction": direction,
            "structure_votes": 2 + int(strength >= 0.75),
            "structure_confidence": 0.55 + 0.35 * strength,
            "structure_location_safe": True,
            "structure_room_usd": 1.5,
            "htf_direction": direction,
            "level_direction": direction if strength >= 0.45 else "NEUTRAL",
            "level_event": "BREAK_RETEST",
            "order_block_direction": direction if strength >= 0.65 else "NEUTRAL",
        }

    def _write_training_history(self, count: int = 180) -> None:
        path = self.lane_folder / "exploratory_history.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with path.open("w", encoding="utf-8") as handle:
            for index in range(count):
                # A deterministic coprime stride distributes the full strength
                # range through every chronological fold. A simple 20-row saw
                # tooth made the final holdout an artificial distribution shift.
                strength = ((index * 37) % 101) / 100.0
                win = strength >= 0.48
                # A small deterministic noise component prevents a perfect toy classifier.
                if index % 17 == 0:
                    win = not win
                pnl = 0.95 if win else -1.05
                opened = start + timedelta(minutes=index * 3)
                row = {
                    "status": "CLOSED",
                    "shadow_lane": "EXPLORATORY",
                    "candidate_key": f"test-{index}",
                    "opened_at": opened.isoformat(),
                    "closed_at": (opened + timedelta(seconds=25)).isoformat(),
                    "final_profit_usd": pnl,
                    "close_reason": "TRIPLE_BARRIER_TARGET" if win else "TRIPLE_BARRIER_HARD_STOP",
                    "entry_profile": self._profile(strength),
                }
                handle.write(json.dumps(row) + "\n")

    def test_insufficient_data_does_not_create_champion(self) -> None:
        report = train_v63_self_learner()
        self.assertFalse(report["approved"])
        self.assertFalse(Path(scalping_settings.SCALPING_V63_CHAMPION_MODEL_PATH).exists())

    def test_chronological_model_can_promote_high_precision_champion(self) -> None:
        self._write_training_history()
        report = train_v63_self_learner()
        self.assertTrue(report["approved"], report)
        self.assertTrue(report["promoted"], report)
        self.assertIn("GRADIENT_BOOSTING", {item["model_name"] for item in report["all_models"]})
        self.assertIn("fold_stability_passed", report["best_model"])
        self.assertIn("permutation_brier_importance", report["best_model"])
        self.assertTrue(report["best_model"]["untouched_holdout"]["available"])
        self.assertTrue(report["best_model"]["untouched_holdout"]["passes"])
        self.assertLess(
            report["best_model"]["threshold_selection_rows"],
            report["best_model"]["oos_rows"],
        )
        status = load_v63_champion_status()
        self.assertTrue(status["approved"], status)
        strong = score_v63_profile(self._profile(0.95))
        weak = score_v63_profile(self._profile(0.10))
        self.assertGreater(strong["probability_win"], weak["probability_win"])
        self.assertTrue(strong["allowed"], strong)

    def test_incompatible_champion_schema_is_rejected(self) -> None:
        champion_path = Path(scalping_settings.SCALPING_V63_CHAMPION_MODEL_PATH)
        champion_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "format_version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "strategy_id": "OLD_STRATEGY",
            "approved": True,
            "numeric_features": [],
            "categorical_features": [],
        }
        joblib.dump(artifact, champion_path)
        status = load_v63_champion_status()
        self.assertFalse(status["approved"], status)
        self.assertIn("strategy_id", status["incompatibilities"])
        self.assertIn("feature_schema", status["incompatibilities"])

    def test_pre_holdout_artifact_is_rejected(self) -> None:
        champion_path = Path(scalping_settings.SCALPING_V63_CHAMPION_MODEL_PATH)
        champion_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "format_version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
            "approved": True,
            "numeric_features": list(NUMERIC_FEATURES),
            "categorical_features": list(CATEGORICAL_FEATURES),
        }
        joblib.dump(artifact, champion_path)
        status = load_v63_champion_status()
        self.assertFalse(status["approved"], status)
        self.assertIn("artifact_format", status["incompatibilities"])

    def test_learned_lane_is_shadow_only_and_blocks_without_model(self) -> None:
        snapshot = ScalpingSnapshotState(
            symbol="XAUUSD", timestamp=datetime.now(timezone.utc), bid=4000.0, ask=4000.2,
            spread=0.2, mid=4000.1, session="NEW_YORK", active_sessions=["NEW_YORK"],
            contract_size=100.0, quote_age_seconds=0.0,
        )
        signal = ScalpSignalState(
            action="SELL", direction="SELL", allowed=True, score=55.0, confidence=0.8,
            target_profit_usd=0.9, stop_loss_usd=1.1, signal_key="test", pattern="DIRECT_SCORE",
            metrics={"M1": {"atr": 1.5, "rsi": 40, "momentum": -1}, "v6_market_structure": {}},
            reasons=[], block_reasons=[],
        )
        base = {
            "lane": "EXPLORATORY", "demo_eligible": False, "allowed": True, "direction": "SELL",
            "checks": {"base": True}, "failed_checks": [], "winner_score": 50.0,
            "score_margin": 30.0, "spread_usd": 0.2, "spread_atr": 0.1,
            "vwap_distance_atr": 0.5, "relative_volume": 1.0, "micro_direction": "SELL",
            "micro_confidence": 0.6, "directional_micro_windows": 1, "persistence_cycles": 2,
            "persistence_seconds": 0.5, "structure_direction": "SELL", "structure_votes": 2,
        }
        learned = evaluate_v63_learned_gate(snapshot, signal, base)
        self.assertFalse(learned["allowed"])
        self.assertFalse(learned["demo_eligible"])
        self.assertIn("approved_calibrated_model", learned["failed_checks"])


    def test_training_frame_decorrelates_lanes_and_excludes_learned_feedback(self) -> None:
        opened = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
        profile = self._profile(0.8)
        for lane, pnl in (("STRICT", 0.9), ("BALANCED", 0.8), ("EXPLORATORY", 0.7), ("LEARNED", 0.6)):
            path = self.history if lane == "STRICT" else self.lane_folder / f"{lane.lower()}_history.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "status": "CLOSED",
                "shadow_lane": lane,
                "candidate_key": f"same-episode-{lane}",
                "direction": "SELL",
                "entry_price": 4000.10,
                "opened_at": opened.isoformat(),
                "closed_at": (opened + timedelta(seconds=20)).isoformat(),
                "final_profit_usd": pnl,
                "close_reason": "TRIPLE_BARRIER_TARGET",
                "entry_profile": {**profile, "shadow_lane": lane},
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        frame = load_v63_training_frame()
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["source_lane"], "STRICT")
        self.assertTrue(frame.attrs["excluded_learned_lane"])
        self.assertEqual(frame.attrs["pre_dedup_rows"], 3)

    def test_dynamic_barrier_improves_payoff_geometry(self) -> None:
        snapshot = ScalpingSnapshotState(
            symbol="XAUUSD", timestamp=datetime.now(timezone.utc), bid=4000.0, ask=4000.23,
            spread=0.23, mid=4000.115, session="NEW_YORK", active_sessions=["NEW_YORK"],
            contract_size=100.0, quote_age_seconds=0.0,
        )
        plan = build_v63_barrier_plan(snapshot, {"spread_atr": 0.14})
        self.assertGreaterEqual(plan["target_stop_ratio"], scalping_settings.SCALPING_V63_MIN_TARGET_STOP_RATIO)
        self.assertLess(plan["breakeven_win_rate"], 0.59)


if __name__ == "__main__":
    unittest.main(verbosity=2)
