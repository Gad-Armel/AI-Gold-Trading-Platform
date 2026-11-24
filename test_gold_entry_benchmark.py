import unittest
import pandas as pd
from tools.benchmark_gold_entry_patterns import evaluate, view


class EntryBenchmarkTests(unittest.TestCase):
    def frame(self, direction=1):
        n = 35
        return pd.DataFrame(dict(time=[60*i for i in range(n)], open=[4000.]*n,
            high=[4000.1]*n, low=[3999.9]*n, close=[4000.]*n, spread=[30]*n,
            direction=[direction]*n, body=[direction*.1]*n, prior_body=[-direction*.1]*n,
            gap_next=[60]*n, M1_direction=[direction]*n, M5_direction=[direction]*n,
            M1_extension=[.1]*n, prior_high=[3999.]*n, prior_low=[4001.]*n))

    def test_flat_prices_lose_spread_and_round_trip_slippage_both_sides(self):
        for direction in (1, -1):
            result = evaluate(self.frame(direction), 0, 35, 'DIRECTIONAL_BODY', 5, 1)
            self.assertGreater(result['trades'], 0)
            self.assertAlmostEqual(result['mean'], -.4)

    def test_stop_gap_fills_at_worse_open_without_clipping_loss(self):
        frame = self.frame()
        frame.loc[2, ['open', 'high', 'low', 'close']] = [3990, 3991, 3989, 3990]
        result = evaluate(frame, 0, 9, 'DIRECTIONAL_BODY', 5, 1)
        self.assertEqual(result['trades'], 1)
        self.assertLess(result['net'], -10)

    def test_nonoverlapping_trade_events_match_reported_returns(self):
        frame = self.frame()
        metrics = evaluate(frame, 0, 35, 'DIRECTIONAL_BODY', 5, 1)
        trades = evaluate(frame, 0, 35, 'DIRECTIONAL_BODY', 5, 1, return_trades=True)
        self.assertEqual(metrics['trades'], len(trades))
        self.assertAlmostEqual(metrics['net'], sum(t['profit'] for t in trades))
        self.assertTrue(all(b['entry_epoch']>a['exit_epoch'] for a,b in zip(trades,trades[1:])))

    def test_closed_bar_view_availability_is_at_close(self):
        frame = pd.concat([self.frame()]*3, ignore_index=True)
        frame['time'] = [60*i for i in range(len(frame))]
        result = view(frame, 60)
        self.assertEqual(result.available.iloc[0], frame.time.iloc[55]+60)

    def test_future_price_shock_does_not_change_prior_features(self):
        frame = pd.concat([self.frame()]*3, ignore_index=True)
        frame['time'] = [60*i for i in range(len(frame))]
        original = view(frame, 60)
        frame.loc[80:, ['open', 'high', 'low', 'close']] = [9000, 9001, 8999, 9000]
        shocked = view(frame, 60)
        pd.testing.assert_frame_equal(original.loc[:79], shocked.loc[:79])


if __name__ == '__main__':
    unittest.main()
