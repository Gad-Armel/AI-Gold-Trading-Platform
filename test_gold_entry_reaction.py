import unittest
import numpy as np
from tools.audit_gold_entry_reaction import reaction


class EntryReactionTests(unittest.TestCase):
    def test_short_uses_ask_and_mid_direction_is_separate_from_spread(self):
        times = np.array([100., 101., 102.])
        bids = np.array([10., 9.95, 9.9])
        asks = bids + .4
        result = reaction(times, bids, asks, 100., 10., 'SELL', 2.)
        self.assertEqual(result['signed_mid_move'], .1)
        self.assertEqual(result['executable_move'], -.3)

    def test_future_quotes_do_not_change_endpoint_mark(self):
        times = np.array([100., 101., 102., 103.])
        bids = np.array([10., 10.1, 10.2, 100.])
        asks = bids + .2
        result = reaction(times, bids, asks, 100., 10.2, 'BUY', 2.)
        bids[-1] = -100.
        self.assertEqual(result, reaction(times, bids, asks, 100., 10.2, 'BUY', 2.))
        self.assertEqual(result['executable_move'], 0.)

    def test_missing_endpoint_and_internal_gap_are_excluded(self):
        times = np.array([100., 101., 120.])
        bids = np.ones(3) * 10
        asks = bids + .2
        self.assertIsNone(reaction(times, bids, asks, 100., 10.2, 'BUY', 30.))
        self.assertIsNone(reaction(times, bids, asks, 100., 10.2, 'BUY', 20.))


if __name__ == '__main__':
    unittest.main()
