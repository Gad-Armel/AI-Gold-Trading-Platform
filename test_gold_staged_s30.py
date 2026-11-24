import unittest
from unittest.mock import patch

from services.research.gold_staged_m1 import staged_confirmation, execution_confirmation
from services.research.gold_entry_momentum import entry_momentum_blocks
from services.research.gold_s30_shadow import s30_observation


class StagedM1Tests(unittest.TestCase):
    def test_shadow_cannot_change_live_entry_requirements(self):
        plan = dict(required_bars=5, after_epoch=100)
        with patch('config.gold_consensus_settings.SCALP_STAGED_M1_ENABLED', False):
            self.assertEqual(execution_confirmation(plan), dict(required_bars=1, after_epoch=None))
        with patch('config.gold_consensus_settings.SCALP_STAGED_M1_ENABLED', True):
            self.assertEqual(execution_confirmation(plan), plan)
            self.assertEqual(execution_confirmation(plan, scalp=False), dict(required_bars=1, after_epoch=None))

    def test_progressive_counts(self):
        self.assertEqual(staged_confirmation([])['required_bars'], 1)
        self.assertEqual(staged_confirmation([dict(opened_epoch=100)]),
                         dict(required_bars=1, after_epoch=100))
        self.assertEqual(staged_confirmation([dict(opened_epoch=100)]*2),
                         dict(required_bars=1, after_epoch=100))

    @patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0)
    def test_five_is_not_six_and_four_is_not_five(self):
        bars = [dict(time=stamp, open=100, close=101) for stamp in range(60, 301, 60)]
        decision = dict(allowed=True, direction='BUY')
        self.assertEqual(entry_momentum_blocks(decision, bars, now=361, required_bars=5), [])
        self.assertTrue(entry_momentum_blocks(decision, bars, now=361, required_bars=6))
        self.assertTrue(entry_momentum_blocks(decision, bars[1:], now=361, required_bars=5))

    @patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0)
    def test_same_closed_bar_cannot_be_reused_for_an_addition(self):
        bars = [dict(time=stamp, open=100, close=101) for stamp in range(60, 361, 60)]
        decision = dict(allowed=True, direction='BUY')
        self.assertTrue(entry_momentum_blocks(decision, bars, now=421, required_bars=6, after_epoch=420))
        self.assertEqual(entry_momentum_blocks(decision, bars, now=421, required_bars=6, after_epoch=419), [])
        self.assertTrue(entry_momentum_blocks(decision, bars, now=421, required_bars=6, after_epoch=0))


class S30ShadowTests(unittest.TestCase):
    def ticks(self):
        return [dict(timestamp=stamp, bid=100+stamp/100, ask=100.2+stamp/100) for stamp in range(0, 96)]

    def test_uses_three_closed_bars_and_has_no_execution_authority(self):
        result = s30_observation(self.ticks(), now=95)
        self.assertTrue(result['available'])
        self.assertEqual(result['direction'], 'BUY')
        self.assertEqual([bar['time'] for bar in result['bars']], [0, 30, 60])
        self.assertFalse(result['execution_enabled'])

    def test_forming_and_future_ticks_do_not_change_completed_bodies(self):
        ticks = self.ticks()+[dict(timestamp=94.5, bid=50, ask=51), dict(timestamp=96, bid=20, ask=21)]
        self.assertEqual(s30_observation(ticks, now=95)['bars'], s30_observation(self.ticks(), now=95)['bars'])

    def test_gaps_and_stale_ticks_never_manufacture_a_signal(self):
        self.assertFalse(s30_observation(self.ticks()[:80], now=95)['available'])
        self.assertFalse(s30_observation([tick for tick in self.ticks() if not 10 <= tick['timestamp'] <= 20], now=95)['available'])
        self.assertFalse(s30_observation([], now=95)['available'])
