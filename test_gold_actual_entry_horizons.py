import unittest
import numpy as np
from tools.audit_gold_actual_entry_horizons import outcome


class ActualEntryHorizonTests(unittest.TestCase):
    def test_stop_gap_charges_first_executable_bid_without_clipping(self):
        times=np.arange(6,dtype=float)
        bids=np.array([100.,100.,99.,90.,101.,102.])
        result=outcome(times,bids,bids+.4,1.,100.4,'BUY',4.)
        self.assertTrue(result['stop_hit'])
        self.assertAlmostEqual(result['profit'],-10.45)
        self.assertEqual(result['stop_time'],3.)

    def test_sell_stop_uses_ask_and_not_bid(self):
        times=np.arange(6,dtype=float)
        bids=np.array([100.,100.,101.,104.9,100.,99.])
        result=outcome(times,bids,bids+.4,1.,100.,'SELL',4.)
        self.assertTrue(result['stop_hit'])
        self.assertAlmostEqual(result['profit'],-5.35)

    def test_pre_entry_adverse_price_cannot_stop_later_position(self):
        times=np.arange(6,dtype=float)
        bids=np.array([80.,100.,101.,102.,103.,104.])
        result=outcome(times,bids,bids+.4,1.,100.,'BUY',3.)
        self.assertFalse(result['stop_hit'])
        self.assertAlmostEqual(result['profit'],2.95)

    def test_incomplete_horizon_has_no_fabricated_return(self):
        times=np.arange(6,dtype=float)
        bids=np.full(6,100.)
        result=outcome(times,bids,bids+.4,1.,100.,'BUY',10.)
        self.assertFalse(result['available'])
        self.assertNotIn('profit',result)


if __name__=='__main__':
    unittest.main()
