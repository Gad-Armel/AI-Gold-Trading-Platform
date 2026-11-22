import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from services.dashboard.gold_manual_scalp_web import MAX_REPORT_BYTES, read_manual_scalp


class ManualScalpDashboardReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "report.json"
        self.now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
        self.report = {
            "symbol": "XAUUSD",
            "generated_at": (self.now - timedelta(seconds=1)).isoformat(),
            "valid_until": (self.now + timedelta(seconds=14)).isoformat(),
            "action": "BUY",
            "bias": "BUY",
            "directional_evidence_score": 71,
            "quote": {"bid": 2500.0, "ask": 2500.02, "spread": 0.02},
            "scenario_levels": {
                "entry_reference": 2500.01, "entry_zone": [2499.98, 2500.04],
                "sl": 2499.81, "tp1": 2500.20, "tp2": 2500.40, "tp3": 2500.60,
            },
            "scenario_reward_to_risk": 0.95,
            "reports": {"candle_action": "BUY", "candle_score": 76, "tick_action": "BUY", "tick_score": 71},
            "reasons": ["Candle and tick-flow agree."],
            "blocks": [],
            "execution_enabled": False,
            "orders_sent": False,
        }

    def publish(self, report=None):
        self.path.write_text(json.dumps(self.report if report is None else report), encoding="utf-8")

    def test_fresh_read_only_report_is_live(self):
        self.publish()
        result = read_manual_scalp(self.path, self.now.timestamp())
        self.assertEqual(result["state"], "live")
        self.assertEqual(result["report"]["action"], "BUY")
        self.assertEqual(result["age_seconds"], 1)

    def test_expired_and_old_report_cannot_be_live(self):
        self.publish()
        result = read_manual_scalp(self.path, (self.now + timedelta(seconds=15)).timestamp())
        self.assertEqual(result["state"], "stale")
        self.assertIn("expired", result["message"])

    def test_absent_report_waits(self):
        self.assertEqual(read_manual_scalp(self.path)["state"], "waiting")

    def test_invalid_or_execution_enabled_report_fails_closed(self):
        for field, value in (("execution_enabled", True), ("orders_sent", True),
                             ("symbol", "EURUSD"), ("directional_evidence_score", float("nan"))):
            report = dict(self.report); report[field] = value; self.publish(report)
            self.assertEqual(read_manual_scalp(self.path, self.now.timestamp())["state"], "error")

    def test_malformed_timestamps_and_missing_action_levels_fail_closed(self):
        report = dict(self.report); report["generated_at"] = "2026-11-06T12:00:00"
        self.publish(report)
        self.assertEqual(read_manual_scalp(self.path, self.now.timestamp())["state"], "error")
        report = dict(self.report); report["scenario_levels"] = {}
        self.publish(report)
        self.assertEqual(read_manual_scalp(self.path, self.now.timestamp())["state"], "error")

    def test_oversized_report_fails_closed(self):
        self.path.write_bytes(b" " * (MAX_REPORT_BYTES + 1))
        self.assertEqual(read_manual_scalp(self.path, self.now.timestamp())["state"], "error")


if __name__ == "__main__":
    unittest.main()
