import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from config import gold_inverse_settings as cfg
from services.execution.gold_inverse_demo import InverseDemoExecutor
from services.execution.gold_inverse_policy import inverse_active
from services.execution.gold_consensus_demo_broker import execution_safety, _entry_capacity_block
from services.research.gold_s30_execution import account_fingerprint
from test_gold_consensus_demo_broker import FakeMT5


class MirrorMT5(FakeMT5):
    def __init__(self):
        super().__init__()
        self.info.digits = 2
        self.info.trade_tick_size = .01
        self.pending = []
        self.next_ticket = 100

    def orders_get(self, **kwargs):
        return tuple(self.pending)

    def order_send(self, request):
        self.sent.append(request)
        if 'position' in request:
            self.positions = [row for row in self.positions if row.ticket != request['position']]
        else:
            self.next_ticket += 1
            self.positions.append(SimpleNamespace(ticket=self.next_ticket, identifier=self.next_ticket,
                magic=request['magic'], type=request['type'], volume=request['volume'],
                price_open=request['price'], sl=request['sl'], profit=0., comment=request['comment'], time=1000))
        return SimpleNamespace(retcode=10009, deal=5, order=6)


def source(ticket=7, direction=0, opened=1000):
    return SimpleNamespace(ticket=ticket, identifier=ticket, magic=cfg.SOURCE_MAGIC, type=direction,
        volume=.01, price_open=4000.2, sl=3998. if direction == 0 else 4002.2,
        profit=0., comment='main', time=opened)


class InverseDemoTests(unittest.TestCase):
    def test_main_heartbeat_must_match_inverse_account(self):
        import json
        from datetime import datetime, timezone
        from run_gold_inverse_bot import main_ready
        status = dict(mode='demo', status='RUNNING', account_fingerprint='source',
            updated_at=datetime.fromtimestamp(1000, timezone.utc).isoformat(),
            config=dict(inverse_companion_supported=True))
        with patch('run_gold_inverse_bot.Path.read_text', return_value=json.dumps(status)):
            self.assertTrue(main_ready(1001., 'source'))
            self.assertFalse(main_ready(1001., 'different'))
            self.assertFalse(main_ready(1020., 'source'))

    def setUp(self):
        import tempfile
        from pathlib import Path
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        exit_root = patch('services.execution.gold_pair_exit.ROOT', Path(directory.name))
        exit_root.start()
        self.addCleanup(exit_root.stop)
        self.broker = MirrorMT5()
        self.state = dict(account_fingerprint=account_fingerprint(self.broker.account_info()), links={})
        self.saved = []
        self.engine = InverseDemoExecutor(self.broker, self.state, lambda value: self.saved.append(copy.deepcopy(value)))
        for mocked in (patch('services.execution.gold_inverse_demo.quote_age', return_value=0.),
                       patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0),
                       patch('services.execution.gold_inverse_demo.is_emergency_stop_enabled', return_value=False)):
            mocked.start()
            self.addCleanup(mocked.stop)
        self.engine.cycle(999)

    def test_opposite_open_with_sl_and_no_fixed_tp_then_linked_close(self):
        for direction in (0, 1):
            self.broker.positions = [source(direction=direction)]
            self.state['links'] = {}
            self.broker.sent = []
            self.engine.cycle(1000)
            request = self.broker.sent[0]
            self.assertEqual(request['type'], 1-direction)
            self.assertEqual(request['volume'], .01)
            self.assertGreater(request['sl'], 0)
            self.assertEqual(request['tp'], 0.)
            self.assertEqual(request['magic'], cfg.MAGIC)
            self.assertEqual(self.state['links']['7']['signal_policy'],
                             'INHERIT_MAIN_ANALYSIS_REVERSE_CONFIRMED_FILL')
            self.assertEqual(self.state['links']['7']['source_direction'], 'BUY' if direction == 0 else 'SELL')
            self.assertEqual(self.state['links']['7']['inverse_direction'], 'SELL' if direction == 0 else 'BUY')
            self.assertTrue(any(row['links'].get('7', {}).get('open') == 'INTENT' for row in self.saved))
            self.engine.cycle(1001)
            self.assertEqual(len(self.broker.sent), 1)
            self.broker.positions = [row for row in self.broker.positions if row.magic == cfg.MAGIC]
            self.engine.cycle(1002)
            self.assertEqual(len(self.broker.sent), 2)
            self.assertEqual(self.broker.positions, [])

    def test_inverse_sl_does_not_reopen_while_source_remains(self):
        self.broker.positions = [source()]
        self.engine.cycle(1000)
        self.broker.positions = [source()]
        self.engine.cycle(1001)
        self.assertEqual(len(self.broker.sent), 1)

    def test_close_decision_exits_inverse_before_source_disappears(self):
        import tempfile
        from pathlib import Path
        from services.execution.gold_pair_exit import publish_exit, exit_requested
        with tempfile.TemporaryDirectory() as directory, patch(
                'services.execution.gold_pair_exit.ROOT', Path(directory)):
            self.broker.positions = [source()]
            self.engine.cycle(1000)
            publish_exit(self.broker, source(), 'strategy exit')
            self.assertFalse(exit_requested('7', 'another-account'))
            self.engine.cycle(1001)
            self.assertEqual(len(self.broker.sent), 2)
            self.assertEqual([row.magic for row in self.broker.positions], [cfg.SOURCE_MAGIC])
            self.engine.cycle(1002)
            self.assertEqual(len(self.broker.sent), 2)

    def test_startup_does_not_backfill_existing_main(self):
        self.state.pop('bootstrapped')
        self.broker.positions = [source()]
        self.engine.cycle(1000)
        self.assertFalse(self.broker.sent)
        self.assertEqual(self.state['links']['7']['open'], 'STARTUP_BASELINE_SKIPPED')

    def test_restart_recovers_owned_position_without_duplicate(self):
        self.broker.positions = [source()]
        self.engine.cycle(1000)
        restored = copy.deepcopy(self.state)
        restored['links']['7']['open'] = 'INTENT'
        engine = InverseDemoExecutor(self.broker, restored, lambda value: None)
        engine.cycle(1001)
        self.assertEqual(len(self.broker.sent), 1)

    def test_timeout_intent_is_not_retried(self):
        self.broker.positions = [source()]
        with patch.object(self.broker, 'order_send', return_value=SimpleNamespace(retcode=10012)) as send:
            self.engine.cycle(1000)
            self.engine.cycle(1001)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.state['links']['7']['open'], 'UNCERTAIN')

    def test_missing_positions_cannot_trigger_closes(self):
        self.broker.positions = None
        with self.assertRaises(RuntimeError):
            self.engine.cycle(1000)
        self.assertFalse(self.broker.sent)

    def test_pending_inverse_order_is_reported_during_stop(self):
        self.broker.pending = [SimpleNamespace(magic=cfg.MAGIC)]
        report = self.engine.cycle(1000, stop=True)
        self.assertEqual(report['pending_inverse_orders'], 1)
        self.assertEqual(report['inverse_positions'], 0)

    def test_position_reconciles_uncertain_open_without_retry(self):
        self.broker.positions = [source()]
        self.engine.cycle(1000)
        self.state['links']['7']['open'] = 'UNCERTAIN'
        report = self.engine.cycle(1001)
        self.assertEqual(self.state['links']['7']['open'], 'POSITION_CONFIRMED')
        self.assertFalse(report['uncertain_links'])
        self.assertEqual(len(self.broker.sent), 1)

    def test_real_or_changed_account_is_never_traded(self):
        for changes in (dict(trade_mode=2), dict(login=123)):
            account = self.broker.account_info()
            for key, value in changes.items():
                setattr(account, key, value)
            with patch.object(self.broker, 'account_info', return_value=account):
                with self.assertRaises(RuntimeError):
                    self.engine.cycle(1000)
        self.assertFalse(self.broker.sent)

    def test_budget_capacity_old_source_and_pending_guards(self):
        self.broker.positions = [source(opened=990)]
        self.engine.cycle(1000)
        self.assertFalse(self.broker.sent)
        self.state['links'] = {}
        self.broker.positions = [source()]
        self.broker.positions[0].sl = 3990.
        self.engine.cycle(1000)
        self.assertFalse(self.broker.sent)
        self.state['links'] = {}
        self.broker.positions = [source(ticket=ticket) for ticket in (7, 8, 9, 10)]
        self.engine.cycle(1000)
        self.assertFalse(self.broker.sent)
        self.state['links'] = {}
        self.broker.positions = [source()]
        self.broker.pending = [SimpleNamespace(magic=cfg.MAGIC)]
        self.engine.cycle(1000)
        self.assertFalse(self.broker.sent)

    def test_stop_only_closes_inverse_positions(self):
        self.broker.positions = [source()]
        self.engine.cycle(1000)
        self.engine.cycle(1001, stop=True)
        self.assertEqual([row.magic for row in self.broker.positions], [cfg.SOURCE_MAGIC])

    def test_companion_heartbeat_is_account_bound_and_expires(self):
        import json
        account = self.broker.account_info()
        payload = dict(protocol=1, state='RUNNING', magic=cfg.MAGIC,
            heartbeat_epoch=1000., account_fingerprint=account_fingerprint(account))
        with patch('services.execution.gold_inverse_policy.Path.read_text', return_value=json.dumps(payload)):
            self.assertTrue(inverse_active(account, now=1001.))
            self.assertFalse(inverse_active(account, now=1020.))
            account.login = 99
            self.assertFalse(inverse_active(account, now=1001.))

    @patch('services.execution.gold_consensus_demo_broker.inverse_active', return_value=True)
    @patch('services.execution.gold_consensus_demo_broker.validate_demo_session_identity', return_value=(True, 'demo'))
    def test_main_reserves_two_slots_and_recognizes_authorized_inverse(self, identity, active):
        self.broker.positions = [source(7), source(8)]
        self.assertEqual(_entry_capacity_block(self.broker)['action'], 'POSITION_CAP')
        self.broker.positions = [source()]
        self.broker.positions.append(SimpleNamespace(magic=cfg.MAGIC, volume=.01, ticket=100))
        self.assertTrue(execution_safety(self.broker)[0])

    @patch('services.execution.gold_consensus_demo_broker.inverse_active', return_value=False)
    def test_pair_reservation_does_not_depend_on_heartbeat_reads(self, active):
        self.broker.positions = [source(7), source(8)]
        self.assertEqual(_entry_capacity_block(self.broker)['action'], 'POSITION_CAP')


if __name__ == '__main__':
    unittest.main()
