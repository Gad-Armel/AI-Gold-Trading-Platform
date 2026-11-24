import tempfile
import unittest
from types import SimpleNamespace
import numpy as np
import pandas as pd
from services.execution.gold_paper_portfolio import GoldPaperPortfolio
from services.research.gold_learned_policy import feature_frame, GoldLearnedPolicy, apply_entry_filter, learned_exit


class ConstantForecast:
    def predict(self, x):
        return np.full(len(x), 2.)


class LearnedPolicyTests(unittest.TestCase):
    def frame(self):
        c = 100+np.arange(150)*.1+np.sin(np.arange(150))
        return pd.DataFrame(dict(time=1800000000+np.arange(150)*300, open=c-.1, high=c+1, low=c-1, close=c))

    def test_features_are_causal_and_match_bounded_live_window(self):
        frame = self.frame()
        full = feature_frame(frame)
        pd.testing.assert_series_equal(full.iloc[100], feature_frame(frame.iloc[21:101]).iloc[-1])
        changed = frame.copy()
        changed.loc[101:, ['open','high','low','close']] += 9000
        pd.testing.assert_frame_equal(full.iloc[:101], feature_frame(changed).iloc[:101])

    def test_inference_excludes_forming_bar_and_reanchors_quote(self):
        frame = self.frame()
        policy = GoldLearnedPolicy.__new__(GoldLearnedPolicy)
        policy.cache = {}
        policy.models = {'SCALP': dict(model=ConstantForecast(), training_last_bar=0,
            round_trip_slippage_usd=.1, model_id='test', forecast_bars=3,
            minimum_edge_usd=.25, validation={})}
        snapshot = SimpleNamespace(candles={'M5': frame}, timestamp=pd.to_datetime(frame.time.iloc[-1]+100, unit='s', utc=True),
                                   bid=float(frame.close.iloc[-2]), ask=float(frame.close.iloc[-2])+.2)
        context = dict(available=True, bar_id='last-completed')
        first = policy.assess(snapshot, 'SCALP', context)
        self.assertAlmostEqual(first['edge_usd']['BUY'], 1.7)
        frame.loc[149, ['open','high','low','close']] += 5000
        self.assertEqual(first, policy.assess(snapshot, 'SCALP', context))
        snapshot.bid += 3; snapshot.ask += 3
        self.assertAlmostEqual(policy.assess(snapshot, 'SCALP', context)['edge_usd']['BUY'], -1.3)

    def test_entry_filter_cannot_restore_news_permission(self):
        d = dict(allowed=False, direction='BUY', blocks=['News'])
        apply_entry_filter(d, dict(available=True, edge_usd={'BUY': 100}, minimum_edge_usd=.25))
        self.assertFalse(d['allowed'])
        self.assertEqual(d['blocks'], ['News'])
        d['allowed'] = True
        apply_entry_filter(d, dict(available=False, reason='Stale'))
        self.assertFalse(d['allowed'])

    def test_exit_requires_distinct_bars_and_resets_on_stale_or_new_position(self):
        assessment = dict(available=True, bar_id='a', continuation_usd={'BUY': -1}, minimum_edge_usd=.25)
        positions = [dict(ticket=1, direction='BUY')]
        state = {}
        for _ in range(20):
            self.assertFalse(learned_exit(assessment, positions, state, 0))
        assessment['bar_id'] = 'b'
        self.assertTrue(learned_exit(assessment, positions, state, 0))
        positions[0]['ticket'] = 2
        self.assertFalse(learned_exit(assessment, positions, state, 0))
        # A quiet quote stays inside the exit ceiling and keeps the lane armed.
        self.assertFalse(learned_exit(assessment, positions, state, 3))
        self.assertEqual(state.get('signature'), (2,))
        # Only a genuinely stale feed disarms it.
        self.assertFalse(learned_exit(assessment, positions, state, 30))
        self.assertEqual(state, {})


class PaperPortfolioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paper = GoldPaperPortfolio(self.temp.name)
        self.paper.mark(100, 100.2, 1000, 0)

    def open(self, lane='SCALP', direction='BUY', **extra):
        d = dict(allowed=True, direction=direction, stop_loss=99 if direction == 'BUY' else 101,
                 take_profit=104 if direction == 'BUY' else 96)
        d.update(extra)
        return self.paper.open(lane, d, margin=2)

    def test_global_cap_fixed_volume_and_no_same_lane_pyramiding(self):
        self.assertTrue(self.open()['success'])
        self.assertFalse(self.open()['success'])
        self.assertTrue(self.open('SWING', 'SELL')['success'])
        self.assertTrue(self.open('INTRADAY')['success'])
        self.assertFalse(self.open('SCALP')['success'])
        self.assertEqual([p['volume'] for p in self.paper.positions], [.01, .01, .01])

    def test_costs_and_cash_reconcile_buy_and_sell(self):
        self.open()
        self.open('SWING', 'SELL')
        self.paper.mark(100.5, 100.7, 1001, 0)
        self.paper.close_lane('SCALP', 'test')
        self.paper.close_lane('SWING', 'test')
        self.assertAlmostEqual(self.paper.balance, 99.4)
        self.assertAlmostEqual(sum(t['profit'] for t in self.paper.trades), -.6)

    def test_gap_stop_uses_worse_quote_not_ideal_stop_fill(self):
        self.open()
        self.paper.mark(97, 97.2, 1001, 0)
        self.assertFalse(self.paper.positions)
        self.assertLess(self.paper.trades[0]['profit'], -3)

    def test_stale_quotes_cannot_fill_or_close(self):
        self.open()
        self.paper.mark(90, 90.2, 1001, 100)
        self.assertEqual(len(self.paper.positions), 1)
        self.assertTrue(self.paper.close_lane('SCALP', 'stale')['failures'])
        self.assertFalse(self.open('SWING')['success'])

    def test_large_profit_does_not_trigger_fixed_target(self):
        self.open()
        self.paper.mark(110, 110.2, 1001, 0)
        self.assertEqual(len(self.paper.positions), 1)

    def test_learned_exit_closes_profitable_paper_position_after_two_bars(self):
        self.open()
        self.paper.mark(110, 110.2, 1001, 0)
        assessment = dict(available=True, bar_id='a', continuation_usd={'BUY': -1}, minimum_edge_usd=.25)
        state = {}
        self.assertFalse(learned_exit(assessment, self.paper.details('SCALP'), state, 0))
        assessment['bar_id'] = 'b'
        self.assertTrue(learned_exit(assessment, self.paper.details('SCALP'), state, 0))
        result = self.paper.close_lane('SCALP', 'Learned adverse continuation')
        self.assertEqual(result['closed_count'], 1)
        self.assertFalse(self.paper.positions)
        self.assertAlmostEqual(self.paper.balance, 109.7)

    def test_wide_stop_margin_and_news_blocks(self):
        self.assertFalse(self.open(stop_loss=90)['success'])
        self.assertFalse(self.open(allowed=False)['success'])
        self.assertFalse(self.paper.open('SCALP', dict(allowed=True), margin=99)['success'])
        self.assertFalse(self.paper.open('SCALP', dict(allowed=True), margin=None)['success'])

    def test_loss_breaker_includes_realized_and_expires(self):
        self.open()
        self.paper.mark(94, 94.2, 1001, 0)
        self.assertFalse(self.open(stop_loss=93, take_profit=98)['success'])
        self.paper.mark(94, 94.2, 100000, 0)
        self.assertTrue(self.open(stop_loss=93, take_profit=98)['success'])


if __name__ == '__main__':
    unittest.main()
