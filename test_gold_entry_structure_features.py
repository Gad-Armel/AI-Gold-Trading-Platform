import unittest
import numpy as np
import pandas as pd
from services.research.gold_entry_structure_features import candle_structure


class EntryStructureFeatureTests(unittest.TestCase):
    def frame(self,seconds=60):
        n=60
        return pd.DataFrame(dict(time=10800+np.arange(n)*seconds,open=np.full(n,8.),
            high=np.full(n,10.),low=np.full(n,7.),close=np.full(n,9.),tick_volume=np.ones(n)))

    def features(self,frame,seconds=60):
        return candle_structure(frame,seconds=seconds,broker_offset_seconds=10800)

    def test_future_price_and_volume_changes_cannot_revise_past_features(self):
        frame=self.frame()
        first=self.features(frame)
        frame.loc[55:,'high']+=100
        frame.loc[55:,'close']+=50
        frame.loc[55:,'tick_volume']*=1000
        pd.testing.assert_frame_equal(first.iloc[:55],self.features(frame).iloc[:55])

    def test_m5_features_become_available_only_after_bar_completion(self):
        result=self.features(self.frame(300),300)
        self.assertEqual(result.feature_epoch.iloc[0],300)
        self.assertEqual(result.feature_epoch.iloc[25],26*300)

    def test_sweep_compares_against_prior_extrema_not_current_bar(self):
        frame=self.frame()
        frame.loc[25,'high']=13
        result=self.features(frame)
        self.assertEqual(result.upside_sweep.iloc[25],1.)
        self.assertAlmostEqual(result.resistance_distance_stop_budget.iloc[25],.2)
        self.assertAlmostEqual(result.upper_wick_fraction.iloc[25],4/6)

    def test_two_body_confirmation_uses_two_distinct_completed_candles(self):
        frame=self.frame(300)
        frame.loc[25,'close']=7.5
        result=self.features(frame,300)
        self.assertEqual(result.two_candle_direction.iloc[25],0.)
        self.assertEqual(result.two_candle_direction.iloc[26],0.)
        self.assertEqual(result.two_candle_direction.iloc[27],1.)


if __name__=='__main__':
    unittest.main()
