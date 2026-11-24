import tempfile
import unittest
from unittest.mock import patch
from config import gold_consensus_settings as settings
from services.research.gold_scalp_additions import addition_blocks
from services.execution.gold_consensus_demo_broker import open_horizon_position
from services.execution.gold_paper_portfolio import GoldPaperPortfolio
from test_gold_consensus_demo_broker import FakeMT5


class ScalpOnlyTests(unittest.TestCase):
    def test_secondary_orders_disabled_at_broker(self):
        mt5 = FakeMT5()
        for lane in ('INTRADAY', 'SWING'):
            self.assertEqual(open_horizon_position(mt5, lane, {})['action'], 'ANALYSIS_ONLY')
        self.assertEqual(mt5.sent, [])

    def test_additions_never_average_down_or_hedge(self):
        position = dict(direction='BUY', entry_price=100., volume=.01, profit=-1, sl=98)
        self.assertTrue(addition_blocks(dict(direction='BUY'), [position], 99, 99.2))
        position['profit'] = 1
        self.assertTrue(addition_blocks(dict(direction='SELL'), [position], 101, 101.2))
        self.assertEqual(addition_blocks(dict(direction='BUY'), [position], 101, 101.2), [])

    def test_paper_account_cap_allows_three_positions_but_not_four(self):
        with tempfile.TemporaryDirectory() as root:
            paper = GoldPaperPortfolio(root)
            for index in range(3):
                price = 4000 + index
                paper.mark(price, price+.2, 1000+index*20, 0)
                decision = dict(allowed=True, direction='BUY', evidence=85, take_profit=price+5, stop_loss=price-5)
                self.assertTrue(paper.open('SCALP', decision, margin=10, stop_mode='INDIVIDUAL')['success'])
            self.assertEqual(len(paper.positions), 3)
            self.assertTrue(all(abs(p['entry_price']-p['sl']-5)<1e-8 for p in paper.positions))
            self.assertFalse(paper.open('SCALP', decision, margin=10, stop_mode='INDIVIDUAL')['success'])
            self.assertFalse(paper.open('INTRADAY', decision, margin=10, stop_mode='INDIVIDUAL')['success'])

    def test_fourth_position_needs_stronger_current_evidence(self):
        positions = [dict(direction='BUY', entry_price=100., volume=.01, profit=1., sl=98)] * 3
        for evidence in (84.99, float('nan'), None):
            self.assertTrue(addition_blocks(dict(direction='BUY', evidence=evidence), positions, 101, 101.2))
        self.assertEqual(addition_blocks(dict(direction='BUY', evidence=85), positions, 101, 101.2), [])

    def test_additions_block_missing_invalid_or_crossed_stops(self):
        position = dict(direction='BUY', entry_price=100., volume=.01, profit=1.)
        for stop in (None, 0, float('nan'), 102):
            self.assertTrue(addition_blocks(dict(direction='BUY'), [dict(position, sl=stop)], 101, 101.2))
        self.assertEqual(addition_blocks(dict(direction='BUY'), [dict(position, sl=100.5)], 101, 101.2), [])
        position.update(direction='SELL', entry_price=102)
        self.assertEqual(addition_blocks(dict(direction='SELL'), [dict(position, sl=101.5)], 101, 101.2), [])
