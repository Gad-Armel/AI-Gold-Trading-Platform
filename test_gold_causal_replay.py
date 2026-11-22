import unittest
import pandas as pd
from services.research.gold_causal_replay import replay, ReplayConfig


class CausalReplayTests(unittest.TestCase):
    def ticks(self, stamps, bids, spread=.2):
        return pd.DataFrame(dict(timestamp=stamps, bid=bids, ask=[value+spread for value in bids]))

    def candidate(self, **kwargs):
        return dict(feature_epoch=1., direction='BUY', stop=99., setup='TEST', **kwargs)

    def test_fill_uses_first_quote_after_latency_not_previous_quote(self):
        ticks = self.ticks([1., 1.1, 1.5, 2., 3.], [100., 100., 101., 100., 100.])
        result = replay(ticks, [self.candidate()], start=0, end=4,
            config=ReplayConfig(latency=.35, maximum_hold=.1, round_trip_cost=.1))
        trade = result['trades'][0]
        self.assertEqual(trade['entered_at'], 1.5)
        self.assertAlmostEqual(trade['entry'], 101.2)
        self.assertAlmostEqual(trade['net_price'], -1.3)

    def test_stop_gaps_fill_at_executable_quote_not_stop(self):
        ticks = self.ticks([1., 1.5, 2.], [100., 100., 97.])
        result = replay(ticks, [self.candidate()], start=0, end=3)
        self.assertEqual(result['trades'][0]['exit'], 97.)
        self.assertEqual(result['trades'][0]['reason'], 'BROKER_SL')

    def test_unclosed_position_is_censored_not_invented_profit(self):
        ticks = self.ticks([1., 1.5, 2.], [100., 100., 100.1])
        result = replay(ticks, [self.candidate()], start=0, end=3)
        self.assertEqual(result['summary']['trades'], 0)
        self.assertEqual(result['censored_positions'], 1)

    def test_pre_entry_high_cannot_arm_trailing(self):
        ticks = self.ticks([0., 1., 1.5, 2.], [110., 100., 100., 100.])
        result = replay(ticks, [self.candidate()], start=0, end=3)
        self.assertEqual(result['censored_positions'], 1)

    def test_expired_request_and_gap_entry_rejected(self):
        for stamps in ([1., 8.], [1., 4.5]):
            ticks = self.ticks(stamps, [100., 100.])
            result = replay(ticks, [self.candidate()], start=0, end=9)
            self.assertEqual(result['summary']['trades'], 0)
            self.assertEqual(sum(result['rejected'].values()), 1)

    def test_spread_charged_once_and_costs_once(self):
        ticks = self.ticks([1., 1.5, 2., 2.5], [100., 100., 100., 100.])
        result = replay(ticks, [self.candidate()], start=0, end=3,
            config=ReplayConfig(maximum_hold=.4, round_trip_cost=.08))
        self.assertAlmostEqual(result['trades'][0]['gross_price'], -.2)
        self.assertAlmostEqual(result['trades'][0]['net_price'], -.28)

    def test_invalid_quotes_fail_closed(self):
        with self.assertRaises(ValueError):
            replay(self.ticks([1.], [float('nan')]), [], start=0, end=3)

    def test_invalid_latency_or_cost_does_not_report_zero_trade_success(self):
        for config in (ReplayConfig(latency=float('nan')), ReplayConfig(latency=0),
                       ReplayConfig(round_trip_cost=float('inf')), ReplayConfig(maximum_entry_risk=-1)):
            with self.assertRaises(ValueError):
                replay(self.ticks([1.], [100.]), [], start=0, end=3, config=config)

    def test_sell_pays_ask_at_exit(self):
        ticks = self.ticks([1., 1.5, 2., 2.5], [100., 100., 99., 99.])
        candidate = dict(feature_epoch=1., direction='SELL', stop=102., setup='TEST')
        result = replay(ticks, [candidate], start=0, end=3,
            config=ReplayConfig(maximum_hold=.4, round_trip_cost=.08))
        self.assertAlmostEqual(result['trades'][0]['entry'], 100.)
        self.assertAlmostEqual(result['trades'][0]['exit'], 99.2)
        self.assertAlmostEqual(result['trades'][0]['net_price'], .72)

    def test_repeated_unchanged_quotes_are_not_directional_ticks(self):
        ticks = self.ticks([1., 1.1, 1.2, 1.3], [100., 100., 100., 100.])
        result = replay(ticks, [], start=0, end=2, tick_sequence=True)
        self.assertEqual(result['summary']['trades'], 0)
        self.assertEqual(result['unfilled_requests'], 0)

    def test_duplicate_candidates_cannot_open_overlapping_positions(self):
        ticks = self.ticks([1., 1.5, 2., 2.5], [100., 100., 100., 100.])
        result = replay(ticks, [self.candidate(), self.candidate()], start=0, end=3)
        self.assertEqual(result['censored_positions'], 1)
        self.assertEqual(result['summary']['trades'], 0)


if __name__ == '__main__':
    unittest.main()
