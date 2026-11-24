import unittest
from services.research.gold_entry_episode import EntryEpisodeGuard


class EntryEpisodeTests(unittest.TestCase):
    def test_confirmed_fill_blocks_unchanged_setup_even_after_exit(self):
        guard = EntryEpisodeGuard()
        self.assertTrue(guard.allowed('S5:1000:BREAKOUT:4000.50', 'BUY'))
        guard.record_fill('S5:1000:BREAKOUT:4000.50', 'BUY', deal_id=123, confirmed=True)
        self.assertFalse(guard.allowed('S5:1000:BREAKOUT:4000.50', 'BUY'))
        self.assertTrue(guard.blocks('S5:1000:BREAKOUT:4000.50', 'BUY'))
        # No flat-position input or passage-of-time input can accidentally rearm.
        self.assertFalse(guard.allowed('S5:1000:BREAKOUT:4000.50', 'BUY'))

    def test_new_market_event_rearms_and_direction_is_separate(self):
        guard = EntryEpisodeGuard()
        guard.record_fill('S5:1000:RETEST:4000.50', 'BUY', deal_id=123, confirmed=True)
        self.assertTrue(guard.allowed('S5:1005:RETEST:4000.50', 'BUY'))
        self.assertTrue(guard.allowed('S5:1000:RETEST:4000.50', 'SELL'))

    def test_order_acceptance_or_invalid_deal_never_consumes_setup(self):
        guard = EntryEpisodeGuard()
        for confirmed, deal in ((False, 123), (None, 123), (True, 0), (True, True)):
            with self.assertRaises(ValueError):
                guard.record_fill('event', 'BUY', deal_id=deal, confirmed=confirmed)
            self.assertTrue(guard.allowed('event', 'BUY'))

    def test_bounded_history_and_repeated_fill_is_idempotent(self):
        guard = EntryEpisodeGuard(maximum=2)
        for setup, deal in (('a', 1), ('b', 2), ('a', 1), ('c', 3)):
            guard.record_fill(setup, 'BUY', deal_id=deal, confirmed=True)
        self.assertEqual(guard.snapshot()['filled_setup_count'], 2)
        self.assertTrue(guard.allowed('a', 'BUY'))  # oldest event evicted
        self.assertFalse(guard.allowed('b', 'BUY'))
        self.assertFalse(guard.allowed('c', 'BUY'))
        large = EntryEpisodeGuard()
        for i in range(220):
            large.record_fill(f'S5:{i}:BREAKOUT', 'BUY', deal_id=i+1, confirmed=True)
        self.assertEqual(large.snapshot()['filled_setup_count'], 200)

    def test_invalid_identity_fails_closed(self):
        guard = EntryEpisodeGuard()
        for setup, direction in (('', 'BUY'), (None, 'BUY'), ('event', 'WAIT'), ('x'*257, 'SELL')):
            self.assertFalse(guard.allowed(setup, direction))
        for maximum in (0, 201, True, 2.5):
            with self.assertRaises(ValueError):
                EntryEpisodeGuard(maximum=maximum)

    def test_snapshot_roundtrip_keeps_fill_identity_and_eviction_order(self):
        guard = EntryEpisodeGuard(maximum=2)
        guard.record_fill('first', 'BUY', deal_id=12, confirmed=True)
        guard.record_fill('second', 'SELL', deal_id=13, confirmed=True)
        restored = EntryEpisodeGuard()
        restored.restore(guard.snapshot())
        self.assertEqual(restored.snapshot(), guard.snapshot())
        self.assertFalse(restored.allowed('first', 'BUY'))
        restored.record_fill('third', 'BUY', deal_id=14, confirmed=True)
        self.assertTrue(restored.allowed('first', 'BUY'))
        self.assertFalse(restored.allowed('second', 'SELL'))

    def test_invalid_snapshot_never_partially_changes_existing_state(self):
        from copy import deepcopy
        guard = EntryEpisodeGuard()
        guard.record_fill('kept', 'BUY', deal_id=12, confirmed=True)
        good = guard.snapshot()
        bad_snapshots = [None, {}, dict(good, maximum=201), dict(good, maximum=True),
                         dict(good, filled_setup_count=0), dict(good, retained=()),
                         dict(good, retained=[good['retained'][0]]*2, filled_setup_count=2)]
        for field, value in (('setup_id', ''), ('direction', 'WAIT'), ('deal_id', True),
                             ('deal_id', 0), ('deal_id', 1.5)):
            altered = deepcopy(good)
            altered['retained'][0][field] = value
            bad_snapshots.append(altered)
        extra = deepcopy(good)
        extra['retained'][0]['unknown'] = 'discarded'
        bad_snapshots.append(extra)
        for bad in bad_snapshots:
            with self.assertRaises(ValueError):
                guard.restore(bad)
            self.assertEqual(guard.snapshot(), good)


if __name__ == '__main__':
    unittest.main()
