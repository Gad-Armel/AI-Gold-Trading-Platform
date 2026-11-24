import unittest

from services.research.gold_s30_shadow import s30_observation


class FastShadowTests(unittest.TestCase):
    def ticks(self):
        return [dict(timestamp=stamp, bid=4000+stamp*.1, ask=4000+stamp*.1+.02)
                for stamp in range(120, 216)]

    def test_missing_costs_never_promotes_pattern(self):
        result = s30_observation(self.ticks(), now=215)
        self.assertTrue(result['available'])
        fast = result['fast_candidate']
        self.assertTrue(fast['pattern_ready'])
        self.assertFalse(fast['research_candidate'])
        self.assertIsNone(fast['cost_screen_passed'])
        self.assertFalse(fast['execution_enabled'])

    def test_explicit_costs_and_chronological_closed_bars(self):
        result = s30_observation(self.ticks(), now=215, commission_price=.01, slippage_price=.02)
        self.assertEqual(result['direction'], 'BUY')
        self.assertTrue(result['fast_candidate']['research_candidate'])
        self.assertEqual(result['bars'][-1]['time'], 180)
        self.assertIsNone(result['fast_candidate']['expected_value'])

    def test_large_cost_blocks(self):
        result = s30_observation(self.ticks(), now=215, commission_price=1., slippage_price=1.)
        self.assertFalse(result['fast_candidate']['research_candidate'])

    def test_current_reversal_blocks(self):
        ticks = self.ticks()
        for tick in ticks[-5:]:
            tick.update(bid=4010., ask=4010.02)
        result = s30_observation(ticks, now=215, commission_price=0., slippage_price=0.)
        self.assertFalse(result['fast_candidate']['pattern_ready'])

    def test_gap_and_stale_data_rejected(self):
        self.assertFalse(s30_observation(self.ticks()[:-10], now=215)['available'])
        ticks = [tick for tick in self.ticks() if not 140 <= tick['timestamp'] <= 150]
        self.assertFalse(s30_observation(ticks, now=215)['available'])

    def test_invalid_costs_rejected(self):
        for cost in (True, -1, float('nan'), '0'):
            result = s30_observation(self.ticks(), now=215, commission_price=cost, slippage_price=0.)
            self.assertFalse(result['fast_candidate']['research_candidate'])

    def test_same_timestamp_quote_order_is_preserved(self):
        ticks = self.ticks()
        ticks.extend([dict(timestamp=215, bid=4021.6, ask=4021.62),
                      dict(timestamp=215, bid=4021.55, ask=4021.57)])
        result = s30_observation(ticks, now=215, commission_price=0., slippage_price=0.)
        self.assertAlmostEqual(result['fast_candidate']['signed_move_price'], .65)

    def test_intra_second_noise_does_not_change_second_close_efficiency(self):
        sparse = self.ticks()
        dense = []
        for tick in sparse:
            for fraction, offset in ((-.8, .04), (-.6, -.04), (-.4, .04), (-.2, -.04), (0., 0.)):
                dense.append(dict(timestamp=tick['timestamp']+fraction, bid=tick['bid']+offset,
                                  ask=tick['ask']+offset))
        sparse_fast = s30_observation(sparse, now=215, commission_price=0., slippage_price=0.)['fast_candidate']
        dense_fast = s30_observation(dense, now=215, commission_price=0., slippage_price=0.)['fast_candidate']
        self.assertEqual(sparse_fast['quote_efficiency'], dense_fast['quote_efficiency'])
        self.assertLess(dense_fast['raw_tick_efficiency'], dense_fast['quote_efficiency'])


if __name__ == '__main__':
    unittest.main()
