import unittest
from unittest.mock import patch

from config import gold_consensus_settings as settings
from services.execution.gold_consensus_demo_broker import _entry_capacity_block
from services.dashboard.gold_consensus_web import HTML
from test_gold_consensus_demo_broker import FakeMT5, position


class ThreePositionLimitTests(unittest.TestCase):
    def test_fixed_lot_and_both_limits(self):
        self.assertEqual(settings.LOT_SIZE, .01)
        self.assertEqual(settings.MAX_POSITION_SLOTS, 3)
        self.assertEqual(settings.HORIZON_LANES['SCALP']['max_positions'], 3)
        self.assertIn('three combined positions maximum', HTML)

    def test_broker_gate_never_allows_fourth_even_if_config_is_larger(self):
        mt5 = FakeMT5()
        mt5.positions = [position(magic=631011, ticket=ticket) for ticket in range(1, 4)]
        with patch('config.gold_consensus_settings.MAX_POSITION_SLOTS', 5):
            self.assertEqual(_entry_capacity_block(mt5)['action'], 'POSITION_CAP')
        self.assertEqual(mt5.sent, [])


if __name__ == '__main__':
    unittest.main()
