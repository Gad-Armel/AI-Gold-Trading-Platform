from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from config import scalping_settings
from services.research.v6_approval import load_v6_approval, write_v6_approval
from services.research.v6_walk_forward import build_v6_walk_forward_report


class V6ApprovalWalkForwardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.history = root / "history.jsonl"
        self.approval = root / "approval.json"
        self.patchers = [
            patch.object(scalping_settings, "SCALPING_V6_SHADOW_HISTORY_PATH", str(self.history)),
            patch.object(scalping_settings, "SCALPING_V6_DEMO_APPROVAL_PATH", str(self.approval)),
            patch.object(scalping_settings, "SCALPING_V6_PROMOTION_BOOTSTRAP_SAMPLES", 500),
            patch.object(scalping_settings, "SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL", False),
        ]
        for item in self.patchers: item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patchers): item.stop()
        self.temp.cleanup()

    def _write_history(self, profits: list[float]) -> None:
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        with self.history.open("w", encoding="utf-8") as handle:
            for i, pnl in enumerate(profits):
                closed = start + timedelta(minutes=30*i)
                row = {"status": "CLOSED", "opened_at": (closed-timedelta(seconds=30)).isoformat(),
                       "closed_at": closed.isoformat(), "final_profit_usd": pnl, "close_reason": "TEST"}
                handle.write(json.dumps(row)+"\n")

    def test_small_sample_remains_shadow_only(self) -> None:
        self._write_history([.5, -.2] * 10)
        report = build_v6_walk_forward_report(write_approval=True)
        self.assertFalse(report["approved"])
        self.assertFalse(load_v6_approval()["approved"])

    def test_positive_walk_forward_history_creates_valid_approval(self) -> None:
        # Chronologically distributed positive edge: 2 wins for each loss.
        profits = []
        for i in range(240):
            profits.append(-.20 if i % 3 == 0 else .50)
        self._write_history(profits)
        report = build_v6_walk_forward_report(write_approval=True)
        self.assertTrue(report["approved"], report)
        loaded = load_v6_approval()
        self.assertTrue(loaded["approved"], loaded)
        self.assertEqual(loaded["settings_hash"], loaded["expected_settings_hash"])

    def test_expired_or_wrong_settings_approval_is_rejected(self) -> None:
        write_v6_approval({"test": True}, approved=True)
        data = json.loads(self.approval.read_text())
        data["expires_at"] = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        self.approval.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(load_v6_approval()["approved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
