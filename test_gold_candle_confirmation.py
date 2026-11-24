import unittest
from unittest.mock import patch
from services.research.gold_candle_confirmation import confirm_next_move


class CandleConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.state = {}

    def signal(self, score, now, bars=None, direction='BUY'):
        return confirm_next_move({'evidence': score, 'dominant_bias': direction},
                                 self.state, bars, now=now)

    def weaken(self):
        self.assertEqual(self.signal(100, 500), [])
        self.assertTrue(self.signal(76, 600))

    def test_strong_signal_does_not_wait(self):
        self.assertEqual(self.signal(100, 500), [])

    def test_scalp_recovers_after_one_new_completed_m1(self):
        self.weaken()
        decision = {'evidence': 76, 'dominant_bias': 'BUY'}
        bars = [{'time': 600, 'open': 100, 'close': 101}]
        self.assertTrue(confirm_next_move(decision, self.state, bars, now=659,
                                         frame='M1', required_bars=1))
        self.assertEqual(confirm_next_move(decision, self.state, bars, now=660,
                                          frame='M1', required_bars=1), [])

    def test_scalp_rejects_opposing_or_stale_m1(self):
        self.weaken()
        decision = {'evidence': 76, 'dominant_bias': 'BUY'}
        for close, now in [(99, 660), (101, 720)]:
            bars = [{'time': 600, 'open': 100, 'close': close}]
            self.assertTrue(confirm_next_move(decision, self.state, bars, now=now,
                                             frame='M1', required_bars=1))

    def test_scalp_trial_waits_for_three_post_trigger_completed_m1(self):
        self.weaken()
        decision = {'evidence': 76, 'dominant_bias': 'BUY'}
        bars = [{'time': stamp, 'open': 100, 'close': 101} for stamp in (600, 660, 720)]
        self.assertTrue(confirm_next_move(decision, self.state, bars, now=779,
                                         frame='M1', required_bars=3))
        self.assertEqual(confirm_next_move(decision, self.state, bars, now=780,
                                          frame='M1', required_bars=3), [])

    def test_drop_waits_until_two_new_completed_candles(self):
        self.weaken()
        bars = [{'time': 600, 'open': 100, 'close': 101},
                {'time': 900, 'open': 101, 'close': 102}]
        self.assertTrue(self.signal(76, 1199, bars))
        self.assertEqual(self.signal(76, 1200, bars), [])
        self.assertEqual(self.signal(76, 1201, bars), [])

    def test_repeated_candle_does_not_count_twice(self):
        self.weaken()
        bar = {'time': 600, 'open': 100, 'close': 101}
        self.assertTrue(self.signal(76, 1200, [bar, bar]))

    def test_opposing_and_nonconsecutive_candles_do_not_confirm(self):
        self.weaken()
        bars = [{'time': 600, 'open': 100, 'close': 101},
                {'time': 900, 'open': 101, 'close': 100}]
        self.assertTrue(self.signal(76, 1200, bars))
        bars[1] = {'time': 1200, 'open': 101, 'close': 102}
        self.assertTrue(self.signal(76, 1500, bars))

    def test_strong_direction_change_confirms_new_sell_direction(self):
        self.signal(100, 500)
        self.assertTrue(self.signal(90, 600, direction='SELL'))
        bars = [{'time': 600, 'open': 102, 'close': 101},
                {'time': 900, 'open': 101, 'close': 100}]
        self.assertEqual(self.signal(90, 1200, bars, direction='SELL'), [])

    def test_preexisting_candles_do_not_confirm_next_move(self):
        self.weaken()
        bars = [{'time': 0, 'open': 100, 'close': 101},
                {'time': 300, 'open': 101, 'close': 102}]
        self.assertTrue(self.signal(76, 600, bars))


if __name__ == '__main__':
    unittest.main()
