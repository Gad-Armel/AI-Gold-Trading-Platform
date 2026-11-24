from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.research.gold_s30_execution import load_costs


class S30CostCalibrationTests(unittest.TestCase):
    def write_profile(self, path, now, age_seconds):
        profile = {
            'as_of': datetime.fromtimestamp(now-age_seconds, timezone.utc).isoformat(),
            'symbol': 'XAUUSD',
            'currency': 'USD',
            'volume': .01,
            'read_only': True,
            'costs': {
                'available': True,
                'reconciled_pairs': 30,
                'commission_price': .1,
                'slippage_price': .2,
            },
        }
        path.write_text(json.dumps(profile), encoding='utf-8')

    def test_fresh_measured_profile_is_accepted_with_expiry_enforced(self):
        now = datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'costs.json'
            self.write_profile(path, now, 3600)
            costs = load_costs(path, now=now)
        self.assertEqual(costs['profile_type'], 'MEASURED')
        self.assertFalse(costs['calibration_stale'])
        self.assertTrue(costs['calibration_expiry_enforced'])

    def test_stale_measured_profile_fails_closed(self):
        now = datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'costs.json'
            self.write_profile(path, now, 86401)
            with self.assertRaisesRegex(ValueError, 'older than 24 hours'):
                load_costs(path, now=now)

    def test_profile_at_24_hour_boundary_is_accepted(self):
        now = datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'costs.json'
            self.write_profile(path, now, 86400)
            costs = load_costs(path, now=now)
        self.assertEqual(costs['calibration_age_seconds'], 86400)
        self.assertTrue(costs['calibration_expiry_enforced'])

    def test_future_dated_profile_fails_closed(self):
        now = datetime(2026, 10, 26, tzinfo=timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'costs.json'
            self.write_profile(path, now, -1)
            with self.assertRaisesRegex(ValueError, 'not future-dated'):
                load_costs(path, now=now)


if __name__ == '__main__':
    unittest.main()
