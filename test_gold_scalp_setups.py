import unittest
import numpy as np
import pandas as pd
from services.research.gold_scalp_setups import setup_features, latest_observation


def bars(count, seconds):
    prices = 4000+np.arange(count)*.03+np.sin(np.arange(count)/5)*.5
    return pd.DataFrame(dict(time=np.arange(count)*seconds, open=prices-.02,
                             high=prices+.2, low=prices-.2, close=prices))


class SetupObservationTests(unittest.TestCase):
    def setUp(self):
        self.one, self.five = bars(700,60), bars(140,300)

    def test_future_changes_cannot_change_completed_features(self):
        before = setup_features(self.one,self.five,broker_offset_seconds=0,now=36000)
        self.one.loc[self.one.time >= 36000, 'close'] = -100
        self.five.loc[self.five.time >= 36000, 'close'] = -100
        after = setup_features(self.one,self.five,broker_offset_seconds=0,now=36000)
        pd.testing.assert_frame_equal(before,after)

    def test_latest_and_offline_use_identical_feature_function(self):
        table = setup_features(self.one,self.five,broker_offset_seconds=0,now=42000)
        result = latest_observation(self.one,self.five,broker_offset_seconds=0,now=42000)
        self.assertTrue(result['available'])
        self.assertEqual(result['rsi7'], float(table.rsi7.iloc[-1]))
        self.assertEqual(result['feature_epoch'], float(table.available.iloc[-1]))
        self.assertFalse(result['execution_enabled'])
        self.assertIsNone(result['calibrated_probability'])

    def test_stale_and_duplicate_candles_are_unusable(self):
        stale = latest_observation(self.one,self.five,broker_offset_seconds=0,now=42120)
        self.assertFalse(stale['available'])
        duplicates = pd.concat([self.one,self.one.iloc[[-1]]])
        self.assertFalse(latest_observation(duplicates,self.five,broker_offset_seconds=0,now=42000)['available'])

    def test_broker_offset_and_missing_m5_context(self):
        original = latest_observation(self.one,self.five,broker_offset_seconds=0,now=42000)
        self.one.time += 10800
        self.five.time += 10800
        shifted = latest_observation(self.one,self.five,broker_offset_seconds=10800,now=42000)
        self.assertEqual(original,shifted)
        self.assertFalse(latest_observation(self.one,self.five.iloc[:20],
                                           broker_offset_seconds=10800,now=42000)['available'])

    def test_datetime_seconds_microseconds_and_numeric_epochs_match(self):
        expected = latest_observation(self.one,self.five,broker_offset_seconds=0,now=42000)
        for unit in ('s','us','ns'):
            one, five = self.one.copy(), self.five.copy()
            one.time = pd.to_datetime(one.time,unit='s',utc=True).dt.as_unit(unit)
            five.time = pd.to_datetime(five.time,unit='s',utc=True).dt.as_unit(unit)
            self.assertEqual(latest_observation(one,five,broker_offset_seconds=0,now=42000),expected)


if __name__ == '__main__':
    unittest.main()
