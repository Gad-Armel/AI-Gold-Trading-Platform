import unittest
import numpy as np
import pandas as pd
from services.research.gold_tick_entry_research import tick_features,tick_path_labels


class TickEntryResearchTests(unittest.TestCase):
    def data(self):
        times = np.arange(0,400001,100,dtype=np.int64)
        bids = np.full(len(times),4000.)
        return times,bids,bids+.3

    def test_flat_quotes_pay_spread_and_slippage_for_both_directions(self):
        times,bid,ask = self.data()
        for stress,loss in ((1.,-.4),(1.5,-.6)):
            result=tick_path_labels(times,bid,ask,[60],stress=stress).iloc[0]
            self.assertTrue(result.valid)
            self.assertAlmostEqual(result.buy_profit,loss)
            self.assertAlmostEqual(result.sell_profit,loss)

    def test_gap_stop_is_not_clipped_to_five_dollars(self):
        times,bid,ask=self.data()
        bid[times>=100000]-=10;ask[times>=100000]-=10
        result=tick_path_labels(times,bid,ask,[60]).iloc[0]
        self.assertLess(result.buy_profit,-10)
        self.assertEqual(result.buy_exit_epoch,100.)

    def test_pre_execution_excursion_cannot_trigger_post_entry_stop(self):
        times,bid,ask=self.data()
        times=np.r_[times,60050,60090];bid=np.r_[bid,3990,4000];ask=np.r_[ask,3990.3,4000.3]
        order=np.argsort(times,kind='stable')
        result=tick_path_labels(times[order],bid[order],ask[order],[60]).iloc[0]
        self.assertAlmostEqual(result.buy_profit,-.4)

    def test_missing_future_executable_quote_does_not_become_a_label(self):
        times=np.r_[np.arange(0,70000,100),500000].astype(np.int64)
        bids=np.full(len(times),4000.)
        self.assertFalse(tick_path_labels(times,bids,bids+.3,[60]).iloc[0].valid)

    def test_future_quote_shock_does_not_change_prior_features(self):
        times,bid,ask=self.data()
        bid+=times/100000;ask+=times/100000
        original=tick_features(times,bid,ask)
        bid[times>=250000]+=100;ask[times>=250000]+=100
        altered=tick_features(times,bid,ask)
        pd.testing.assert_frame_equal(original[original.feature_epoch<=250],
                                      altered[altered.feature_epoch<=250])


if __name__=='__main__':
    unittest.main()
