import unittest

from services.research.gold_s30_execution import position_exit_signal
from services.research.gold_adaptive_exit import evaluate_adaptive_exit


class FastExitCoherenceTests(unittest.TestCase):
    def evaluate(self, signal, state, now, *, momentum=1., bid=100.):
        return evaluate_adaptive_exit(signal,
            [dict(ticket=1, direction='BUY', volume=.01, entry_price=100., sl=98.)],
            dict(available=True, atr=2., trend=1., momentum=momentum, close=105., previous_low=100., previous_high=110.),
            state, now=now, bid=bid, ask=bid+.2, feed_age=0., risk_usd=2., contract_size=100.,
            config=dict(exit_confirmation_seconds=2, trail_arm_r=100, breakeven_arm_r=100))

    def test_opposing_advisor_context_does_not_invalidate_fast_thesis(self):
        decision = dict(allowed=True, direction='BUY', entry_mode='S5_PRIMARY',
                        advisor1_context=dict(direction='SELL', role='CONTEXT_ONLY'))
        state = {}
        signal = position_exit_signal(decision)
        self.assertFalse(self.evaluate(signal, state, 0)['close'])
        self.assertFalse(self.evaluate(signal, state, 3)['close'])
        self.assertEqual(signal['exit_thesis_source'], 'S5_PRIMARY')
        legacy = dict(allowed=True, direction='SELL')
        state = {}
        self.evaluate(legacy, state, 0)
        self.assertTrue(self.evaluate(legacy, state, 3)['close'])

    def test_actual_fast_reversal_still_closes(self):
        signal = position_exit_signal(dict(allowed=True, direction='SELL', entry_mode='S5_PRIMARY'))
        state = {}
        self.evaluate(signal, state, 0)
        result = self.evaluate(signal, state, 3)
        self.assertTrue(result['close'])
        self.assertEqual(result['reason'], 'Confirmed market thesis invalidation')

    def test_fast_neutral_invalidation_does_not_require_context_advisors(self):
        for frame in ('S1', 'S5', 'S15', 'S30'):
            signal = position_exit_signal(dict(allowed=False, direction='WAIT', dominant_bias='WAIT',
                entry_mode=frame+'_PRIMARY', contributors=[
                    dict(advisor=frame+'_TICKS', bias='WAIT', source_usable=True),
                    dict(advisor='MT5_CANDLES', bias='BUY', source_usable=True),
                    dict(advisor='API_CANDLES', bias='SELL', source_usable=True)]))
            state = {}
            self.assertFalse(self.evaluate(signal, state, 0, momentum=-1., bid=99.)['close'])
            result = self.evaluate(signal, state, 3, momentum=-1., bid=99.)
            self.assertTrue(result['close'])
            self.assertIn('neutral directional thesis', result['reason'])

    def test_stale_fast_source_is_not_a_confirmed_neutral_signal(self):
        signal = position_exit_signal(dict(allowed=False, direction='WAIT', dominant_bias='WAIT',
            entry_mode='S5_PRIMARY', contributors=[dict(advisor='S5_TICKS', bias='WAIT', source_usable=False)]))
        state = {}
        self.evaluate(signal, state, 0, momentum=-1., bid=99.)
        self.assertFalse(self.evaluate(signal, state, 3, momentum=-1., bid=99.)['close'])

    def test_neutral_fast_source_still_requires_opposing_momentum_and_loss(self):
        signal = position_exit_signal(dict(allowed=False, direction='WAIT', dominant_bias='WAIT',
            entry_mode='S5_PRIMARY', contributors=[dict(advisor='S5_TICKS', bias='WAIT', source_usable=True)]))
        state = {}
        self.evaluate(signal, state, 0, momentum=1., bid=99.)
        self.assertFalse(self.evaluate(signal, state, 3, momentum=1., bid=99.)['close'])
        state = {}
        self.evaluate(signal, state, 0, momentum=-1., bid=100.)
        self.assertFalse(self.evaluate(signal, state, 3, momentum=-1., bid=100.)['close'])

    def test_news_and_decision_isolation_are_preserved(self):
        decision = dict(allowed=True, direction='BUY', entry_mode='S15_PRIMARY',
                        news_block=True, news_policy='CLOSE_AND_BLOCK', blocks=[])
        signal = position_exit_signal(decision)
        signal['blocks'].append('test')
        self.assertEqual(decision['blocks'], [])
        self.assertTrue(self.evaluate(signal, {}, 0)['close'])


if __name__ == '__main__':
    unittest.main()
