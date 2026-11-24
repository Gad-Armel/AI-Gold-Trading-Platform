import unittest
from services.research.gold_s30_execution import confirmed_fast_reversal, position_exit_signal


class FastReversalTests(unittest.TestCase):
    def test_new_position_resets_previously_confirmed_reversal(self):
        state = {}
        self.check(state, 10, position_ids=[1])
        self.assertTrue(self.check(state, 11, position_ids=[1])['close'])
        self.assertFalse(self.check(state, 12, position_ids=[2])['close'])
        self.assertTrue(self.check(state, 13, position_ids=[2])['close'])

    def test_distinct_quote_requirement_does_not_count_cached_or_older_quotes(self):
        state = {}
        args = dict(position_ids=[1], require_fresh_quotes=True)
        self.assertFalse(self.check(state, 10, quote_time=100., **args)['close'])
        self.assertFalse(self.check(state, 11, quote_time=100., **args)['close'])
        self.assertFalse(self.check(state, 12, quote_time=99., **args)['close'])
        self.assertTrue(self.check(state, 13, quote_time=101., **args)['close'])
        self.assertEqual(state['quote_observations'], 2)

    def test_fresh_mode_needs_two_observations_even_with_zero_duration(self):
        state = {}
        args = dict(position_ids=[1], require_fresh_quotes=True, minimum_seconds=0.)
        self.assertFalse(self.check(state, 10, quote_time=100., **args)['close'])
        self.assertTrue(self.check(state, 10.1, quote_time=100.1, **args)['close'])

    def test_invalid_quote_clears_reversal_evidence(self):
        for quote in (None, float('nan'), float('inf'), True, -1.):
            state = {}
            args = dict(position_ids=[1], require_fresh_quotes=True)
            self.check(state, 10, quote_time=100., **args)
            self.assertFalse(self.check(state, 11, quote_time=quote, **args)['close'])
            self.assertEqual(state, {})
            self.assertFalse(self.check(state, 12, quote_time=102., **args)['close'])

    def test_position_binding_is_order_independent_and_invalid_binding_clears(self):
        state = {}
        self.check(state, 10, position_ids=[2, 1])
        self.assertTrue(self.check(state, 11, position_ids=[1, 2])['close'])
        self.assertFalse(self.check(state, 12, position_ids=[])['close'])
        self.assertEqual(state, {})

    def check(self, state, now, **kwargs):
        args = dict(entry_blocks=[], market_available=True)
        args.update(kwargs)
        return confirmed_fast_reversal(dict(direction='SELL', allowed=True, entry_mode='S5_PRIMARY'),
                                       'BUY', state, now=now, **args)

    def test_opposite_setup_must_persist(self):
        state = {}
        self.assertFalse(self.check(state, 10)['close'])
        self.assertTrue(self.check(state, 11)['close'])

    def test_any_failed_confirmation_resets_persistence(self):
        for failure in (dict(entry_blocks=['cost']), dict(market_available=False)):
            state = {}
            self.check(state, 10)
            self.assertFalse(self.check(state, 11, **failure)['close'])
            self.assertFalse(self.check(state, 12)['close'])

    def test_neutral_and_same_direction_never_reverse(self):
        for direction in ('WAIT', 'BUY'):
            result = confirmed_fast_reversal(dict(direction=direction, allowed=True), 'BUY', {},
                now=10, entry_blocks=[], market_available=True)
            self.assertFalse(result['close'])

    def test_unconfirmed_opposite_cannot_trigger_adaptive_reversal(self):
        original = dict(direction='SELL', allowed=True, entry_mode='S5_PRIMARY')
        signal = position_exit_signal(original, confirmed_reversal=False)
        self.assertFalse(signal['allowed'])
        self.assertTrue(signal['entry_confirmation_only'])
        self.assertTrue(original['allowed'])

    def test_confirmed_opposite_remains_directional(self):
        signal = position_exit_signal(dict(direction='SELL', allowed=True), confirmed_reversal=True)
        self.assertTrue(signal['allowed'])


if __name__ == '__main__':
    unittest.main()
