import unittest
from unittest.mock import patch
from services.dashboard.gold_consensus_web import read_dashboard_status


class MainPnlTests(unittest.TestCase):
    def test_disabled_inverse_cannot_override_main_broker_history(self):
        main = dict(account_fingerprint='demo', pnl=dict(realized=-49.51),
                    lanes=dict(SCALP=dict(closed_trades=[dict(position_id=123)])))
        inverse = dict(protocol=1, account_fingerprint='demo', demo_only=True,
            heartbeat_epoch=100., state='RUNNING', trading=dict(available=True,
                main_display=dict(pnl=dict(available=True, realized=-1.79), closed_trades=[])))
        with patch('services.dashboard.gold_consensus_web._read_status_json', side_effect=[main,inverse,{}]), \
             patch('config.gold_inverse_settings.EXECUTOR_ENABLED', False):
            result = read_dashboard_status(now=101.)
        self.assertEqual(result['pnl']['realized'], -49.51)
        self.assertEqual(result['lanes']['SCALP']['closed_trades'][0]['position_id'], 123)
