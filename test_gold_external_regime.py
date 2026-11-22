import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import numpy as np
import pandas as pd
from services.research.gold_engine_score import EngineScore, EngineScoreConfig
from services.research.gold_multiengine_research import opening_range, multi_features, MultiEngineResearch
from services.research.gold_causal_replay import replay, ReplayConfig
from services.research.gold_simulation_parameters import run_isolated
from types import SimpleNamespace


class ExternalRegimeTests(unittest.TestCase):
    def test_sweep_overrides_do_not_leak_between_worker_jobs(self):
        baseline = dict(target=1.5, nested=[1])
        module = SimpleNamespace(P=dict(target=99., nested=[8]))
        first = run_isolated(module, baseline, dict(target=3.), lambda: dict(module.P))
        second = run_isolated(module, baseline, {}, lambda: dict(module.P))
        self.assertEqual(first['target'], 3.)
        self.assertEqual(second['target'], 1.5)
        self.assertEqual(module.P['target'], 99.)

    def test_parameters_restored_after_failed_simulation(self):
        module = SimpleNamespace(P=dict(target=1.5))
        with self.assertRaises(RuntimeError):
            run_isolated(module, dict(target=1.5), dict(target=3.),
                         lambda: (_ for _ in ()).throw(RuntimeError('failed')))
        self.assertEqual(module.P, dict(target=1.5))

    def rates(self, period, count, start=0):
        stamps = start+np.arange(count)*period
        close = 4000+np.sin(stamps/900)*2+stamps*.0001
        return pd.DataFrame(dict(time=stamps, open=close-.1, high=close+.4, low=close-.4, close=close))

    def test_score_deduplicates_and_retains_large_losses(self):
        score = EngineScore()
        score.observe('loss', -20., now=1.)
        score.observe('loss', -20., now=2.)
        self.assertEqual(score.report(now=2.)['results'], 1)
        self.assertEqual(score.report(now=2.)['net_r_sum'], -20.)
        self.assertFalse(score.report(now=2.)['execution_enabled'])

    def test_pause_expiry_is_review_not_automatic_profit_or_broker_permission(self):
        score = EngineScore(EngineScoreConfig(window=3, minimum_results=2, prior_count=0,
                                              minimum_new_results=2, pause_seconds=10))
        score.observe('one', -1., now=1.)
        score.observe('two', -1., now=2.)
        self.assertEqual(score.report(now=3.)['state'], 'PAPER_PAUSED')
        self.assertEqual(score.report(now=12.)['state'], 'PAPER_REVIEW_DUE')
        score.observe('three', 2., now=13.)
        score.observe('four', 2., now=14.)
        result = score.report(now=14.)
        self.assertEqual(result['state'], 'PAPER_ACTIVE')
        self.assertFalse(result['execution_enabled'])

    def test_bad_scores_or_reverse_time_rejected(self):
        score = EngineScore()
        score.observe('first', 1., now=2.)
        with self.assertRaises(ValueError):
            score.observe('second', 1., now=1.)
        with self.assertRaises(ValueError):
            score.observe('third', float('nan'), now=3.)

    def test_opening_range_requires_full_coverage_and_retries(self):
        start = datetime(2026, 10, 21, 7, tzinfo=timezone.utc).timestamp()
        rates = self.rates(60, 30, start)
        missing = opening_range(rates.iloc[:-1], now=start+1800, zone='Europe/London', hour=8)
        complete = opening_range(rates, now=start+1800, zone='Europe/London', hour=8)
        self.assertFalse(missing['available'])
        self.assertTrue(complete['available'])
        self.assertEqual(complete['start_epoch'], start)

    def test_london_range_uses_local_session_dst(self):
        start = datetime(2026, 12, 1, 8, tzinfo=timezone.utc).timestamp()
        result = opening_range(self.rates(60, 30, start), now=start+1800,
                               zone='Europe/London', hour=8)
        self.assertTrue(result['available'])
        self.assertEqual(result['start_epoch'], start)

    def test_future_htf_prices_cannot_change_past_features(self):
        five = self.rates(300, 340)
        slow = self.rates(900, 150)
        before = multi_features(five, slow, offset=0)
        slow.loc[slow.time >= five.time.max()+300, ['open', 'high', 'low', 'close']] += 1000
        after = multi_features(five, slow, offset=0)
        pd.testing.assert_frame_equal(before, after)

    @patch('services.research.gold_multiengine_research.multi_features', return_value=pd.DataFrame())
    def test_unavailable_data_is_not_cached_for_five_minutes(self, mocked):
        model = MultiEngineResearch()
        for stamp in (300., 301.):
            model.assess([], {}, now=stamp, bid=4000., ask=4000.3)
        self.assertEqual(mocked.call_count, 2)

    def test_failed_entry_does_not_consume_opening_range(self):
        ticks = pd.DataFrame(dict(timestamp=[1., 1.5, 2., 2.5, 3., 3.5],
                                  bid=[100.]*6, ask=[100.2]*6))
        events = [dict(feature_epoch=1., direction='BUY', stop=90., range_id='same'),
                  dict(feature_epoch=2., direction='BUY', stop=99., range_id='same')]
        result = replay(ticks, events, start=0, end=4,
            config=ReplayConfig(maximum_hold=.4, round_trip_cost=.08))
        self.assertEqual(result['rejected']['invalid_risk'], 1)
        self.assertEqual(result['rejected']['duplicate_range'], 0)
        self.assertEqual(result['summary']['trades'], 1)

    def test_atr_trailing_requires_observed_entry_atr(self):
        ticks = pd.DataFrame(dict(timestamp=[1., 1.5], bid=[100.]*2, ask=[100.2]*2))
        result = replay(ticks, [dict(feature_epoch=1., direction='BUY', stop=99.)], start=0, end=2,
                        config=ReplayConfig(trailing_gap_atr=1.5))
        self.assertEqual(result['rejected']['invalid_risk'], 1)


if __name__ == '__main__':
    unittest.main()
