import unittest
from datetime import datetime, timezone

import pandas as pd

from tools.audit_gold_live_observation import summarize_samples


class LiveObservationTests(unittest.TestCase):
    def test_directional_observation_is_not_an_authorized_trade(self):
        epoch = 1792993000.
        stamp = datetime.fromtimestamp(epoch, timezone.utc).isoformat()
        samples = [dict(status='RUNNING', observed_at=stamp, updated_at=stamp,
                        direction='BUY', allowed=False, entry_ready=False)]
        ticks = pd.DataFrame([dict(timestamp=epoch+index*.25, bid=4000., ask=4000.4)
                              for index in range(160)])
        results = summarize_samples(samples, ticks)
        raw = next(row for row in results if row['horizon_seconds'] == 15 and row['cohort'] == 'directional')
        self.assertEqual(raw['observations'], 1)
        self.assertAlmostEqual(raw['mean_net_price'], -.7)
        self.assertEqual(raw['net_positive_fraction'], 0.)
        self.assertTrue(all(row['observations'] == 0 for row in results
                            if row['cohort'] == 'all_entry_checks_ready'))

    def test_cached_stale_signal_is_not_labelled_as_fresh(self):
        samples = [dict(status='RUNNING', observed_at='2026-10-26T10:00:10+00:00',
                        updated_at='2026-10-26T10:00:00+00:00', direction='BUY')]
        results = summarize_samples(samples, pd.DataFrame(columns=['timestamp', 'bid', 'ask']))
        self.assertTrue(all(row['observations'] == 0 for row in results))


if __name__ == '__main__':
    unittest.main()
