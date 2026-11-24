import unittest
from unittest.mock import patch

from services.research.gold_s30_shadow import s30_observation
from services.research.gold_s30_execution import directional_signal, entry_check
from services.research.gold_horizon_policy import build_horizon_decisions
from test_gold_horizon_policy import _consensus


class S5Tests(unittest.TestCase):
    def ticks(self):
        return [dict(timestamp=stamp/10, bid=4000+stamp*.01, ask=4000.02+stamp*.01)
                for stamp in range(1200, 2301)]

    def test_three_s5_are_fifteen_seconds_not_forty_five(self):
        report = s30_observation(self.ticks(), now=230, period_seconds=5)
        self.assertTrue(report['available'])
        self.assertEqual([bar['time'] for bar in report['bars']], [215, 220, 225])
        self.assertEqual(report['timeframe'], 'S5')

    def test_s1_research_has_full_six_second_context(self):
        report = s30_observation(self.ticks(), now=230, period_seconds=1)
        self.assertTrue(report['available'])
        self.assertEqual([bar['time'] for bar in report['bars']], [227, 228, 229])
        self.assertNotIn('Insufficient continuous six-second quote coverage', report['fast_candidate']['blocks'])
        self.assertFalse(report['execution_enabled'])

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=0., slippage_price=0.))
    def test_explicit_s1_uses_completed_bars_and_same_entry_checks(self, mocked):
        signal = directional_signal(self.ticks(), now=230, bid=4023, ask=4023.02, atr=2., period_seconds=1)
        self.assertEqual(signal['timeframe'], 'S1')
        self.assertEqual(signal['bias'], 'BUY')
        decision = build_horizon_decisions(_consensus(('SELL', 95), ('SELL', 95), ('SELL', 90)),
            scalp_signal=signal, market_context={'SCALP': dict(available=True, atr=2., bid=4023., ask=4023.02)})['SCALP']
        self.assertEqual(decision['entry_mode'], 'S1_PRIMARY')
        self.assertTrue(decision['allowed'])
        blocks, report = entry_check(dict(direction='BUY'), self.ticks(), now=230,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused', period_seconds=1)
        self.assertEqual(report['entry_timeframe'], 'S1')
        self.assertEqual([bar['time'] for bar in report['bars']], [227, 228, 229])
        self.assertNotIn('Unsupported fast timeframe', blocks)

    def test_sparse_s1_does_not_invent_candles(self):
        ticks = [tick for tick in self.ticks() if tick['timestamp'].is_integer()]
        signal = directional_signal(ticks, now=230, bid=4023, ask=4023.02, atr=2., period_seconds=1)
        self.assertEqual(signal['bias'], 'WAIT')

    def test_short_bars_require_proportional_tick_coverage(self):
        ticks = [tick for tick in self.ticks() if not 221 <= tick['timestamp'] <= 223]
        self.assertFalse(s30_observation(ticks, now=230, period_seconds=5)['available'])
        sparse = [tick for tick in self.ticks() if tick['timestamp'].is_integer()]
        self.assertFalse(s30_observation(sparse, now=230, period_seconds=1)['available'])

    def test_s5_live_policy_and_levels(self):
        ticks = self.ticks()
        signal = directional_signal(ticks, now=230, bid=4023., ask=4023.02, atr=2., period_seconds=5)
        decision = build_horizon_decisions(_consensus(('SELL', 95), ('SELL', 95), ('SELL', 90)),
            scalp_signal=signal, market_context={'SCALP': dict(available=True, atr=2., bid=4023., ask=4023.02)})['SCALP']
        self.assertTrue(decision['allowed'])
        self.assertEqual(decision['entry_mode'], 'S5_PRIMARY')
        self.assertEqual(decision['levels']['source'], 'S5_STRUCTURE')
        self.assertLess(decision['stop_loss'], 4023.)

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=0., slippage_price=0.))
    def test_addition_requires_new_five_second_close(self, mocked):
        for count in (3, 5, 6):
            blocks, report = entry_check(dict(direction='BUY'), self.ticks(), now=230,
                plan=dict(required_bars=count, after_epoch=None), cost_path='unused', period_seconds=5)
            self.assertEqual(blocks, [])
            self.assertEqual(len(report['bars']), count)
        blocks, _ = entry_check(dict(direction='BUY'), self.ticks(), now=230,
            plan=dict(required_bars=5, after_epoch=230), cost_path='unused', period_seconds=5)
        self.assertTrue(any('fresh' in block for block in blocks))

    def test_future_ticks_cannot_change_closed_bars(self):
        ticks = self.ticks()
        report = s30_observation(ticks, now=230, period_seconds=5)
        ticks.append(dict(timestamp=231., bid=1., ask=1.02))
        self.assertEqual(report['bars'], s30_observation(ticks, now=230, period_seconds=5)['bars'])


if __name__ == '__main__':
    unittest.main()
