import json
from pathlib import Path
import tempfile
import unittest

from tools.summarize_demo_monitoring import summarize, fresh_status


class MonitoringFreshnessTests(unittest.TestCase):
    def test_stale_previous_run_cannot_manufacture_session_profit(self):
        def sample(observed, updated, profit):
            return dict(observed_at=observed,
                        account=dict(equity=100, balance=100), positions=[],
                        status=dict(updated_at=updated, pnl=dict(realized=profit, total=profit), lanes={}))

        rows = [sample('2026-10-18T20:00:00+00:00', '2026-10-15T20:00:00+00:00', -100),
                sample('2026-10-18T20:00:10+00:00', '2026-10-18T20:00:09+00:00', 0),
                sample('2026-10-18T20:00:20+00:00', '2026-10-18T20:00:19+00:00', -1)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'observations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf-8')
            result = summarize(root)
        self.assertEqual(result['main_total_change'], -1)
        self.assertEqual(result['observations'], 2)
        self.assertEqual(result['excluded_stale_or_incomplete_observations'], 1)

    def test_missing_and_future_status_are_not_live_observations(self):
        self.assertFalse(fresh_status(dict(observed_at='2026-10-18T20:00:00Z', status={})))
        self.assertFalse(fresh_status(dict(observed_at='2026-10-18T20:00:00Z',
                                          status=dict(updated_at='2026-10-18T21:00:00Z'))))
