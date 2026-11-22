import tempfile
import unittest
from unittest.mock import patch
from services.execution.gold_paper_portfolio import GoldPaperPortfolio


class PaperRiskParityTests(unittest.TestCase):
    def test_quiet_but_fresh_broker_tick_still_allows_protective_exits(self):
        with tempfile.TemporaryDirectory() as root:
            paper = GoldPaperPortfolio(root)
            paper.mark(4000, 4000.2, 1000, 100, exit_quote_age=0)
            self.assertFalse(paper.valid_quote)
            self.assertTrue(paper.valid_exit_quote)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paper = GoldPaperPortfolio(self.tmp.name)
        self.paper.mark(4000, 4000.2, 1000, 0)
        self.decision = dict(allowed=True, direction='BUY', take_profit=4005,
                             stop_loss=3995, levels={})

    def test_individual_stop_uses_same_five_dollar_budget_as_demo(self):
        result = self.paper.open('SCALP', self.decision, margin=10, stop_mode='INDIVIDUAL')
        self.assertTrue(result['success'], result)
        p = self.paper.positions[0]
        self.assertAlmostEqual(p['entry_price']-p['sl'], 5)
        self.paper.mark(3997, 3997.2, 1001, 0)
        self.assertEqual(len(self.paper.positions), 1)
        self.paper.mark(3994, 3994.2, 1002, 0)
        self.assertEqual(len(self.paper.positions), 0)
        self.assertLess(self.paper.trades[0]['profit'], -5)  # gap/slippage, not clipped

    @patch('config.gold_consensus_settings.SESSION_LOSS_STOP_ENABLED', False)
    def test_disabled_session_stop_keeps_paper_trading_after_loss(self):
        self.paper.balance = 94
        self.paper.trades.append(dict(profit=-6, closed_epoch=999))
        self.assertTrue(self.paper.open('SCALP', self.decision, margin=10,
                                       stop_mode='INDIVIDUAL')['success'])

    @patch('config.gold_consensus_settings.SESSION_LOSS_STOP_ENABLED', True)
    def test_enabled_session_stop_still_blocks(self):
        self.paper.trades.append(dict(profit=-6, closed_epoch=999))
        self.assertFalse(self.paper.open('SCALP', self.decision, margin=10,
                                        stop_mode='INDIVIDUAL')['success'])

    def test_margin_reserves_current_stop_budget(self):
        self.assertFalse(self.paper.open('SCALP', self.decision, margin=96,
                                        stop_mode='INDIVIDUAL')['success'])

    def test_exit_freshness_is_independent_of_entry_freshness(self):
        self.assertTrue(self.paper.open('SCALP', self.decision, margin=10,
                                       stop_mode='INDIVIDUAL')['success'])
        self.paper.mark(3998, 3998.2, 1001, 3)
        self.assertFalse(self.paper.valid_quote)
        self.assertTrue(self.paper.valid_exit_quote)
        self.assertEqual(self.paper.close_lane('SCALP', 'confirmed exit')['closed_count'], 1)
        self.assertFalse(self.paper.open('INTRADAY', self.decision, margin=10,
                                        stop_mode='INDIVIDUAL')['success'])


if __name__ == '__main__':
    unittest.main()
