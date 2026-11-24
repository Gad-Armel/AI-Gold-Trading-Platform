import unittest
from unittest.mock import patch
from test_gold_advisory import snapshot
from services.research.gold_advisory import build_gold_advisory
from services.research.gold_main_candle_signal import MainCandleSignal


class MainCandleCacheTests(unittest.TestCase):
    @patch('services.research.gold_advisory.build_verified_market_context', return_value={})
    @patch('services.research.gold_advisory.build_v6_market_structure', return_value={})
    def test_stability_audit_is_read_only_and_checks_cache_parity(self, *_):
        from tools.audit_gold_signal_stability import audit_snapshot
        value = snapshot()
        original = {name: frame.copy() for name, frame in value.candles.items()}
        result = audit_snapshot(value)
        self.assertTrue(all(all(checks.values()) for checks in result['cache_parity'].values()))
        self.assertEqual(set(result['warmup_windows']), {'64', '128', '256'})
        for name, frame in original.items():
            self.assertTrue(frame.equals(value.candles[name]))

    def assert_signals_equal(self, actual, expected):
        for name in ('SCALP', 'INTRADAY', 'SWING'):
            for key in ('bias', 'directional_score', 'levels', 'votes', 'valid_until'):
                self.assertEqual(actual['horizons'][name][key], expected['horizons'][name][key])

    @patch('services.research.gold_advisory.build_verified_market_context', return_value={})
    @patch('services.research.gold_advisory.build_v6_market_structure', return_value={})
    def test_price_and_spread_changes_rebase_exact_original_levels(self, *_):
        value = snapshot()
        cache = MainCandleSignal()
        self.assert_signals_equal(cache.build(value), build_gold_advisory(value))
        value.bid += 2
        value.ask += 2.4
        value.spread += .4
        self.assert_signals_equal(cache.build(value), build_gold_advisory(value))
        self.assertEqual(cache.misses, 1)
        self.assertEqual(cache.hits, 1)

    @patch('services.research.gold_advisory.build_verified_market_context', return_value={})
    @patch('services.research.gold_advisory.build_v6_market_structure', return_value={})
    def test_closed_candle_revision_invalidates_cache(self, *_):
        value = snapshot()
        cache = MainCandleSignal()
        cache.build(value)
        value.candles['M1'].loc[50, 'close'] -= 1
        self.assert_signals_equal(cache.build(value), build_gold_advisory(value))
        self.assertEqual(cache.misses, 2)

    @patch('services.research.gold_advisory.build_verified_market_context', return_value={})
    @patch('services.research.gold_advisory.build_v6_market_structure', return_value={})
    def test_forming_candle_change_does_not_change_closed_signal(self, *_):
        value = snapshot()
        cache = MainCandleSignal()
        cache.build(value)
        value.candles['M1'].loc[99, 'close'] -= 10
        self.assert_signals_equal(cache.build(value), build_gold_advisory(value))
        self.assertEqual(cache.hits, 1)

    @patch('services.research.gold_advisory.build_verified_market_context', return_value={})
    @patch('services.research.gold_advisory.build_v6_market_structure', return_value={})
    def test_unsorted_and_invalid_numeric_inputs_keep_canonical_signal(self, *_):
        value=snapshot()
        cache=MainCandleSignal()
        cache.build(value)
        value.candles['M1']=value.candles['M1'].iloc[::-1].copy()
        self.assert_signals_equal(cache.build(value),build_gold_advisory(value))
        self.assertEqual(cache.hits,1)
        value.candles['M1']['close']=value.candles['M1']['close'].astype(object)
        value.candles['M1'].loc[50,'close']='invalid'
        self.assert_signals_equal(cache.build(value),build_gold_advisory(value))
        self.assertEqual(cache.misses,2)

    @patch('services.research.gold_advisory.build_verified_market_context', return_value={})
    @patch('services.research.gold_advisory.build_v6_market_structure', return_value={})
    def test_duplicate_times_and_completed_bar_rollover_keep_canonical_signal(self, *_):
        value=snapshot()
        cache=MainCandleSignal()
        cache.build(value)
        frame=value.candles['M1']
        frame.loc[50,'time']=frame.loc[49,'time']
        self.assert_signals_equal(cache.build(value),build_gold_advisory(value))
        self.assertEqual(cache.misses,2)
        extra=frame.iloc[[-1]].copy()
        import pandas as pd
        extra['time']+=pd.Timedelta(minutes=1)
        extra['close']+=1
        value.candles['M1']=pd.concat([frame,extra],ignore_index=True)
        self.assert_signals_equal(cache.build(value),build_gold_advisory(value))
        self.assertEqual(cache.misses,3)
