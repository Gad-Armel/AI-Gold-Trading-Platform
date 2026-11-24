import unittest
from unittest.mock import patch

from config import gold_consensus_settings as settings
from services.execution.gold_consensus_demo_broker import open_horizon_position
from test_gold_consensus_demo_broker import FakeMT5
from tools.audit_gold_trade_strategy import analyze
from services.research.gold_signal_persistence import update_signal_persistence


class AuditRegressionTests(unittest.TestCase):
    def test_confirmation_cannot_be_carried_between_timeframes(self):
        state = {}
        update_signal_persistence(state, direction='BUY', source='S5_PRIMARY', now=10.)
        update_signal_persistence(state, direction='BUY', source='S5_PRIMARY', now=13.)
        self.assertEqual(state['signal_since'], 10.)
        update_signal_persistence(state, direction='BUY', source='S15_PRIMARY', now=14.)
        self.assertEqual(state['signal_since'], 14.)
        self.assertEqual(state['cycles'], 1)
        update_signal_persistence(state, direction='WAIT', source='S15_PRIMARY', now=15.)
        self.assertIsNone(state['signal_since'])

    def setUp(self):
        for mocked in (
            patch('services.execution.gold_consensus_demo_broker.validate_demo_session_identity', return_value=(True, 'demo')),
            patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0),
            patch.dict(settings.HORIZON_LANES['SCALP'], stop_mode='ANALYSIS'),
            patch('services.execution.gold_consensus_demo_broker._journal'),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)

    def decision(self, **overrides):
        return dict(dict(allowed=True, direction='BUY', take_profit=4010., stop_loss=3998., entry_mode='S1_PRIMARY'), **overrides)

    def test_analysis_cannot_bypass_monetary_stop_budget(self):
        broker = FakeMT5()
        result = open_horizon_position(broker, 'SCALP', self.decision(stop_loss=3994.))
        self.assertEqual(result['action'], 'RISK_BUDGET_BLOCK')
        self.assertFalse(broker.sent)

    def test_s1_stop_is_grid_normalized_without_fixed_tp(self):
        broker = FakeMT5()
        broker.info.trade_tick_size = .01
        broker.info.digits = 2
        result = open_horizon_position(broker, 'SCALP', self.decision(stop_loss=3998.005))
        self.assertTrue(result['success'], result)
        self.assertEqual(broker.sent[0]['sl'], 3998.01)
        self.assertEqual(broker.sent[0]['tp'], 0.)
        self.assertEqual(broker.sent[0]['volume'], .01)

    @patch('services.execution.gold_consensus_demo_broker.broker_quote_age', return_value=-10.)
    def test_future_broker_quote_is_not_executable(self, mocked):
        broker = FakeMT5()
        result = open_horizon_position(broker, 'SCALP', self.decision())
        self.assertEqual(result['action'], 'QUOTE_BLOCK')
        self.assertFalse(broker.sent)

    def test_nonfinite_executable_quote_is_rejected(self):
        broker = FakeMT5()
        broker.tick.bid = float('nan')
        result = open_horizon_position(broker, 'SCALP', self.decision())
        self.assertEqual(result['action'], 'QUOTE_BLOCK')

    def test_audit_deduplicates_deals_includes_manual_exit_fees(self):
        entry = dict(ticket=1, position_id=10, symbol='XAUUSD', type=0, entry=0,
            magic=631011, volume=.01, price=4000., time_msc=100000, profit=0., commission=-.1)
        close = dict(ticket=2, position_id=10, symbol='XAUUSD', type=1, entry=1,
            magic=0, volume=.01, price=4001., time_msc=101000, profit=1., fee=-.2)
        result = analyze([entry, close, close], [])
        self.assertEqual(result['summary']['trades'], 1)
        self.assertAlmostEqual(result['summary']['net'], .7)
        self.assertFalse(result['closed_positions'][0]['matched_entry'])
        self.assertEqual(analyze([entry], [])['summary']['trades'], 0)


if __name__ == '__main__':
    unittest.main()
