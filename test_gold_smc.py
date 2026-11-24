import copy
import math
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from services.research.gold_smc import (
    SmcConfig, SmcStrategy, _flips, _orderblocks, _sweeps,
    apply_smc_policy, candidate_cost, completed_frame, structure,
)


def history(count=40, seconds=60, end=None):
    start = 0 if end is None else end-count*seconds
    rows = []
    for index in range(count):
        center = 100+2*math.sin(index*math.pi/4)
        rows.append(dict(time=start+index*seconds, available=start+(index+1)*seconds,
                         open=center+.1, close=center-.1, high=center+.5,
                         low=center-.5, tick_volume=100))
    return rows


def append_bar(rows, *, opened, close, low, high, volume=300, seconds=60):
    stamp = rows[-1]['time']+seconds
    rows.append(dict(time=stamp, available=stamp+seconds, open=opened, close=close,
                     low=low, high=high, tick_volume=volume))


class SmcStructureTests(unittest.TestCase):
    def setUp(self):
        self.config = SmcConfig()

    def test_pivot_exists_only_after_right_side_confirmation(self):
        rows = history()
        complete = structure(pd.DataFrame(rows), self.config)
        for swing in complete['swings']:
            prefix = [row for row in rows if row['available'] < swing['known_at']]
            prior = structure(pd.DataFrame(prefix), self.config)
            self.assertFalse(any(item['anchor_at'] == swing['anchor_at'] and item['kind'] == swing['kind']
                                 for item in prior['swings']))
            self.assertEqual(swing['known_at']-swing['anchor_at'], 120)

    def test_displacement_break_is_known_at_close_not_origin(self):
        rows = history()
        append_bar(rows, opened=100, close=104, low=99, high=104.5)
        result = structure(pd.DataFrame(rows), self.config)
        event = result['breaks'][-1]
        self.assertEqual(event['direction'], 1)
        self.assertTrue(event['displacement'])
        self.assertEqual(event['known_at'], rows[-1]['available'])
        self.assertLess(event['source_swing']['known_at'], event['known_at'])

    def test_sweep_then_confirmed_micro_break(self):
        rows = history()
        append_bar(rows, opened=98, close=99, low=96.5, high=100)
        self.assertEqual(_sweeps(structure(pd.DataFrame(rows), self.config), self.config), [])
        append_bar(rows, opened=99, close=104, low=98.5, high=104.5)
        candidates = _sweeps(structure(pd.DataFrame(rows), self.config), self.config)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['model'], 'SWEEP_RECLAIM')
        self.assertLess(candidates[0]['stop_loss'], 96.5)
        self.assertFalse(candidates[0]['execution_enabled'])

    def test_sweep_without_reclaim_or_volume_is_not_a_signal(self):
        for reclaim, volume in ((97, 300), (99, 10)):
            rows = history()
            append_bar(rows, opened=98, close=reclaim, low=96.5, high=100)
            append_bar(rows, opened=99, close=104, low=98.5, high=104.5, volume=volume)
            self.assertEqual(_sweeps(structure(pd.DataFrame(rows), self.config), self.config), [])

    def test_short_sweep_is_a_mirror_not_a_hedging_order(self):
        rows = history()
        append_bar(rows, opened=98, close=99, low=96.5, high=100)
        append_bar(rows, opened=99, close=104, low=98.5, high=104.5)
        mirrored = [dict(row, open=200-row['open'], close=200-row['close'],
                         low=200-row['high'], high=200-row['low']) for row in rows]
        long = _sweeps(structure(pd.DataFrame(rows), self.config), self.config)[0]
        short = _sweeps(structure(pd.DataFrame(mirrored), self.config), self.config)[0]
        self.assertEqual(short['direction'], 'SELL')
        self.assertAlmostEqual(short['stop_loss'], 200-long['stop_loss'])

    def test_flip_retest_fires_once_and_expires(self):
        rows = history()
        append_bar(rows, opened=100, close=104, low=99, high=104.5)
        self.assertEqual(_flips(structure(pd.DataFrame(rows), self.config), self.config), [])
        append_bar(rows, opened=102.6, close=103.4, low=102.4, high=104)
        candidates = _flips(structure(pd.DataFrame(rows), self.config), self.config)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['model'], 'SR_FLIP_RETEST')
        append_bar(rows, opened=102.6, close=103.4, low=102.4, high=104)
        self.assertEqual(_flips(structure(pd.DataFrame(rows), self.config), self.config), [])

    def test_failed_flip_and_late_retest_do_not_trigger(self):
        for delay, closed in ((0, 102), (3, 103.4)):
            rows = history()
            append_bar(rows, opened=100, close=104, low=99, high=104.5)
            for _ in range(delay):
                append_bar(rows, opened=104, close=104.1, low=103.8, high=104.5, volume=100)
            append_bar(rows, opened=102.6, close=closed, low=101.9, high=104)
            self.assertEqual(_flips(structure(pd.DataFrame(rows), self.config), self.config), [])

    def test_orderblock_first_retest_and_no_backdated_entry(self):
        rows = history(seconds=300)
        append_bar(rows, opened=100, close=104, low=99, high=104.5, seconds=300)
        five = structure(pd.DataFrame(rows), self.config)
        known = five['breaks'][-1]['known_at']
        one = dict(rows=[dict(available=known-60, low=103, high=104, close=104),
                         dict(available=known+60, low=103, high=104, close=104),
                         dict(available=known+120, open=98.5, close=99.8, low=98.2,
                              high=100, atr_before=2, rvol=2)])
        result = _orderblocks(one, five, self.config)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['model'], 'OB_CONTINUATION')
        self.assertGreater(result[0]['known_at'], result[0]['anchor_at'])
        one['rows'][1].update(low=98.2, high=99)
        self.assertEqual(_orderblocks(one, five, self.config), [])

    def test_long_and_short_rules_are_mirrors(self):
        rows = history()
        append_bar(rows, opened=100, close=104, low=99, high=104.5)
        append_bar(rows, opened=102.6, close=103.4, low=102.4, high=104)
        long = _flips(structure(pd.DataFrame(rows), self.config), self.config)[0]
        mirrored = [dict(row, open=200-row['open'], close=200-row['close'],
                         low=200-row['high'], high=200-row['low']) for row in rows]
        short = _flips(structure(pd.DataFrame(mirrored), self.config), self.config)[0]
        self.assertEqual(short['direction'], 'SELL')
        self.assertAlmostEqual(short['stop_loss'], 200-long['stop_loss'])


class SmcIntegrationTests(unittest.TestCase):
    def frames(self):
        return {name: pd.DataFrame(history(60, seconds, end=216000))
                for name, seconds in (('M1', 60), ('M5', 300), ('M15', 900), ('H1', 3600))}

    def test_cache_ignores_forming_data_and_invalidates_volume_revision(self):
        frames = self.frames()
        engine = SmcStrategy()
        arguments = dict(now=216000, bid=100, ask=100.1, offset=0)
        report = engine.assess(frames, **arguments)
        self.assertTrue(report['available'])
        extra = pd.DataFrame([dict(time=216000, open=1, close=1, low=1, high=1, tick_volume=100)])
        frames['M1'] = pd.concat([frames['M1'], extra], ignore_index=True)
        self.assertEqual(engine.assess(frames, **arguments), report)
        frames['M1'].loc[10, 'tick_volume'] += 1
        self.assertEqual(engine.assess(frames, **arguments)['builds'], 2)

    def test_prior_features_do_not_receive_future_data(self):
        frames = self.frames()
        engine = SmcStrategy()
        arguments = dict(now=216000, bid=100, ask=100.1, offset=0)
        expected = engine.assess(frames, **arguments)
        for name, frame in frames.items():
            frames[name] = pd.concat([frame, pd.DataFrame([dict(time=216000, open=-1, close=-1,
                low=-1, high=-1, tick_volume=-1)])], ignore_index=True)
        self.assertEqual(engine.assess(frames, **arguments), expected)

    def test_gaps_duplicates_stale_missing_volume_and_nan_fail_closed(self):
        for failure in ('gap', 'duplicate', 'volume', 'nan', 'stale'):
            frames = self.frames()
            if failure == 'gap':
                frames['M5'] = frames['M5'].drop(index=20)
            elif failure == 'duplicate':
                frames['M1'] = pd.concat([frames['M1'], frames['M1'].iloc[-1:]])
            elif failure == 'volume':
                frames['M1'] = frames['M1'].drop(columns='tick_volume')
            elif failure == 'nan':
                frames['M1'].loc[20, 'tick_volume'] = float('nan')
            report = SmcStrategy().assess(frames, now=216370 if failure == 'stale' else 216000,
                                          bid=100, ask=100.1, offset=0)
            self.assertFalse(report['available'], failure)
            self.assertFalse(report['execution_enabled'])

    def test_bad_configuration_is_rejected(self):
        for arguments in (dict(swing_wing=True), dict(commission_price=-1),
                          dict(slippage_price=float('nan')), dict(minimum_rvol=0)):
            with self.assertRaises(ValueError):
                SmcConfig(**arguments)

    def test_end_to_end_flip_can_confirm_but_never_creates_permission(self):
        frames = self.frames()
        rows = history(40, end=216000)
        append_bar(rows, opened=100, close=104, low=99, high=104.5)
        append_bar(rows, opened=102.6, close=103.4, low=102.4, high=104)
        frames['M1'] = pd.DataFrame(rows)
        frames['H1'][['open', 'high', 'low', 'close']] += 10
        engine = SmcStrategy(SmcConfig(commission_price=.02, slippage_price=.03))
        report = engine.assess(frames, now=216120, bid=103.4, ask=103.5, offset=0)
        self.assertTrue(report['available'])
        matching = [candidate for candidate in report['candidates'] if candidate['eligible']]
        self.assertEqual(matching[0]['model'], 'SR_FLIP_RETEST')
        decision = dict(allowed=True, direction='BUY', stop_loss=100)
        apply_smc_policy(decision, report, policy='filter', now=216120)
        self.assertTrue(decision['allowed'])
        self.assertEqual(decision['stop_loss'], 100)
        blocked = dict(allowed=False, direction='BUY')
        apply_smc_policy(blocked, report, policy='filter', now=216120)
        self.assertFalse(blocked['allowed'])
        frames['M5'].loc[frames['M5'].index[-1], ['open', 'high', 'low', 'close', 'tick_volume']] = [100, 100.5, 95.5, 96, 300]
        opposed = engine.assess(frames, now=216120, bid=103.4, ask=103.5, offset=0)
        self.assertFalse(any(candidate['eligible'] for candidate in opposed['candidates']))

    def test_read_only_audit_replays_the_identical_core(self):
        from tools.audit_gold_smc import evaluate
        config = SmcConfig()
        capture = dict(symbol='XAUUSD', candles={name: frame.to_dict('records') for name, frame in self.frames().items()},
                       now=216000, bid=100, ask=100.1, offset=0)
        report = evaluate(capture, config)
        expected = SmcStrategy(config).assess(capture['candles'], now=216000, bid=100, ask=100.1, offset=0)
        self.assertEqual(report, expected)
        self.assertEqual(asdict(config)['commission_price'], None)
        with self.assertRaises(ValueError):
            evaluate(dict(capture, symbol='EURUSD'), config)

    def test_demo_capture_rejects_live_account_without_any_order_call(self):
        from tools.audit_gold_smc import capture_demo
        fake = Mock()
        fake.initialize.return_value = True
        fake.ACCOUNT_TRADE_MODE_DEMO = 0
        fake.account_info.return_value = SimpleNamespace(trade_mode=2)
        with patch.dict('sys.modules', {'MetaTrader5': fake}):
            with self.assertRaises(ValueError):
                capture_demo()
        fake.order_send.assert_not_called()
        fake.shutdown.assert_called_once()

    def test_filter_startup_refuses_unknown_costs_before_acquiring_runtime_lock(self):
        import run_gold_consensus_bot as main_bot
        arguments = SimpleNamespace(mode='shadow', paper_trading=False, learned_policy='off',
                                    exit_policy='adaptive', smc_policy='filter')
        with patch.object(main_bot, '_arguments', return_value=arguments), \
                patch.object(main_bot.settings, 'SCALP_SMC_CONFIG', {}), \
                patch.object(main_bot.ScalpingInstanceLock, 'acquire') as acquire:
            with self.assertRaisesRegex(ValueError, 'verified round-trip'):
                main_bot.main()
            acquire.assert_not_called()

    def test_main_applies_filter_only_after_exit_evaluation(self):
        import ast
        source = (Path(__file__).parent/'run_gold_consensus_bot.py').read_text(encoding='utf-8')
        calls = {name: [] for name in ('apply_smc_policy', 'evaluate_adaptive_exit', 'assess_position_conscience')}
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in calls:
                calls[node.func.id].append(node.lineno)
        self.assertEqual(len(calls['apply_smc_policy']), 1)
        self.assertGreater(calls['apply_smc_policy'][0], max(calls['evaluate_adaptive_exit']+calls['assess_position_conscience']))

    def test_invalid_filter_timestamps_fail_closed(self):
        for value in (None, float('nan'), 'invalid'):
            decision = dict(allowed=True, direction='BUY')
            apply_smc_policy(decision, dict(available=True, feature_epoch=value, valid_until=160,
                candidates=[dict(id='example', direction='BUY', eligible=True)]), policy='filter', now=120)
            self.assertFalse(decision['allowed'])

    def test_policy_can_only_veto_not_authorize_or_change_direction_and_stops(self):
        decision = dict(allowed=True, direction='BUY', stop_loss=98, volume=.01)
        report = dict(available=True, feature_epoch=100, valid_until=160, candidates=[
            dict(id='example', direction='BUY', eligible=True)])
        original = copy.deepcopy(decision)
        apply_smc_policy(decision, report, policy='observe', now=120)
        self.assertEqual({key: decision[key] for key in original}, original)
        blocked = dict(original, allowed=False)
        apply_smc_policy(blocked, report, policy='filter', now=120)
        self.assertFalse(blocked['allowed'])
        apply_smc_policy(decision, report, policy='filter', now=160)
        self.assertFalse(decision['allowed'])
        self.assertEqual(decision['stop_loss'], 98)
        self.assertEqual(decision['volume'], .01)
        report['candidates'][0]['direction'] = 'SELL'
        opposed = dict(original)
        apply_smc_policy(opposed, report, policy='filter', now=120)
        self.assertFalse(opposed['allowed'])

    def test_costs_are_not_invented_and_geometry_is_not_ev(self):
        candidate = dict(sign=1, stop_loss=98, known_at=100)
        structures = dict(M1=dict(swings=[dict(kind='HIGH', price=103, known_at=80)]))
        unknown = candidate_cost(candidate, bid=100, ask=100.2, structures=structures, config=SmcConfig())
        self.assertIsNone(unknown['expected_value'])
        self.assertTrue(unknown['blocks'])
        known = candidate_cost(candidate, bid=100, ask=100.2, structures=structures,
                               config=SmcConfig(commission_price=.05, slippage_price=.05))
        self.assertEqual(known['blocks'], [])
        self.assertAlmostEqual(known['friction_price'], .3)
        self.assertIsNone(known['calibrated_probability'])
        near = candidate_cost(dict(sign=1, stop_loss=100, known_at=100), bid=100, ask=100.2,
                              structures=structures, config=SmcConfig())
        self.assertTrue(any('too close' in block for block in near['blocks']))

    def test_opposing_levels_expire_instead_of_becoming_permanent_targets(self):
        result = candidate_cost(dict(sign=1, stop_loss=98, known_at=100000), bid=100, ask=100.2,
            structures=dict(M1=dict(swings=[dict(kind='HIGH', price=103, known_at=80)])),
            config=SmcConfig(commission_price=0, slippage_price=0))
        self.assertIsNone(result['opposing_level'])
        self.assertTrue(result['blocks'])
