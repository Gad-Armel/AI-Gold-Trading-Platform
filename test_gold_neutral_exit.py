import unittest
from services.research.gold_adaptive_exit import evaluate_adaptive_exit


class NeutralThesisExitTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.decision = dict(allowed=False, direction='WAIT', dominant_bias='WAIT', evidence=15,
            continuous_directional_entries=True,
            contributors=[dict(advisor=name, source_usable=True, bias='WAIT')
                          for name in ('MT5_CANDLES', 'API_CANDLES')])
        self.context = dict(available=True, atr=2, momentum=-.5, trend=.2,
                            close=100, previous_low=95, previous_high=105)

    def evaluate(self, now, bid=98):
        return evaluate_adaptive_exit(self.decision,
            [dict(ticket=1, direction='BUY', entry_price=100, volume=.01, sl=95)],
            self.context, self.state, now=now, bid=bid, ask=bid+.2, feed_age=0,
            config=dict(exit_confirmation_seconds=30, stagnation_seconds=7200),
            risk_usd=5, contract_size=100)

    def test_fresh_neutral_thesis_requires_confirmation_before_cutting_loss(self):
        self.assertFalse(self.evaluate(1000)['close'])
        self.assertFalse(self.evaluate(1029)['close'])
        result = self.evaluate(1030)
        self.assertTrue(result['close'])
        self.assertIn('neutral', result['reason'])

    def test_source_outage_is_not_neutral_confirmation(self):
        self.decision['contributors'][1]['source_usable'] = False
        self.assertFalse(self.evaluate(1000)['close'])
        self.assertFalse(self.evaluate(1100)['close'])

    def test_spread_noise_and_recovery_do_not_trigger_loss_exit(self):
        self.assertFalse(self.evaluate(1000, 99.8)['close'])
        self.assertFalse(self.evaluate(1100, 99.8)['close'])
        self.evaluate(1200)
        self.context['momentum'] = .5
        self.assertFalse(self.evaluate(1300)['close'])
