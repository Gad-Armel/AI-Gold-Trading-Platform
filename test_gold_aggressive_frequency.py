import unittest
from unittest.mock import patch

from config import gold_consensus_settings as settings
from services.research.gold_horizon_policy import evaluate_entry_timing
from services.research.gold_scalp_guard import reentry_blocks
from run_gold_consensus_bot import _scalp_churn_blocks
from services.research.gold_staged_m1 import staged_confirmation, fast_confirmation
from services.research.gold_continuous_session import post_exit_blocks


class AggressiveFrequencyTests(unittest.TestCase):
    def test_one_bar_m1_setting_never_invalidates_fast_confirmation(self):
        with patch('config.gold_consensus_settings.SCALP_M1_CONFIRMATION_BARS', 1):
            plan = staged_confirmation([dict(opened_epoch=100.)])
            fast = fast_confirmation(plan)
        self.assertEqual(plan['required_bars'], 1)
        self.assertEqual(fast, dict(required_bars=settings.FAST_CONFIRMATION_BARS, after_epoch=100.))
        for count in (3, 5, 6):
            self.assertEqual(fast_confirmation(dict(required_bars=count, after_epoch=None))['required_bars'], count)
        with self.assertRaises(ValueError):
            fast_confirmation(dict(required_bars=True, after_epoch=None))

    def test_profile_preserves_risk_and_signal_guards(self):
        self.assertEqual(settings.MINIMUM_ENTRY_SPACING_SECONDS, 2.)
        self.assertEqual(settings.SCALP_REENTRY_COOLDOWN_SECONDS, 1.)
        self.assertEqual(settings.POST_EXIT_ANALYSIS_SECONDS, 1.)
        self.assertEqual(settings.SCALP_MAX_TRADES_PER_HOUR, 240)
        self.assertEqual(settings.LOT_SIZE, .01)
        self.assertEqual(settings.MAX_TRADE_RISK_USD, 5.)
        self.assertTrue(settings.FAST_RANGE_COST_FILTER_ENABLED)
        self.assertTrue(settings.FAST_MICRO_CONFIRMATION_REQUIRED)
        self.assertEqual(settings.SCALP_LOSS_COOLDOWN_SECONDS, 30.)

    def test_reentry_uses_one_second_and_requires_history(self):
        state = dict(history_available=True, pending_closed=[], last_exit_at=100., last_exit_direction='BUY')
        self.assertTrue(reentry_blocks(state, now=100.5, direction='BUY'))
        self.assertEqual(reentry_blocks(state, now=101., direction='BUY'), [])
        state['history_available'] = False
        self.assertTrue(reentry_blocks(state, now=105., direction='BUY'))

    def test_hourly_ceiling_is_real_not_a_trade_target(self):
        state = dict(entry_times=[100.]*(settings.SCALP_MAX_TRADES_PER_HOUR-1), consecutive_losses=0)
        self.assertEqual(_scalp_churn_blocks(state, now=101., spread=.2, context={}), [])
        state['entry_times'].append(100.)
        self.assertTrue(any('rate limit' in reason for reason in
                            _scalp_churn_blocks(state, now=101., spread=.2, context={})))

    def test_loss_cooldown_still_overrides_fast_reentry(self):
        state = dict(entry_times=[], consecutive_losses=4, last_loss_at=100.)
        self.assertTrue(any('loss cooldown' in reason for reason in
                            _scalp_churn_blocks(state, now=105., spread=.2, context={})))

    def test_global_post_exit_pause_does_not_restore_thirty_second_delay(self):
        states = dict(SCALP=dict(last_exit_at=100.))
        self.assertTrue(post_exit_blocks(states, now=100.5))
        self.assertEqual(post_exit_blocks(states, now=101.), [])

    def test_shorter_confirmation_does_not_authorize_blocked_signal_or_additions(self):
        config = dict(settings.HORIZON_LANES['SCALP'])
        decision = dict(horizon='SCALP', allowed=True, direction='BUY', evidence=90.)
        def evaluate(count, age, elapsed):
            return evaluate_entry_timing(decision, open_position_count=count,
                signal_age_seconds=age, seconds_since_last_entry=elapsed, lane_config=config)
        self.assertFalse(evaluate(0, .9, 20.)[0])
        self.assertTrue(evaluate(0, 1., 20.)[0])
        self.assertFalse(evaluate(1, 1., 2.)[0])
        decision['allowed'] = False
        self.assertFalse(evaluate(0, 10., 20.)[0])


if __name__ == '__main__':
    unittest.main()
