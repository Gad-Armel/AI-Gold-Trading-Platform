import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.dashboard.gold_consensus_web import read_dashboard_status
from services.dashboard.gold_inverse_reporting import summarize_groups, trading_snapshot
from services.dashboard.gold_dual_reset import reset_both_displays


def deal(ticket, identifier, magic, entry, price, profit=0., comment=''):
    return SimpleNamespace(ticket=ticket, position_id=identifier, magic=magic, entry=entry,
        symbol='XAUUSD', type=0 if entry == 0 else 1, price=price, profit=profit,
        commission=0., swap=0., fee=0., volume=.01, time_msc=1792738000000+ticket*1000,
        comment=comment)


class DualDashboardTests(unittest.TestCase):
    def test_shared_reset_is_display_only_and_uses_actual_open_baselines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'reset.json'
            status = dict(account_fingerprint='same', inverse=dict(fresh=True, trading=dict(available=True,
                main_display=dict(pnl=dict(available=True, floating=2., actual_floating=3.)),
                pnl=dict(available=True, floating=-2., actual_floating=-3.))))
            with patch('services.dashboard.gold_dual_reset.RESET_PATH', path):
                result = reset_both_displays(status, now=1000.)
            self.assertEqual(result['main_open_baseline'], 3.)
            self.assertEqual(result['inverse_open_baseline'], -3.)
            self.assertEqual(json.loads(path.read_text())['reset_epoch'], 1000.)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_reset_filters_closed_history_and_zeroes_open_mark_to_market(self):
        deals = [deal(1, 10, 631011, 0, 4016.04), deal(2, 10, 0, 1, 4014.30, -1.74),
                 deal(3, 20, 631021, 0, 4015.65, comment='INV:10'), deal(4, 20, 0, 1, 4014.78, .87)]
        broker = SimpleNamespace(positions_get=lambda **kwargs: [], history_deals_get=lambda *args: deals,
            account_info=lambda: SimpleNamespace(login=1, server='demo', trade_mode=0))
        reset = dict(reset_epoch=9999999999., main_open_baseline=0., inverse_open_baseline=0.)
        with patch('services.dashboard.gold_inverse_reporting.load_display_reset', return_value=reset):
            report = trading_snapshot(broker)
        self.assertEqual(report['pnl']['total'], 0.)
        self.assertEqual(report['main_display']['pnl']['total'], 0.)
        self.assertEqual(report['closed_trades'], [])
        self.assertEqual(report['main_display']['closed_trades'], [])
        self.assertEqual(report['paired']['combined_net'], 0.)

    def test_reset_with_open_positions_preserves_positions_and_zeroes_display(self):
        deals = [deal(1, 10, 631011, 0, 4000.), deal(2, 20, 631021, 0, 4000., comment='INV:10')]
        positions = [SimpleNamespace(ticket=identifier, identifier=identifier, magic=magic,
            type=0, price_open=4000., price_current=4001., volume=.01, sl=3998., tp=0.,
            profit=profit, swap=0., comment=comment) for identifier, magic, profit, comment in
            [(10, 631011, 2., 'main'), (20, 631021, -1., 'INV:10')]]
        broker = SimpleNamespace(positions_get=lambda **kwargs: positions, history_deals_get=lambda *args: deals,
            account_info=lambda: SimpleNamespace(login=1, server='demo', trade_mode=0))
        reset = dict(reset_epoch=9999999999., main_open_baseline=2., inverse_open_baseline=-1., paired_main_open_baseline=2.)
        with patch('services.dashboard.gold_inverse_reporting.load_display_reset', return_value=reset):
            report = trading_snapshot(broker)
        self.assertEqual(report['pnl']['total'], 0.)
        self.assertEqual(report['main_display']['pnl']['total'], 0.)
        self.assertEqual(report['paired']['combined_net'], 0.)
        self.assertEqual(report['positions'][0]['profit'], -1.)

    def test_matched_pair_uses_same_experiment_not_main_session(self):
        deals = [deal(1, 10, 631011, 0, 4016.04), deal(2, 10, 0, 1, 4014.30, -1.74),
                 deal(3, 20, 631021, 0, 4015.65, comment='INV:10'),
                 deal(4, 20, 0, 1, 4014.78, .87),
                 deal(5, 99, 631011, 0, 4000.), deal(6, 99, 0, 1, 3900., -100.)]
        broker = SimpleNamespace(positions_get=lambda **kwargs: [], history_deals_get=lambda *args: deals)
        report = trading_snapshot(broker)
        self.assertAlmostEqual(report['pnl']['total'], .87)
        self.assertAlmostEqual(report['paired']['main_net'], -1.74)
        self.assertAlmostEqual(report['paired']['combined_net'], -.87)
        self.assertTrue(report['paired']['available'])

    def test_manual_close_fees_are_counted(self):
        deals = [deal(1, 10, 631021, 0, 4000., comment='INV:9'), deal(2, 10, 0, 1, 4001., 1.)]
        deals[0].commission = -.1
        deals[1].fee = -.2
        report = summarize_groups(deals, [], 631021)
        self.assertAlmostEqual(report['total'], .7)

    def test_open_position_has_link_and_missing_entry_history_is_unknown(self):
        position = SimpleNamespace(ticket=20, identifier=20, magic=631021, type=1,
            price_open=4000., price_current=3999., volume=.01, sl=4002., tp=0.,
            profit=1., swap=0., comment='INV:10')
        broker = SimpleNamespace(positions_get=lambda **kwargs: [position], history_deals_get=lambda *args: [])
        report = trading_snapshot(broker)
        self.assertEqual(report['positions'][0]['source_position_id'], '10')
        self.assertFalse(report['pnl']['available'])
        self.assertIsNone(report['pnl']['total'])
        self.assertFalse(report['paired']['available'])

    def test_inverse_failure_does_not_remove_main_and_account_mismatch_is_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            main, inverse = Path(folder)/'main.json', Path(folder)/'inverse.json'
            main.write_text(json.dumps(dict(status='RUNNING', account_fingerprint='same')))
            inverse.write_text(json.dumps(dict(protocol=1, demo_only=True, state='RUNNING',
                account_fingerprint='same', heartbeat_epoch=1000)))
            with patch('services.dashboard.gold_consensus_web.STATUS_PATH', main), patch(
                    'services.dashboard.gold_consensus_web.INVERSE_STATUS_PATH', inverse):
                self.assertTrue(read_dashboard_status(now=1001)['inverse']['fresh'])
                self.assertEqual(read_dashboard_status(now=1020)['inverse']['state'], 'STALE')
                inverse.write_text('{bad')
                result = read_dashboard_status(now=1001)
                self.assertEqual(result['status'], 'RUNNING')
                self.assertFalse(result['inverse']['available'])
                inverse.write_text(json.dumps(dict(account_fingerprint='different', protocol=1, demo_only=True)))
                self.assertFalse(read_dashboard_status(now=1001)['inverse']['available'])


if __name__ == '__main__':
    unittest.main()
