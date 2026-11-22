import unittest

from tools.research_m1_confirmation import compare, preceding_bars


class M1ConfirmationResearchTests(unittest.TestCase):
    def test_future_and_forming_bars_are_not_used(self):
        bars = [dict(time=stamp, open=100, close=101) for stamp in (0, 60, 120, 180, 240)]
        selected, opened = preceding_bars(bars, '1970-01-01T00:03:30Z', 0)
        self.assertEqual([row['time'] for row in selected], [0, 60, 120])
        self.assertEqual(opened, 210)

    def test_subset_preserves_actual_net_pnl(self):
        bars = [dict(time=stamp, open=100, close=close) for stamp, close in ((0, 99), (60, 101), (120, 101))]
        trade = dict(opened_at='1970-01-01T00:03:00Z', direction='BUY', profit=-1.25)
        result = compare(bars, [trade], 0)
        stats = result['segments']['all']['by_required_bars']
        self.assertEqual(stats['2']['net'], -1.25)
        self.assertEqual(stats['3']['trades'], 0)

    def test_gap_and_duplicates_cannot_pass(self):
        bars = [dict(time=stamp, open=100, close=101) for stamp in (0, 120, 180)]
        trade = dict(opened_at='1970-01-01T00:04:00Z', direction='BUY', profit=1)
        self.assertEqual(compare(bars, [trade], 0)['comparable_trades'], 0)
        with self.assertRaises(ValueError):
            compare(bars+bars[:1], [trade], 0)

    def test_empty_cohort_is_explicit(self):
        result = compare([], [], 0)
        self.assertEqual(result['comparable_trades'], 0)
        self.assertIsNone(result['later_segment_starts'])

    def test_naive_trade_timestamp_is_not_interpreted_in_host_timezone(self):
        with self.assertRaises(ValueError):
            preceding_bars([], '2026-10-19T00:00:00', 0)

    def test_broker_offset_does_not_shift_confirmation_window(self):
        bars = [dict(time=10800+stamp, open=100, close=101) for stamp in (0, 60, 120)]
        trade = dict(opened_at='1970-01-01T00:03:00Z', direction='BUY', profit=1)
        self.assertEqual(compare(bars, [trade], 10800)['segments']['all']['by_required_bars']['3']['trades'], 1)
