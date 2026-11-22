import unittest

from services.research.gold_s30_shadow import s30_observation, fast_candidate


class TwoBarScalpTests(unittest.TestCase):
    def test_activity_accepts_small_confirmed_move_but_not_flat_quotes(self):
        bars = [dict(time=-5, close=4000., high=4002., low=3999.)]
        ticks = [(i*.5, 4000+i*.02, 4000.5+i*.02) for i in range(7)]
        args = dict(now=3., direction='BUY', commission_price=.1, slippage_price=.2,
                    micro_window_seconds=3, range_cost_multiple=1.)
        self.assertFalse(fast_candidate(ticks, bars, **args)['research_candidate'])
        self.assertTrue(fast_candidate(ticks, bars, activity_mode=True, **args)['research_candidate'])
        flat = [(i*.5, 4000., 4000.5) for i in range(7)]
        self.assertFalse(fast_candidate(flat, bars, activity_mode=True, **args)['research_candidate'])

    def test_single_closed_bar_is_available_without_future_candle(self):
        result = s30_observation(self.ticks(), now=230., period_seconds=5, bar_count=1,
            commission_price=.1, slippage_price=.2, range_cost_multiple=1., micro_window_seconds=3)
        self.assertTrue(result['available'])
        self.assertEqual(len(result['bars']), 1)
        self.assertEqual(result['direction'], 'BUY')
        self.assertLessEqual(result['bars'][0]['time']+5, 230.)

    def ticks(self):
        return [dict(timestamp=index*.25, bid=4000+index*.025, ask=4000.1+index*.025)
                for index in range(800, 921)]

    def test_two_closed_bars_are_supported_without_synthetic_quotes(self):
        result = s30_observation(self.ticks(), now=230., period_seconds=5, bar_count=2,
            commission_price=0., slippage_price=0., range_cost_multiple=1.5)
        self.assertTrue(result['available'])
        self.assertEqual(len(result['bars']), 2)
        self.assertEqual(result['direction'], 'BUY')
        self.assertTrue(all(bar['time']+5 <= 230 for bar in result['bars']))

    def test_sparse_data_still_fails_coverage(self):
        result = s30_observation(self.ticks()[::12], now=230., period_seconds=5,
            bar_count=2, commission_price=0., slippage_price=0., range_cost_multiple=1.5)
        self.assertFalse(result['available'])

    def test_cost_margin_still_rejects_unaffordable_range(self):
        bars = [dict(time=0, close=4000., high=4000.8, low=4000.),
                dict(time=5, close=4000., high=4001.2, low=4000.)]
        ticks = [(index, 4000+index*.1, 4000.2+index*.1) for index in range(7)]
        result = fast_candidate(ticks, bars, now=6., direction='BUY', commission_price=.3,
                                slippage_price=.2, range_cost_multiple=1.5)
        self.assertAlmostEqual(result['recent_range_proxy_price'], 1.)
        self.assertFalse(result['cost_screen_passed'])
        self.assertEqual(result['range_cost_multiple'], 1.5)

    def test_invalid_margin_cannot_disable_cost_protection(self):
        for margin in (0., .5, True, float('nan')):
            with self.assertRaises(ValueError):
                s30_observation(self.ticks(), now=230., bar_count=2, period_seconds=5,
                    range_cost_multiple=margin)

    def test_short_window_recognizes_recent_bid_ask_recovery(self):
        mids = [4002., 4001.8, 4001.6, 4001., 4001.2, 4001.4, 4001.6]
        ticks = [(i, price-.05, price+.05) for i, price in enumerate(mids)]
        bars = [dict(time=-10, close=4001.5, high=4003., low=4000.),
                dict(time=-5, close=4001.5, high=4003., low=4000.)]
        args = dict(now=6, direction='BUY', commission_price=.1, slippage_price=.2)
        short = fast_candidate(ticks, bars, micro_window_seconds=3, **args)
        control = fast_candidate(ticks, bars, micro_window_seconds=6, **args)
        self.assertTrue(short['research_candidate'])
        self.assertFalse(control['research_candidate'])
        self.assertEqual(short['micro_window_seconds'], 3)
        self.assertGreater(short['signed_bid_move_price'], 0)
        self.assertGreater(short['signed_ask_move_price'], 0)

    def test_short_window_still_rejects_missing_updates(self):
        bars = [dict(time=-10, close=4001., high=4003., low=4000.)]*2
        result = fast_candidate([(0, 4000., 4000.1), (6, 4001., 4001.1)], bars,
            now=6, direction='BUY', commission_price=.1, slippage_price=.2, micro_window_seconds=3)
        self.assertIn('Insufficient continuous three-second quote coverage', result['blocks'])


if __name__ == '__main__':
    unittest.main()
