import unittest
from pathlib import Path
from unittest.mock import patch

from services.dashboard.gold_consensus_web import _read_status_json


class StatusRetryTests(unittest.TestCase):
    def test_transient_windows_sharing_error_recovers_without_cache(self):
        with patch.object(Path, 'read_text', side_effect=[PermissionError('sharing'), '{"cycle": 12}']) as read, patch(
                'services.dashboard.gold_consensus_web.time.sleep') as sleep:
            self.assertEqual(_read_status_json(Path('unused')), dict(cycle=12))
            self.assertEqual(read.call_count, 2)
            sleep.assert_called_once_with(.01)

    def test_persistent_error_is_bounded_and_not_disguised_as_fresh(self):
        with patch.object(Path, 'read_text', side_effect=PermissionError('sharing')) as read, patch(
                'services.dashboard.gold_consensus_web.time.sleep') as sleep:
            with self.assertRaises(PermissionError):
                _read_status_json(Path('unused'))
            self.assertEqual(read.call_count, 3)
            self.assertEqual(sleep.call_count, 2)


if __name__ == '__main__':
    unittest.main()
