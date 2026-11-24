import unittest
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from services.research.gold_adaptive_exit import market_exit_context
from services.research.gold_exit_context_cache import ExitContextCache


@patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0)
class ExitContextCacheTests(unittest.TestCase):
    def setUp(self):
        times = pd.date_range('2026-10-08T10:00:00Z', periods=65, freq='min')
        closes = [4000+i*.1 for i in range(65)]
        bars = pd.DataFrame(dict(time=times, open=closes, close=closes,
                                high=[v+.2 for v in closes], low=[v-.2 for v in closes]))
        self.snapshot = SimpleNamespace(candles={'M1': bars}, timestamp=times[-1])
        self.now = times[-1]
        self.cache = ExitContextCache()

    def compare(self, now=None):
        now = self.now if now is None else now
        actual = self.cache.get(self.snapshot, 'SCALP', now_utc=now)
        self.assertEqual(actual, market_exit_context(self.snapshot, 'SCALP', now_utc=now))
        return actual

    def test_cached_and_fresh_results_match(self):
        self.assertTrue(self.compare()['available'])
        self.compare()
        self.assertEqual(self.cache.hits, 1)

    def test_forming_price_changes_do_not_recalculate(self):
        self.compare()
        self.snapshot.candles['M1'].loc[64, 'close'] = 9000
        self.compare()
        self.assertEqual(self.cache.hits, 1)

    def test_closed_candle_correction_and_invalid_range_invalidate(self):
        self.compare()
        self.snapshot.candles['M1'].loc[60, 'close'] += .1
        self.compare()
        self.assertEqual(self.cache.misses, 2)
        self.snapshot.candles['M1'].loc[60, 'high'] = 1
        self.assertFalse(self.compare()['available'])

    def test_newly_completed_bar_changes_results(self):
        first = self.compare()
        later = self.compare(self.now+pd.Timedelta(minutes=1))
        self.assertNotEqual(first['bar_id'], later['bar_id'])

    def test_clock_freshness_is_not_cached(self):
        self.assertTrue(self.compare()['available'])
        self.assertFalse(self.compare(self.now+pd.Timedelta(minutes=5))['available'])

    def test_returned_nested_values_cannot_poison_cache(self):
        result = self.compare()
        result['structure_research']['regime'] = 'CORRUPTED'
        self.compare()

    def test_numeric_time_and_duplicates_match_canonical(self):
        frame = self.snapshot.candles['M1']
        frame['time'] = frame.time.astype('int64')//10**9
        self.snapshot.candles['M1'] = pd.concat([frame.iloc[::-1], frame.iloc[[25]]], ignore_index=True)
        self.compare()
        self.compare()


if __name__ == '__main__':
    unittest.main()
