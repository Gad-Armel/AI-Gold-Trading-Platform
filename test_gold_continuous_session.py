import unittest
from unittest.mock import patch
from services.research.gold_continuous_session import session_loss_stop, post_exit_blocks


class ContinuousSessionTests(unittest.TestCase):
    def test_losses_do_not_shutdown_bot(self):
        self.assertFalse(session_loss_stop({'available': True, 'total': -100}))

    def test_optional_loss_stop_remains_testable(self):
        with patch('config.gold_consensus_settings.SESSION_LOSS_STOP_ENABLED', True):
            self.assertTrue(session_loss_stop({'available': True, 'total': -5.16}))

    def test_pause_expires_after_thirty_seconds(self):
        states = {'SCALP': {'last_exit_at': 100}, 'INTRADAY': {'last_exit_at': 110}}
        self.assertTrue(post_exit_blocks(states, now=139.9))
        self.assertEqual(post_exit_blocks(states, now=140), [])

    def test_initial_start_does_not_pause(self):
        self.assertEqual(post_exit_blocks({'SCALP': {}}, now=100), [])
