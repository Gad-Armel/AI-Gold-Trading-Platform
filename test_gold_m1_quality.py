import unittest
from services.research.gold_m1_quality import sequence_quality
from services.research.gold_staged_m1 import staged_confirmation
from tools.review_demo_losses import trade_cohort


class SequenceQualityTests(unittest.TestCase):
    def test_cohort_uses_entry_time_and_refuses_host_timezone_assumptions(self):
        rows = [dict(opened_at='2026-10-19T05:00:00Z', closed_at='2026-10-19T06:00:00Z'),
                dict(opened_at='2026-10-19T05:20:00Z', closed_at='2026-10-19T06:00:00Z')]
        self.assertEqual(trade_cohort(rows, '2026-10-19T05:18:47Z'), rows[1:])
        with self.assertRaises(ValueError):
            trade_cohort(rows, '2026-10-19T05:18:47')

    def observe(self, bars, **changes):
        args = dict(now=180, direction='BUY', bid=103, ask=103.2, atr=2, required_bars=3, offset=0)
        args.update(changes)
        return sequence_quality(bars, **args)

    def bars(self):
        return [dict(time=index*60, open=100+index, close=101+index,
                     low=100+index, high=101.5+index) for index in range(3)]

    def test_measures_cost_extension_and_rejection_without_execution_authority(self):
        result = self.observe(self.bars())
        self.assertTrue(result['available'])
        self.assertTrue(result['all_bodies_agree'])
        self.assertAlmostEqual(result['entry_extension_atr'], .1)
        self.assertAlmostEqual(result['spread_to_sequence_move'], .2/3)
        self.assertAlmostEqual(result['last_rejection_fraction'], 1/3)
        self.assertFalse(result['execution_enabled'])

    def test_forming_bar_cannot_change_diagnostics(self):
        bars = self.bars()
        self.assertEqual(self.observe(bars), self.observe(bars+[dict(time=180, open=10, close=1, low=1, high=10)]))

    def test_entry_geometry_is_direction_symmetric(self):
        buy = self.observe(self.bars())
        mirrored = [dict(time=bar['time'], open=200-bar['open'], close=200-bar['close'],
                         high=200-bar['low'], low=200-bar['high']) for bar in self.bars()]
        sell = self.observe(mirrored, direction='SELL', bid=96.8, ask=97)
        for name in ('close_path_efficiency', 'distance_to_sequence_extreme_atr',
                     'remaining_sequence_range_in_spreads', 'last_body_atr'):
            self.assertAlmostEqual(buy[name], sell[name])
        self.assertAlmostEqual(buy['close_path_efficiency'], 1)
        self.assertAlmostEqual(buy['remaining_sequence_range_in_spreads'], 1.5)

    def test_extension_beyond_extreme_is_negative_not_an_entry_authorization(self):
        result = self.observe(self.bars(), bid=104, ask=104.2)
        self.assertLess(result['distance_to_sequence_extreme_atr'], 0)
        self.assertFalse(result['execution_enabled'])
        self.assertIsNone(self.observe(self.bars(), ask=103)['remaining_sequence_range_in_spreads'])

    def test_missing_minutes_and_bad_data_are_not_signals(self):
        for bars in (self.bars()[1:], self.bars()+self.bars()[:1], [dict(time=120)]):
            self.assertFalse(self.observe(bars)['available'])
        self.assertFalse(self.observe(self.bars(), atr=0)['available'])
        self.assertFalse(self.observe(self.bars(), now=240)['available'])

    def test_malformed_opening_times_cannot_crash_or_bypass_staging(self):
        for epoch in (None, float('nan'), -1, True, 'bad'):
            self.assertEqual(staged_confirmation([dict(opened_epoch=100), dict(opened_epoch=epoch)])['after_epoch'], 0)
