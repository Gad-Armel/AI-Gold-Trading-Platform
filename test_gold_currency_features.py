import unittest
import numpy as np
import pandas as pd
from tools.research_gold_currency_entries import currency_features


class CurrencyFeatureTests(unittest.TestCase):
    def bars(self):
        return pd.DataFrame(dict(time=10800 + np.arange(90) * 60,
                                 close=1.1 + np.sin(np.arange(90) / 5) * .001))

    def test_completed_feature_is_unavailable_before_bar_close(self):
        bars = self.bars()
        features = currency_features(bars)
        epoch = int(bars.time.iloc[60] - 10800)
        query = pd.DataFrame(dict(feature_epoch=[epoch + 59, epoch + 60]))
        merged = pd.merge_asof(query, features, on='feature_epoch', direction='backward')
        expected = np.log(bars.close.iloc[60] / bars.close.iloc[59]) * 10000
        self.assertAlmostEqual(merged.return_1.iloc[1], expected)
        self.assertNotAlmostEqual(merged.return_1.iloc[0], expected)

    def test_future_changes_cannot_change_past_features(self):
        bars = self.bars()
        original = currency_features(bars)
        bars.loc[70:, 'close'] *= 2
        changed = currency_features(bars)
        cutoff = int(bars.time.iloc[69] + 60 - 10800)
        pd.testing.assert_frame_equal(original[original.feature_epoch <= cutoff],
                                      changed[changed.feature_epoch <= cutoff])

    def test_gap_is_not_treated_as_minute_return(self):
        bars = self.bars().drop(index=50)
        features = currency_features(bars)
        next_close = 51 * 60 + 60
        self.assertFalse((features.feature_epoch == next_close).any())
        self.assertTrue((features.feature_epoch > 82 * 60).any())


if __name__ == '__main__':
    unittest.main()
