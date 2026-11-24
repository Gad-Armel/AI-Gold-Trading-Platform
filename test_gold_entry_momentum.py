import unittest
from unittest.mock import patch
from services.research.gold_entry_momentum import entry_momentum_blocks, scalp_confirmation_blocks


class EntryMomentumTests(unittest.TestCase):
    def setUp(self):
        offset = patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0)
        offset.start()
        self.addCleanup(offset.stop)
        self.decision = dict(allowed=True, direction='BUY')

    def test_live_recorded_pullback_prevents_chasing_high_score(self):
        bars = [dict(time=60, open=4141.37, close=4139.68)]
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=127))

    def test_two_or_three_candles_require_distinct_closed_matching_bodies(self):
        bars = [dict(time=60, open=100, close=101), dict(time=120, open=101, close=102),
                dict(time=180, open=102, close=103)]
        self.assertEqual(entry_momentum_blocks(self.decision, bars, now=240, required_bars=3), [])
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=239, required_bars=3))
        bars[0]['close'] = 99
        self.assertEqual(entry_momentum_blocks(self.decision, bars, now=240, required_bars=2), [])
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=240, required_bars=3))

    def test_doji_duplicate_and_gap_cannot_create_confirmation(self):
        first = dict(time=60, open=100, close=101)
        for bars in ([first, first], [first, dict(time=180, open=101, close=102)],
                     [first, dict(time=120, open=101, close=101)]):
            self.assertTrue(entry_momentum_blocks(self.decision, bars,
                            now=max(row['time'] for row in bars)+60, required_bars=2))

    def test_missing_latest_closed_minute_is_stale(self):
        bars = [dict(time=60, open=100, close=101)]
        self.assertEqual(entry_momentum_blocks(self.decision, bars, now=179.9), [])
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=180))

    def test_invalid_confirmation_count_fails_closed(self):
        for count in (0, 7, 2.0, True):
            self.assertTrue(entry_momentum_blocks(self.decision, [], now=180, required_bars=count))

    def test_three_bearish_bars_confirm_sell_not_buy(self):
        bars = [dict(time=stamp, open=102, close=101) for stamp in (60, 120, 180)]
        self.assertEqual(entry_momentum_blocks(dict(allowed=True, direction='SELL'), bars,
                         now=240, required_bars=3), [])
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=240, required_bars=3))

    def test_recorded_swing_reentry_waits_through_opposing_m1_rally(self):
        decision = dict(allowed=True, direction='SELL', horizon='SWING', evidence=72.53)
        bars = [dict(time=60, open=4121.93, close=4123.54),
                dict(time=120, open=4123.59, close=4125.83)]
        self.assertTrue(entry_momentum_blocks(decision, bars, now=166))
        bars.append(dict(time=180, open=4126, close=4125))
        self.assertEqual(entry_momentum_blocks(decision, bars, now=245), [])

    def test_swing_respects_pending_leading_scalp_wait(self):
        decision = dict(allowed=True, direction='SELL', horizon='SWING')
        blocks = scalp_confirmation_blocks(decision, dict(direction='SELL', waiting_since=100))
        self.assertTrue(blocks)
        self.assertIn('SWING', blocks[0])

    def test_confirmed_candle_and_aligned_flow_allow_entry(self):
        bars = [dict(time=60, open=100, close=101)]
        self.assertEqual(entry_momentum_blocks(self.decision, bars, now=127,
                         flow=dict(available=True, bias='BUY')), [])

    def test_forming_candle_cannot_reverse_completed_candle_read(self):
        bars = [dict(time=60, open=101, close=100), dict(time=120, open=100, close=102)]
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=127))

    def test_opposing_live_flow_requires_wait(self):
        bars = [dict(time=60, open=100, close=101)]
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=127,
                        flow=dict(available=True, bias='SELL')))

    def test_sell_candle_and_stale_data(self):
        bars = [dict(time=60, open=101, close=100)]
        self.decision['direction'] = 'SELL'
        self.assertEqual(entry_momentum_blocks(self.decision, bars, now=127), [])
        self.assertTrue(entry_momentum_blocks(self.decision, bars, now=300))

    def test_same_direction_cannot_bypass_scalp_confirmation(self):
        waiting = dict(direction='BUY', waiting_since=100)
        self.assertTrue(scalp_confirmation_blocks(self.decision, waiting))
        self.decision['direction'] = 'SELL'
        self.assertEqual(scalp_confirmation_blocks(self.decision, waiting), [])

    def test_completed_scalp_confirmation_releases_intraday(self):
        self.assertEqual(scalp_confirmation_blocks(self.decision,
                         dict(direction='BUY', waiting_since=None)), [])

    def test_neutral_during_pending_confirmation_does_not_bypass_wait(self):
        self.assertTrue(scalp_confirmation_blocks(self.decision,
                        dict(direction='WAIT', waiting_since=100)))
        self.assertEqual(scalp_confirmation_blocks(self.decision,
                         dict(direction='WAIT', waiting_since=None)), [])
