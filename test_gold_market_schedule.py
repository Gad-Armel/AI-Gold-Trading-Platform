import unittest
from datetime import datetime
from types import SimpleNamespace

from services.research.gold_market_schedule import market_schedule, broker_entry_permission, execution_plan
from services.research.gold_fast_selection import candidate_risk_blocks
from test_gold_consensus_demo_broker import FakeMT5


class MarketScheduleTests(unittest.TestCase):
    def test_strategy_routing_never_promotes_unvalidated_patterns(self):
        plan = execution_plan(dict(setup_observation=dict(regime='TREND_UP', candidates=dict(pullback='BUY'))))
        self.assertEqual(plan['research_candidates'][0]['direction'], 'BUY')
        self.assertTrue(all(not row['execution_enabled'] for row in plan['research_candidates']))
        self.assertIsNone(plan['calibrated_probability'])
    def at(self, stamp):
        return market_schedule(datetime.fromisoformat(stamp))

    def test_summer_winter_and_mismatched_dst_weeks(self):
        winter = self.at('2026-01-12T13:30:00+00:00')
        summer = self.at('2026-07-13T12:30:00+00:00')
        mixed = self.at('2026-10-26T12:30:00+00:00')
        self.assertTrue(winter['london_new_york_overlap'])
        self.assertTrue(summer['london_new_york_overlap'])
        self.assertTrue(mixed['london_new_york_overlap'])
        self.assertIn('+00:00', mixed['local_times']['London'])
        self.assertIn('-04:00', mixed['local_times']['New_York'])

    def test_auction_utc_follows_london_dst(self):
        self.assertIn('10:30:00', self.at('2026-01-12T08:00:00+00:00')['next_regular_lbma_auction_utc'])
        self.assertIn('09:30:00', self.at('2026-07-13T08:00:00+00:00')['next_regular_lbma_auction_utc'])

    def test_weekend_is_context_not_broker_closure(self):
        report = self.at('2026-10-24T12:00:00+00:00')
        self.assertEqual(report['active_centres'], [])
        self.assertFalse(report['execution_authority'])
        self.assertFalse(report['holiday_calendar_verified'])
        self.assertIn('2026-10-26T10:30', report['next_regular_lbma_auction_utc'])

    def test_shanghai_night_crosses_midnight_not_sunday(self):
        self.assertEqual(self.at('2026-10-23T17:00:00+00:00')['sge_regular_session'], 'NIGHT')
        self.assertEqual(self.at('2026-10-25T17:00:00+00:00')['sge_regular_session'], 'BREAK')
        self.assertEqual(self.at('2026-10-26T01:00:00+00:00')['sge_regular_session'], 'DAY')

    def test_rollover_watch_uses_new_york_local_clock(self):
        self.assertTrue(self.at('2026-10-26T21:00:00+00:00')['rollover_watch'])
        self.assertFalse(self.at('2026-10-26T18:00:00+00:00')['rollover_watch'])
        with self.assertRaises(ValueError):
            market_schedule(datetime(2026, 10, 26))

    def test_broker_directional_modes(self):
        for mode, buys, sells in ((0, False, False), (1, True, False), (2, False, True),
                                  (3, False, False), (4, True, True), (99, False, False)):
            self.assertEqual(broker_entry_permission(SimpleNamespace(trade_mode=mode), 'BUY') is None, buys)
            self.assertEqual(broker_entry_permission(SimpleNamespace(trade_mode=mode), 'SELL') is None, sells)
        self.assertIsNotNone(broker_entry_permission(None, 'BUY'))

    def test_stop_budget_selection_does_not_squeeze_structural_stop(self):
        broker = FakeMT5()
        signal = dict(bias='BUY', levels=dict(sl=3990.))
        blocks = candidate_risk_blocks(broker, signal, bid=4000., ask=4000.2)
        self.assertTrue(any('budget' in block for block in blocks))
        self.assertEqual(signal['levels']['sl'], 3990.)
        signal['levels']['sl'] = 3998.
        self.assertEqual(candidate_risk_blocks(broker, signal, bid=4000., ask=4000.2), [])


if __name__ == '__main__':
    unittest.main()
