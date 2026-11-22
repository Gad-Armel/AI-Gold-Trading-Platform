import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.research.gold_s30_execution import load_costs, account_fingerprint


class ProvisionalCostTests(unittest.TestCase):
    def setUp(self):
        self.account = SimpleNamespace(login=123, server='Test-Demo', trade_mode=0, currency='USD')
        self.report = dict(as_of='2026-10-21T00:00:00+00:00', symbol='XAUUSD', currency='USD',
            volume=.01, read_only=True, profile_type='PROVISIONAL_DEMO',
            account_fingerprint=account_fingerprint(self.account),
            costs=dict(available=False, reconciled_pairs=0, commission_price=.1, slippage_price=.2))

    def load(self, **kwargs):
        with patch('services.research.gold_s30_execution.Path.read_text', return_value=json.dumps(self.report)):
            return load_costs('unused', now=1792540800+3600, **kwargs)

    def test_explicit_matching_demo_can_use_labelled_assumptions(self):
        result = self.load(allow_provisional=True, account=self.account)
        self.assertEqual(result['profile_type'], 'PROVISIONAL_DEMO')
        self.assertFalse(result['available'])
        self.assertEqual(result['reconciled_pairs'], 0)

    def test_opt_in_and_identity_are_required(self):
        with self.assertRaises(ValueError):
            self.load(account=self.account)
        with self.assertRaises(ValueError):
            self.load(allow_provisional=True)
        self.account.login = 124
        with self.assertRaises(ValueError):
            self.load(allow_provisional=True, account=self.account)

    def test_live_account_cannot_use_provisional_costs(self):
        self.account.trade_mode = 2
        self.report['account_fingerprint'] = account_fingerprint(self.account)
        with self.assertRaises(ValueError):
            self.load(allow_provisional=True, account=self.account)

    def test_provisional_still_rejects_invalid_costs(self):
        self.report['costs']['slippage_price'] = -1
        with self.assertRaises(ValueError):
            self.load(allow_provisional=True, account=self.account)


if __name__ == '__main__':
    unittest.main()
