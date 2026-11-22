import unittest
from services.research.gold_flow_exit import evaluate_flow_exit


class FlowExitTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.positions = [dict(ticket=1, direction='BUY', entry_price=2000., volume=.01)]

    def quote(self, t, bid, ask=None, **kwargs):
        return evaluate_flow_exit(self.positions, self.state, now=t, quote_time=kwargs.get('quote_time', t),
                                  bid=bid, ask=bid+.1 if ask is None else ask, horizon=kwargs.get('horizon', 'SCALP'))

    def test_buy_loss_reversal_before_candle_close(self):
        outcomes = [self.quote(t, 2000-t*.1) for t in range(0, 22, 2)]
        self.assertFalse(any(x['close'] for x in outcomes[:9]))
        self.assertTrue(outcomes[-1]['close'])

    def test_sell_reversal(self):
        self.positions[0]['direction'] = 'SELL'
        self.assertTrue([self.quote(t, 2000+t*.1) for t in range(0,22,2)][-1]['close'])

    def test_profitable_trend_is_not_fixed_target(self):
        self.assertFalse(any(self.quote(t, 2000+t*.2)['close'] for t in range(0,100,2)))

    def test_profit_giveback(self):
        for t in range(0,30,2): self.quote(t, 2000+t*.2)
        results = [self.quote(t, 2005.6-(t-28)*.1) for t in range(30,60,2)]
        self.assertTrue(any(x['close'] for x in results))
        self.assertGreater(results[-1]['move'], 0)

    def test_spread_only_does_not_exit(self):
        self.assertFalse(any(self.quote(t, 2000-t*.1, 2001)['close'] for t in range(0,30,2)))

    def test_repeated_quote_does_not_confirm(self):
        for t in range(0,16,2): self.quote(t, 2000-t*.1)
        self.assertFalse(self.quote(15,1998.6,quote_time=14)['close'])
        self.assertEqual(self.state['adverse_since'],12)

    def test_quiet_quote_within_ceiling_still_manages_the_position(self):
        """A few seconds without a new tick is a quiet market, not a dead feed.

        Disarming here left positions unmanaged during slow adverse drifts.
        """
        for t in range(0,16,2): self.quote(t, 2000-t*.1)
        self.assertEqual(self.state['adverse_since'],12)
        result = self.quote(21,1997.8,quote_time=18)
        self.assertNotIn('unavailable', result['reason'])
        self.assertEqual(self.state['adverse_since'],12)

    def test_stale_future_and_gap_reset_confirmation(self):
        for t in range(0,16,2): self.quote(t, 2000-t*.1)
        self.assertFalse(self.quote(40,1998,quote_time=17)['close'])
        self.assertIsNone(self.state['adverse_since'])
        self.assertFalse(self.quote(20,1998,quote_time=26)['close'])
        self.quote(22,1998)
        self.assertFalse(self.quote(40,1995)['close'])
        self.assertEqual(len(self.state['samples']),1)

    def test_new_position_does_not_inherit_flow(self):
        for t in range(0,16,2): self.quote(t, 2000-t*.1)
        self.positions[0]['ticket'] = 2
        self.assertFalse(self.quote(16,1998.4)['close'])
        self.assertEqual(len(self.state['samples']),1)

    def test_small_clock_skew_keeps_quote_reversal_protection_active(self):
        results = [self.quote(t, 2000-t*.1, quote_time=t+2.6) for t in range(0, 24, 2)]
        self.assertTrue(any(result['close'] for result in results))
        self.assertNotIn('unavailable', results[-1]['reason'])

    def test_swing_requires_longer_evidence(self):
        self.assertFalse(any(self.quote(t,2000-t*.1,horizon='SWING')['close'] for t in range(0,100,2)))
        self.assertTrue(any(self.quote(t,2000-t*.1,horizon='SWING')['close'] for t in range(100,130,2)))

    def test_flat_clears_state(self):
        self.quote(0,2000)
        self.positions=[]
        self.quote(2,2000)
        self.assertEqual(self.state,{})
