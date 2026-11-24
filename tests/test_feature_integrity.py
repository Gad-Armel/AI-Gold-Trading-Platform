import unittest

import pandas as pd

from vfinal.data.quality import annotate_ticks
from vfinal.features.core import clean_candles, rsi, tick_features, time_features


class FeatureIntegrityTests(unittest.TestCase):
    def test_numeric_candle_clock_is_seconds_and_forming_bar_is_excluded(self):
        frame = pd.DataFrame(dict(time=[1767225600], open=[100], high=[101], low=[99], close=[100]))
        self.assertTrue(clean_candles(frame).empty)
        self.assertEqual(clean_candles(frame, closed_only=False).time.iloc[0], pd.Timestamp("2026-01-01T00:00:00Z"))

    def test_rsi_distinguishes_rising_falling_and_flat_prices(self):
        for values, expected in ((range(100, 140), 100), (range(140, 100, -1), 0), ([100] * 40, 50)):
            self.assertEqual(rsi(pd.DataFrame(dict(close=list(values)))), expected)

    def test_later_ticks_cannot_change_a_historical_feature_snapshot(self):
        history = pd.DataFrame(dict(time_msc=[1000000 + index * 200 for index in range(20)],
                                    bid=[100 + index * .01 for index in range(20)],
                                    ask=[100.2 + index * .01 for index in range(20)]))
        future = pd.DataFrame(dict(time_msc=[1020000 + index * 200 for index in range(50)],
                                   bid=[200] * 50, ask=[220] * 50))
        now = pd.Timestamp(1003800, unit="ms", tz="UTC")
        self.assertEqual(tick_features(history, now), tick_features(pd.concat([history, future]), now))

    def test_spread_baselines_do_not_depend_on_future_observations(self):
        history = pd.DataFrame(dict(time_msc=[1000000 + index * 200 for index in range(10)],
                                    bid=[100] * 10, ask=[100.2] * 10))
        future = pd.DataFrame(dict(time_msc=[1020000 + index * 200 for index in range(30)],
                                   bid=[100] * 30, ask=[120] * 30))
        before = annotate_ticks(history)
        after = annotate_ticks(pd.concat([history, future])).iloc[:len(history)]
        pd.testing.assert_series_equal(before.spread_baseline, after.spread_baseline)
        pd.testing.assert_series_equal(before.tick_quality_score, after.tick_quality_score)

    def test_time_features_accept_naive_and_aware_timestamps(self):
        expected = time_features("2026-01-01T12:00:00Z")
        self.assertEqual(time_features(pd.Timestamp("2026-01-01T12:00:00")), expected)
        self.assertEqual(time_features(pd.Timestamp("2026-01-01T13:00:00+01:00")), expected)
