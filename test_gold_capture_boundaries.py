import unittest
from datetime import datetime, timedelta, timezone
from tools.capture_gold_strategy_data import quote_windows


class CaptureBoundaryTests(unittest.TestCase):
    def test_fractional_requests_are_covered_by_contiguous_whole_seconds(self):
        start = datetime(2026, 10, 20, 9, 59, 7, 271380, tzinfo=timezone.utc)
        end = start+timedelta(hours=24)
        windows = list(quote_windows(start, end))
        self.assertLessEqual(windows[0][0], start)
        self.assertGreaterEqual(windows[-1][1], end)
        for lower, upper in windows:
            self.assertEqual(lower.microsecond, 0)
            self.assertEqual(upper.microsecond, 0)
        for previous, current in zip(windows, windows[1:]):
            self.assertEqual(previous[1], current[0])

    def test_naive_and_reversed_windows_fail(self):
        now = datetime.now(timezone.utc)
        for start, end in ((now, now-timedelta(seconds=1)), (now.replace(tzinfo=None), now)):
            with self.assertRaises(ValueError):
                list(quote_windows(start, end))


if __name__ == '__main__':
    unittest.main()
