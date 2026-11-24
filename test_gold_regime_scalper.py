import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from services.research.gold_regime_scalper import (
    RegimeScalper, candidate_from_row, feature_table, quote_bars, rate_features,
)


class RegimeScalperTests(unittest.TestCase):
    def rates(self, period):
        stamps = np.arange(0, 7200, period)
        close = 4000+stamps*.001
        return pd.DataFrame(dict(time=stamps, open=close-.1, high=close+.3, low=close-.3, close=close))

    def ticks(self):
        stamps = np.arange(6000, 6600, .25)
        mid = 4006+np.sin(stamps/7)*.3+(stamps-6000)*.001
        return pd.DataFrame(dict(timestamp=stamps, bid=mid-.05, ask=mid+.05))

    def row(self):
        return dict(feature_epoch=6600, evidence=80., trend_sign=1, setup='TREND_PULLBACK',
                    direction='BUY', stop=4000., reference=4001., m1_atr=2.)

    def test_rate_available_only_at_close(self):
        output = rate_features(self.rates(60), 60, 0, 'm1')
        self.assertEqual(output.feature_epoch.iloc[-1], 7200)
        self.assertTrue(output.m1_atr.iloc[:29].isna().all())

    def test_numeric_and_datetime_candles_have_identical_features(self):
        numeric = self.rates(60)
        dated = numeric.assign(time=pd.to_datetime(numeric.time, unit='s'))
        pd.testing.assert_frame_equal(rate_features(numeric, 60, 0, 'm1'),
                                      rate_features(dated, 60, 0, 'm1'))

    def test_invalid_ohlc_is_rejected(self):
        frame = self.rates(60)
        frame.loc[10, 'high'] = frame.close.iloc[10]-1
        with self.assertRaises(ValueError):
            rate_features(frame, 60, 0, 'm1')

    def test_future_candles_do_not_change_past_features(self):
        m1, m5 = self.rates(60), self.rates(300)
        m5 = pd.concat([m5, self.rates(300).assign(time=lambda frame: frame.time-7200)])
        before = feature_table(self.ticks(), m1, m5, offset=0)
        m1.loc[m1.time >= 6600, ['open', 'high', 'low', 'close']] += 1000
        m5.loc[m5.time >= 6600, ['open', 'high', 'low', 'close']] += 1000
        after = feature_table(self.ticks(), m1, m5, offset=0)
        pd.testing.assert_frame_equal(before, after)

    def test_missing_quotes_not_forward_filled(self):
        ticks = self.ticks()
        ticks = ticks[(ticks.timestamp < 6500) | (ticks.timestamp >= 6520)]
        bars = quote_bars(ticks)
        self.assertFalse(bars[bars.bucket == 6520].covered.iloc[0])
        self.assertFalse(bars.bucket.eq(6510).any())

    def test_expired_or_future_setup_cannot_enter(self):
        for stamp in (6599, 6605, 6700):
            result = candidate_from_row(self.row(), now=stamp, bid=4000.9, ask=4001.)
            self.assertEqual(result['bias'], 'WAIT')
            self.assertFalse(result['source_usable'])

    def test_valid_setup_is_not_calibrated_probability(self):
        result = candidate_from_row(self.row(), now=6600.2, bid=4000.9, ask=4001.)
        self.assertEqual(result['bias'], 'BUY')
        self.assertEqual(result['levels']['sl'], 4000.)
        self.assertNotIn('probability', result)

    def test_no_setup_keeps_independent_trend_thesis(self):
        row = dict(self.row(), direction='WAIT')
        result = candidate_from_row(row, now=6600.2, bid=4000.9, ask=4001.)
        self.assertEqual(result['bias'], 'WAIT')
        self.assertEqual(result['thesis_bias'], 'BUY')

    def test_invalid_quote_is_unusable_even_without_setup(self):
        result = candidate_from_row(dict(self.row(), direction='WAIT'), now=6600.2,
                                    bid=float('nan'), ask=4001.)
        self.assertFalse(result['source_usable'])

    def test_widening_or_late_entry_cannot_enter(self):
        for bid, ask in ((4000., 4001.), (4001.9, 4002.)):
            result = candidate_from_row(self.row(), now=6600.2, bid=bid, ask=ask)
            self.assertEqual(result['bias'], 'WAIT')

    @patch('services.research.gold_regime_scalper.feature_table')
    def test_cache_does_not_rebuild_each_tick(self, mocked):
        mocked.return_value = pd.DataFrame([self.row()])
        model = RegimeScalper()
        for stamp in (6600.1, 6600.3, 6601.):
            model.assess(self.ticks(), {}, now=stamp, bid=4000.9, ask=4001.)
        self.assertEqual(mocked.call_count, 1)


if __name__ == '__main__':
    unittest.main()
