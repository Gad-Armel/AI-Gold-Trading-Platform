from datetime import datetime, timedelta, timezone
import unittest

from services.research.gold_manual_scalp_advisor import build_manual_scalp_advisory


class GoldManualScalpAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
        stamp = (self.now - timedelta(seconds=1)).isoformat()
        self.candle_report = {
            "generated_at": stamp,
            "symbol": "XAUUSD",
            "bid": 2499.99,
            "ask": 2500.01,
            "horizons": {
                "SCALP": {
                    "action": "BUY",
                    "bias": "BUY",
                    "directional_score": 76,
                    "levels": {
                        "entry_reference": 2500.01,
                        "entry_zone": [2499.98, 2500.04],
                        "sl": 2499.81,
                        "tp1": 2500.20,
                        "tp2": 2500.40,
                        "tp3": 2500.60,
                    },
                }
            },
        }
        self.tick_report = {
            "generated_at": stamp,
            "symbol": "XAUUSD",
            "bid": 2500.00,
            "ask": 2500.02,
            "latest_tick_age_seconds": 0.2,
            "available": True,
            "horizons": {
                "SCALP": {
                    "action": "BUY",
                    "bias": "BUY",
                    "directional_score": 71,
                    "source_usable": True,
                    "window_metrics": {"1": {"data_quality": 0.9}},
                }
            },
        }

    def test_requires_fresh_agreeing_signals_and_returns_manual_levels(self):
        report = build_manual_scalp_advisory(
            self.candle_report, self.tick_report, now=self.now,
        )
        self.assertEqual(report["action"], "BUY")
        self.assertEqual(report["bias"], "BUY")
        self.assertEqual(report["directional_evidence_score"], 71)
        self.assertEqual(report["scenario_levels"]["sl"], 2499.81)
        self.assertGreater(report["scenario_reward_to_risk"], 0.65)
        self.assertFalse(report["execution_enabled"])
        self.assertFalse(report["orders_sent"])
        self.assertIsNone(report.get("calibrated_probability"))

    def test_disagreeing_models_return_wait(self):
        self.tick_report["horizons"]["SCALP"]["action"] = "SELL"
        report = build_manual_scalp_advisory(self.candle_report, self.tick_report, now=self.now)
        self.assertEqual(report["action"], "WAIT")
        self.assertIn("Candle and tick-flow directions disagree.", report["blocks"])
        self.assertEqual(report["scenario_levels"], {})

    def test_stale_report_and_quote_return_wait(self):
        self.tick_report["latest_tick_age_seconds"] = 4.0
        report = build_manual_scalp_advisory(self.candle_report, self.tick_report, now=self.now)
        self.assertEqual(report["action"], "WAIT")
        self.assertTrue(any("stale" in reason.lower() for reason in report["blocks"]))

    def test_wide_spread_returns_wait(self):
        self.tick_report["ask"] = 2500.50
        report = build_manual_scalp_advisory(self.candle_report, self.tick_report, now=self.now)
        self.assertEqual(report["action"], "WAIT")
        self.assertTrue(any("spread" in reason.lower() for reason in report["blocks"]))

    def test_target_must_exceed_spread_and_reward_risk_floor(self):
        self.candle_report["horizons"]["SCALP"]["levels"]["tp1"] = 2500.02
        report = build_manual_scalp_advisory(self.candle_report, self.tick_report, now=self.now)
        self.assertEqual(report["action"], "WAIT")
        self.assertTrue(any("target distance" in reason.lower() for reason in report["blocks"]))

    def test_rejects_mismatched_symbols_and_naive_time(self):
        self.tick_report["symbol"] = "GOLD"
        with self.assertRaisesRegex(ValueError, "exact XAUUSD"):
            build_manual_scalp_advisory(self.candle_report, self.tick_report, now=self.now)
        self.tick_report["symbol"] = "XAUUSD"
        self.tick_report["generated_at"] = "2026-11-06T12:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            build_manual_scalp_advisory(self.candle_report, self.tick_report, now=self.now)


if __name__ == "__main__":
    unittest.main()
