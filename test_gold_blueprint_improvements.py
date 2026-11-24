import unittest
from unittest.mock import patch
from services.execution.gold_consensus_demo_broker import open_horizon_position, _money_stop_price
from services.execution.gold_execution_metrics import execution_metrics
from services.research.gold_profit_lock import profit_lock_exit
from test_gold_consensus_demo_broker import FakeMT5


class BlueprintImprovementTests(unittest.TestCase):
    def setUp(self):
        from config import gold_consensus_settings as settings
        fixed = patch.dict(settings.HORIZON_LANES['SCALP'], stop_mode='INDIVIDUAL', individual_stop_loss_usd=5.0)
        fixed.start(); self.addCleanup(fixed.stop)
        for target, value in [
                ('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0),
                ('services.execution.gold_consensus_demo_broker.validate_demo_session_identity', (True, ''))]:
            item = patch(target, return_value=value) if isinstance(value, tuple) else patch(target, value)
            item.start()
            self.addCleanup(item.stop)
        journal = patch('services.execution.gold_consensus_demo_broker._journal')
        journal.start()
        self.addCleanup(journal.stop)

    def test_stop_uses_injected_broker_and_only_two_profit_calls(self):
        mt5 = FakeMT5()
        with patch.object(mt5, 'order_calc_profit', wraps=mt5.order_calc_profit) as calc:
            result = open_horizon_position(mt5, 'SCALP', dict(
                allowed=True, direction='BUY', take_profit=4004, stop_loss=3998))
        self.assertTrue(result['success'])
        self.assertEqual(calc.call_count, 2)
        self.assertAlmostEqual(mt5.sent[0]['sl'], 3995.2)

    def test_coarse_grid_rounds_stop_inward_on_both_sides(self):
        mt5 = FakeMT5()
        mt5.info.trade_tick_size = .5
        for direction, price in [('BUY',4000.2), ('SELL',4000.2)]:
            stop = _money_stop_price(mt5, mt5.info, direction, .01, price, 5)
            loss = -mt5.order_calc_profit(0 if direction == 'BUY' else 1, 'XAUUSD', .01, price, stop)
            self.assertLessEqual(loss, 5+1e-8)
            self.assertGreater(loss, 4.5)
            self.assertAlmostEqual(stop/.5, round(stop/.5))

    def test_impossible_minimum_stop_and_failed_valuation_send_nothing(self):
        decision = dict(allowed=True, direction='BUY', take_profit=4004, stop_loss=3998)
        mt5 = FakeMT5()
        mt5.info.trade_stops_level = 600
        self.assertEqual(open_horizon_position(mt5, 'SCALP', decision)['action'], 'STOP_GRID_BLOCK')
        self.assertEqual(mt5.sent, [])
        mt5 = FakeMT5()
        mt5.order_calc_profit = lambda *args: None
        self.assertEqual(open_horizon_position(mt5, 'SCALP', decision)['action'], 'RISK_BUDGET_BLOCK')
        self.assertEqual(mt5.sent, [])

    def test_reported_fills_and_pending_acceptance_are_distinguished(self):
        request = dict(type=0, price=100., volume=.01)
        values = execution_metrics(request, dict(retcode=10009,price=100.2,volume=.01),
                                   elapsed_ms=30, point=.01, contract_size=100)
        self.assertAlmostEqual(values['reported_adverse_slippage_usd'], .2)
        pending = execution_metrics(request, dict(retcode=10008,price=100.2,volume=.01),
                                    elapsed_ms=30, point=.01, contract_size=100)
        self.assertIsNone(pending['reported_adverse_slippage_usd'])
        self.assertEqual(pending['state'], 'ACCEPTED_PENDING')
        self.assertTrue(pending['deal_history_confirmation_required'])

    def test_quote_only_profit_lock_is_independent_and_retains_failure_retry_peak(self):
        positions = [dict(ticket=1,direction='BUY',entry_price=100.,volume=.01)]
        state = {}
        args = dict(config=dict(profit_lock_arm_usd=6,profit_lock_retained_fraction=.8),
                    contract_size=100, feed_age=0, now=100)
        self.assertFalse(profit_lock_exit(positions,state,bid=106,ask=106.2,**args)['close'])
        # No candle context or AI inference is required for this quote-only rule.
        result = profit_lock_exit(positions,state,bid=104.8,ask=105,**args)
        self.assertEqual(result['close_tickets'], [1])
        self.assertEqual(profit_lock_exit(positions,state,bid=104.7,ask=104.9,**args)['close_tickets'], [1])
        stale = dict(args, feed_age=100)
        self.assertFalse(profit_lock_exit(positions,state,bid=104,ask=104.2,**stale)['close'])
        self.assertEqual(state['ticket_profit_peaks']['1'], 6)
        # A new ticket cannot inherit the previous winner's peak.
        positions[0]['ticket'] = 2
        self.assertFalse(profit_lock_exit(positions,state,bid=104.8,ask=105,**args)['close'])

    def test_partial_volume_change_scales_peak_and_rebound_does_not_reset_timer(self):
        positions = [dict(ticket=1,direction='BUY',entry_price=100.,volume=.02)]
        state = {}
        args = dict(config=dict(profit_lock_arm_usd=6,profit_lock_retained_fraction=.8),
                    contract_size=100, feed_age=0, now=100)
        profit_lock_exit(positions,state,bid=106,ask=106.2,**args)
        state['adverse_since'] = 90
        profit_lock_exit(positions,state,bid=106,ask=106.2,**args)
        self.assertEqual(state['adverse_since'], 90)
        positions[0]['volume'] = .01
        result = profit_lock_exit(positions,state,bid=105,ask=105.2,**args)
        self.assertEqual(state['ticket_profit_peaks']['1'], 6)
        self.assertFalse(result['close'])


if __name__ == '__main__':
    unittest.main()
