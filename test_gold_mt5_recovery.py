from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from services.research.gold_mt5_recovery import Mt5Recovery


class RecoveryTests(unittest.TestCase):
    def fake(self):
        account = SimpleNamespace(login=123, server='Demo', trade_mode=0)
        mt5 = Mock()
        mt5.initialize.return_value = True
        mt5.account_info.return_value = account
        mt5.terminal_info.return_value = SimpleNamespace(connected=True)
        return account, mt5

    def test_recovery_is_throttled_and_never_sends_orders(self):
        account, mt5 = self.fake()
        recovery = Mt5Recovery(account)
        self.assertTrue(recovery.attempt(mt5, now=100)['reconnected'])
        self.assertFalse(recovery.attempt(mt5, now=110)['attempted'])
        mt5.initialize.assert_called_once_with(timeout=2000)
        mt5.order_send.assert_not_called()

    def test_account_change_and_live_mode_are_blocked(self):
        for changes in (dict(login=456), dict(server='Other'), dict(trade_mode=2)):
            account, mt5 = self.fake()
            recovery = Mt5Recovery(account)
            mt5.account_info.return_value = SimpleNamespace(**(vars(account) | changes))
            self.assertFalse(recovery.attempt(mt5, now=100)['reconnected'])
            mt5.order_send.assert_not_called()

    def test_failed_initialization_is_not_recovery(self):
        account, mt5 = self.fake()
        mt5.initialize.return_value = False
        self.assertFalse(Mt5Recovery(account).attempt(mt5, now=100)['reconnected'])
        mt5.account_info.assert_not_called()

    def test_real_account_cannot_arm_recovery(self):
        with self.assertRaises(ValueError):
            Mt5Recovery(SimpleNamespace(login=123, server='Live', trade_mode=2))
