import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from services.utils.atomic_json import atomic_write_json
from tools.monitor_demo_session import read_status, write_observation


class MonitorCaptureTests(unittest.TestCase):
    @patch('tools.monitor_demo_session.time.sleep')
    def test_status_reader_retries_transient_locks_and_partial_json(self, sleep):
        path = Mock()
        path.read_text.side_effect = [PermissionError('locked'), '{', '{"status":"RUNNING"}']
        self.assertEqual(read_status(path), {'status': 'RUNNING'})
        self.assertEqual(path.read_text.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch('tools.monitor_demo_session.time.sleep')
    def test_status_reader_does_not_hide_persistent_failure(self, sleep):
        path = Mock()
        path.read_text.side_effect = PermissionError('locked')
        with self.assertRaises(PermissionError):
            read_status(path)
        self.assertEqual(path.read_text.call_count, 5)
        self.assertEqual(sleep.call_count, 4)

    def test_latest_matches_last_append_and_uses_atomic_writer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            previous = {'observed_at': 'first', 'positions': []}
            current = {'observed_at': 'second', 'positions': [{'ticket': 123}]}
            write_observation(root, previous)
            with patch('tools.monitor_demo_session.atomic_write_json', wraps=atomic_write_json) as writer:
                write_observation(root, current)
                writer.assert_called_once_with(root/'latest.json', current, indent=0)
            rows = [json.loads(line) for line in (root/'observations.jsonl').read_text().splitlines()]
            self.assertEqual(rows, [previous, current])
            self.assertEqual(json.loads((root/'latest.json').read_text()), current)

    def test_append_survives_latest_publication_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            current = {'observed_at': 'recorded', 'positions': []}
            with patch('tools.monitor_demo_session.atomic_write_json', side_effect=OSError('locked')):
                with self.assertRaises(OSError):
                    write_observation(root, current)
            self.assertEqual(json.loads((root/'observations.jsonl').read_text()), current)
