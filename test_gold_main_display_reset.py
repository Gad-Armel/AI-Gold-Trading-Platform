import unittest
from unittest.mock import patch
import json
from services.dashboard.gold_main_display_reset import apply_main_display_reset, reset_main_display


class MainResetTests(unittest.TestCase):
    def test_reset_uses_raw_pnl_and_preserves_positions_and_broker_values(self):
        raw = dict(available=True, realized=-10., floating=2., total=-8.)
        status = dict(account_fingerprint='demo', updated_at='1970-01-01T00:01:40+00:00',
                      pnl=raw, positions=[dict(ticket=1)], lanes=dict(SCALP=dict(closed_trades=[
                          dict(closed_at='1970-01-01T00:01:30+00:00')])))
        with patch('services.dashboard.gold_main_display_reset.atomic_write_json') as write:
            reset_main_display(status, now=100.)
            baseline = write.call_args.args[1]
        with patch('pathlib.Path.read_text', return_value=json.dumps(baseline)):
            result = apply_main_display_reset(status)
        self.assertEqual(result['pnl']['total'], 0)
        self.assertEqual(result['broker_pnl'], raw)
        self.assertEqual(result['positions'], [dict(ticket=1)])
        self.assertEqual(result['lanes']['SCALP']['closed_trades'], [])
        with patch('services.dashboard.gold_main_display_reset.atomic_write_json') as write:
            reset_main_display(result, now=101.)
            self.assertEqual(write.call_args.args[1]['realized'], -10.)

    def test_stale_snapshot_cannot_reset(self):
        with self.assertRaises(ValueError):
            reset_main_display(dict(account_fingerprint='demo', updated_at='1970-01-01T00:00:00+00:00',
                pnl=dict(available=True)), now=100.)
