import unittest
import json
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from services.research.gold_orbit_research import orbit_features, orbit_candidate, OrbitScalper, read_orbit_forward


class OrbitResearchTests(unittest.TestCase):
    def rates(self, period, count):
        stamps = np.arange(count)*period
        close = 4000+np.sin(stamps/3000)*2+stamps*.0001
        return pd.DataFrame(dict(time=stamps, open=close-.1, high=close+.5,
                                 low=close-.5, close=close, tick_volume=np.full(count, 100)))

    def row(self):
        return dict(feature_epoch=20000., direction='BUY', trend_sign=1,
                    setup='TREND_PULLBACK', close=4000., stop_buy=3997., stop_sell=4003., atr=2.)

    def test_missing_and_short_history_never_substitutes_ema200(self):
        self.assertTrue(orbit_features(None, None, offset=0).empty)
        self.assertTrue(orbit_features(self.rates(60, 250), self.rates(900, 140), offset=0).empty)
        result = OrbitScalper().assess([], {}, now=20000, bid=4000., ask=4000.3)
        self.assertFalse(result['source_usable'])

    def test_closed_context_cannot_leak_future_m15(self):
        one = self.rates(60, 1000).assign(time=lambda frame: frame.time+180000)
        slow = self.rates(900, 300)
        before = orbit_features(one, slow, offset=0)
        slow.loc[slow.time >= one.time.max(), ['open', 'high', 'low', 'close']] += 1000
        after = orbit_features(one, slow, offset=0)
        pd.testing.assert_frame_equal(before, after)

    def test_spread_uses_price_units_not_ambiguous_points(self):
        good = orbit_candidate(self.row(), now=20000.2, bid=4000., ask=4000.3)
        self.assertEqual(good['bias'], 'BUY')
        bad = orbit_candidate(dict(self.row(), stop_buy=3999.), now=20000.2, bid=4000., ask=4000.3)
        self.assertEqual(bad['bias'], 'WAIT')
        self.assertIn('15%', bad['blocks'][0])

    def test_expiry_and_late_entry_wait(self):
        for stamp, bid, ask in ((20060., 4000., 4000.3), (20000., 4001., 4001.3)):
            self.assertEqual(orbit_candidate(self.row(), now=stamp, bid=bid, ask=ask)['bias'], 'WAIT')

    def test_sell_is_mirrored_without_static_daily_bias(self):
        result = orbit_candidate(dict(self.row(), direction='SELL', trend_sign=-1),
                                 now=20000.2, bid=4000., ask=4000.3)
        self.assertEqual(result['bias'], 'SELL')
        self.assertEqual(result['levels']['sl'], 4003.)
        self.assertIsNone(result['calibrated_probability'])

    def test_old_forward_is_not_reported_as_live(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'latest.json'
            path.write_text(json.dumps(dict(observed_at='2026-10-21T10:00:00+00:00', read_only=True,
                execution_enabled=False, strategy='ORBIT_M1_M15_RESEARCH_V1')))
            result = read_orbit_forward(now=pd.Timestamp('2026-10-21T12:00:00Z').timestamp(), path=path)
            self.assertEqual(result['observer_state'], 'FINISHED_OR_STALE')
            self.assertFalse(result['execution_enabled'])


if __name__ == '__main__':
    unittest.main()
