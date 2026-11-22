import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.execution.gold_consensus_demo_broker import _final_entry_quote
from test_gold_consensus_demo_broker import FakeMT5


class FinalQuoteTests(unittest.TestCase):
    def check(self, mt5, direction='BUY'):
        request = dict(type=0 if direction == 'BUY' else 1, price=4000.2 if direction == 'BUY' else 4000.,
                       sl=3998. if direction == 'BUY' else 4002., volume=.01, deviation=20)
        with patch('services.execution.gold_consensus_demo_broker.broker_quote_age', return_value=0.):
            return _final_entry_quote(mt5, mt5.info, request,
                                     4004. if direction == 'BUY' else 3996., request['sl'])

    def test_unchanged_buy_and_sell_remain_eligible(self):
        for direction in ('BUY', 'SELL'):
            block, quote = self.check(FakeMT5(), direction)
            self.assertIsNone(block)
            self.assertEqual(quote['drift_price'], 0.)

    def test_both_direction_price_drift_is_rejected(self):
        for direction in ('BUY', 'SELL'):
            mt5 = FakeMT5()
            mt5.tick.bid += .5
            mt5.tick.ask += .5
            block, _ = self.check(mt5, direction)
            self.assertEqual(block['action'], 'FINAL_QUOTE_BLOCK')

    def test_small_move_and_exact_budget_are_allowed(self):
        mt5 = FakeMT5()
        mt5.tick.bid += .2
        mt5.tick.ask += .2
        block, quote = self.check(mt5)
        self.assertIsNone(block)
        self.assertAlmostEqual(quote['drift_price'], .2)

    def test_missing_invalid_or_exception_quote_blocks(self):
        for quote in (None, SimpleNamespace(bid=float('nan'), ask=4000.2, time_msc=1),
                      SimpleNamespace(bid=4001., ask=4000., time_msc=1)):
            mt5 = FakeMT5()
            mt5.tick = quote
            block, _ = self.check(mt5)
            self.assertEqual(block['action'], 'FINAL_QUOTE_BLOCK')
        mt5 = FakeMT5()
        with patch.object(mt5, 'symbol_info_tick', side_effect=RuntimeError('disconnect')):
            self.assertEqual(self.check(mt5)[0]['action'], 'FINAL_QUOTE_BLOCK')

    def test_stale_final_quote_and_changed_risk_are_rejected(self):
        mt5 = FakeMT5()
        request = dict(type=0, price=4000.2, sl=3998., volume=.01, deviation=20)
        with patch('services.execution.gold_consensus_demo_broker.broker_quote_age', return_value=10.):
            block, _ = _final_entry_quote(mt5, mt5.info, request, 4004., 3998.)
            self.assertEqual(block['action'], 'FINAL_QUOTE_BLOCK')
        with patch('services.execution.gold_consensus_demo_broker._planned_risk_block',
                   return_value=dict(message='Risk budget exceeded')):
            self.assertEqual(self.check(mt5)[0]['action'], 'FINAL_QUOTE_BLOCK')


if __name__ == '__main__':
    unittest.main()
