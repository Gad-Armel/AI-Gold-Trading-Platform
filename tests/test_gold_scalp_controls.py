"""Control mailbox and real HTTP boundaries; no connection to a trading account."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.dashboard.gold_scalp_controls import ControlMailbox, ControlConflict
from services.dashboard.gold_scalp_web import create_server
from tests.test_gold_scalp_web import sample


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = 'dashboard_TEST_1.json'
        self.payload = dict(source=self.source, instance='chart_123', action='pause')
        self.snapshot = sample()
        self.snapshot.update(locked=False, controls=dict(enabled=True, instance='chart_123',
                             last_id='', can_execute=True, liquidating=False))
        self.status = dict(state='live', source=self.source, snapshot=self.snapshot)
        self.mailbox = ControlMailbox(self.directory)

    def test_reset_requires_explicit_native_capability(self):
        payload = {**self.payload, 'action': 'reset_session'}
        with self.assertRaises(ControlConflict):
            self.mailbox.enqueue(payload, self.status, 1000)
        self.snapshot['locked'] = True
        self.snapshot['controls']['can_reset'] = True
        result = self.mailbox.enqueue(payload, self.status, 1000)
        self.assertEqual(result['action'], 'reset_session')
        self.assertIn(';reset_session;END', (self.directory / 'control_TEST_1.csv').read_text())

    def test_queued_is_not_acknowledged_and_wire_is_bound_to_instance(self):
        result = self.mailbox.enqueue(self.payload, self.status, 1000)
        self.assertEqual(result['state'], 'queued')
        wire = (self.directory / 'control_TEST_1.csv').read_text().strip().split(';')
        self.assertEqual(wire, ['GOLD_CONTROL_V1', 'chart_123', result['id'], '1000', '1010', 'pause', 'END'])
        self.assertEqual(len(result['id']), 32)

    def test_unacknowledged_request_cannot_be_overwritten_even_if_consumed(self):
        self.mailbox.enqueue(self.payload, self.status, 1000)
        (self.directory / 'control_TEST_1.csv').unlink()
        with self.assertRaises(ControlConflict):
            self.mailbox.enqueue(self.payload, self.status, 1001)

    def test_acknowledged_command_permits_next_request(self):
        result = self.mailbox.enqueue(self.payload, self.status, 1000)
        (self.directory / 'control_TEST_1.csv').unlink()
        self.snapshot['controls']['last_id'] = result['id']
        self.assertNotEqual(self.mailbox.enqueue(self.payload, self.status, 1001)['id'], result['id'])

    def test_stale_disabled_wrong_instance_and_wrong_account_refused(self):
        cases = [dict(state='stale'), dict(source='dashboard_OTHER.json')]
        for change in cases:
            with self.assertRaises(ControlConflict):
                self.mailbox.enqueue(self.payload, {**self.status, **change})
        for key, value in [('enabled', False), ('instance', 'restarted')]:
            original = self.snapshot['controls'][key]
            self.snapshot['controls'][key] = value
            with self.assertRaises(ControlConflict):
                self.mailbox.enqueue(self.payload, self.status)
            self.snapshot['controls'][key] = original

    def test_resume_cannot_clear_safety_lock_or_liquidation(self):
        payload = {**self.payload, 'action': 'resume'}
        self.snapshot['locked'] = True
        with self.assertRaises(ControlConflict): self.mailbox.enqueue(payload, self.status)
        self.snapshot['locked'] = False
        self.snapshot['controls']['liquidating'] = True
        with self.assertRaises(ControlConflict): self.mailbox.enqueue(payload, self.status)

    def test_disabled_execution_refuses_close_all(self):
        self.snapshot['controls']['can_execute'] = False
        with self.assertRaises(ControlConflict):
            self.mailbox.enqueue({**self.payload, 'action': 'close_all'}, self.status)

    def test_invalid_paths_actions_and_extra_fields_refused(self):
        for change in [dict(source='../escape.json'), dict(instance='x;y'), dict(action='buy'), dict(extra=True)]:
            with self.assertRaises(ValueError): self.mailbox.enqueue({**self.payload, **change}, self.status)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_existing_fresh_mailbox_survives_server_restart(self):
        self.mailbox.enqueue(self.payload, self.status)
        with self.assertRaises(ControlConflict):
            ControlMailbox(self.directory).enqueue(self.payload, self.status)

    def test_expired_mailbox_can_be_replaced(self):
        first = self.mailbox.enqueue(self.payload, self.status, 1000)
        os.utime(self.directory / 'control_TEST_1.csv', (1000, 1000))
        second = self.mailbox.enqueue(self.payload, self.status, 1013)
        self.assertNotEqual(first['id'], second['id'])

    def test_concurrent_clicks_produce_only_one_command(self):
        results = []
        def click():
            try: results.append(self.mailbox.enqueue(self.payload, self.status)['id'])
            except ControlConflict: results.append('blocked')
        workers = [threading.Thread(target=click) for _ in range(8)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(results.count('blocked'), 7)


class ControlHttpTests(unittest.TestCase):
    def setUp(self):
        ControlTests.setUp(self)
        self.publish()
        self.server = create_server(self.directory, 0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        with urlopen(self.url + '/api/status', timeout=3) as response:
            self.token = json.load(response)['control_token']

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(timeout=2)

    def publish(self):
        (self.directory / self.source).write_text(json.dumps(self.snapshot))

    def post(self, payload=None, headers=None, expected=202):
        selected = {'Content-Type': 'application/json', 'Origin': self.url, 'X-Gold-Control': self.token}
        selected.update(headers or {})
        request = Request(self.url + '/api/control', data=json.dumps(self.payload if payload is None else payload).encode(), headers=selected)
        try:
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, expected)
                return json.load(response)
        except HTTPError as error:
            self.assertEqual(error.code, expected)
            error.close()

    def test_http_command_queued_then_native_ack_allows_resume(self):
        reply = self.post()
        self.assertEqual(reply['state'], 'queued')
        (self.directory / 'control_TEST_1.csv').unlink()
        self.snapshot['controls']['last_id'] = reply['id']
        self.snapshot['paused'] = True
        self.publish()
        self.assertEqual(self.post({**self.payload, 'action': 'resume'})['action'], 'resume')

    def test_origin_token_and_host_are_required(self):
        for headers in [{'Origin': 'https://external.example'}, {'X-Gold-Control': ''},
                        {'X-Gold-Control': 'é'}, {'Host': 'external.example'}]:
            self.post(headers=headers, expected=403)
        self.assertFalse((self.directory / 'control_TEST_1.csv').exists())

    def test_http_locked_resume_and_stale_feed_refused(self):
        self.snapshot['locked'] = True; self.publish()
        self.post({**self.payload, 'action': 'resume'}, expected=409)
        old = time.time()-20; os.utime(self.directory / self.source, (old, old))
        self.post(expected=409)

    def test_http_invalid_shapes_and_unsupported_entry_refused(self):
        for payload in [[], {}, {**self.payload, 'action': 'buy'}, {**self.payload, 'extra': True}]:
            self.post(payload, expected=400)

    def test_malformed_optional_control_feed_is_error(self):
        self.snapshot['controls'] = []; self.publish()
        with urlopen(self.url + '/api/status', timeout=3) as response:
            self.assertEqual(json.load(response)['state'], 'error')


if __name__ == '__main__':
    unittest.main()
