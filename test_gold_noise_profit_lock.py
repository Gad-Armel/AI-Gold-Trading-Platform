import unittest
from copy import deepcopy

from services.research.gold_profit_lock import profit_lock_exit


class NoiseProfitLockTests(unittest.TestCase):
    def position(self, direction='BUY', ticket=1, volume=.01):
        return dict(ticket=ticket, direction=direction, entry_price=4000., volume=volume, sl=3998.)

    def run_lock(self, positions, state, bid, ask, *, noise=True, age=.1, **options):
        config = dict(profit_lock_arm_usd=1., profit_lock_retained_fraction=.8)
        if noise:
            config.update(profit_lock_noise_spreads=1., profit_lock_min_retained_usd=.3)
        config.update(options)
        return profit_lock_exit(positions, state, now=100., bid=bid, ask=ask,
            feed_age=age, config=config, contract_size=100.)

    def test_noise_pullback_survives_and_significant_giveback_closes(self):
        ps, state = [self.position()], {}
        self.run_lock(ps, state, 4001., 4001.5)
        small = self.run_lock(ps, state, 4000.7, 4001.2)
        self.assertFalse(small['close'])
        self.assertAlmostEqual(small['ticket_profit_thresholds']['1'], .5)
        self.assertTrue(self.run_lock(ps, state, 4000.49, 4000.99)['close'])

    def test_default_behavior_unchanged(self):
        ps, state = [self.position()], {}
        self.run_lock(ps, state, 4001., 4001.5, noise=False)
        result = self.run_lock(ps, state, 4000.7, 4001.2, noise=False)
        self.assertTrue(result['close'])
        self.assertFalse(result['noise_aware'])
        self.assertAlmostEqual(result['ticket_profit_thresholds']['1'], .8)
        self.assertIn('retained 80%', result['reason'])

    def test_large_spread_cannot_give_back_retained_floor(self):
        ps, state = [self.position()], {}
        self.run_lock(ps, state, 4001., 4003.)
        result = self.run_lock(ps, state, 4000.3, 4002.3)
        self.assertAlmostEqual(result['ticket_profit_thresholds']['1'], .3)
        self.assertTrue(result['close'])
        self.assertGreater(result['ticket_profit_thresholds']['1'], 0)

    def test_sell_uses_ask_and_preserves_position_and_stop(self):
        ps, state = [self.position('SELL')], {}
        before = deepcopy(ps)
        self.run_lock(ps, state, 3998.5, 3999.)
        small = self.run_lock(ps, state, 3998.8, 3999.3)
        self.assertFalse(small['close'])
        result = self.run_lock(ps, state, 3999.1, 3999.6)
        self.assertTrue(result['close'])
        self.assertEqual(ps, before)

    def test_stale_quote_cannot_close_or_update_peak(self):
        ps, state = [self.position()], {}
        self.run_lock(ps, state, 4001., 4001.5)
        before = deepcopy(state)
        result = self.run_lock(ps, state, 4000.1, 4000.6, age=100.)
        self.assertFalse(result['close'])
        self.assertEqual(state, before)

    def test_invalid_noise_configuration_fails_closed(self):
        for invalid in (-1., float('nan'), 'bad'):
            result = self.run_lock([self.position()], {}, 4001., 4001.5,
                                   profit_lock_noise_spreads=invalid)
            self.assertFalse(result['close'])
            self.assertIn('invalid noise configuration', result['reason'])
        result = self.run_lock([self.position()], {}, 4001., 4001.5,
                               profit_lock_min_retained_usd=0.)
        self.assertFalse(result['close'])
        self.assertIn('positive retained floor required', result['reason'])


if __name__ == '__main__':
    unittest.main()
