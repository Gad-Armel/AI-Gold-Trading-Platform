from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from models.scalping_state import ScalpingSnapshotState
from services.research.gold_s30_execution import refresh_fast_snapshot


class FastRefreshTests(unittest.TestCase):
    def snapshot(self):
        return ScalpingSnapshotState(symbol='XAUUSD', timestamp=datetime.now(timezone.utc),
            bid=4000., ask=4000.2, spread=.2, mid=4000.1, session='test', active_sessions=[],
            candles={'M1': 'unchanged'}, tick_time_msc=1000)

    def test_history_and_quote_are_refreshed_without_mutating_analysis(self):
        before = self.snapshot()
        history = Mock()
        history.refresh.return_value = ([], dict(available=True))
        mt5 = Mock()
        mt5.symbol_info_tick.return_value = SimpleNamespace(bid=4001., ask=4001.3, time_msc=2000)
        after, health = refresh_fast_snapshot(mt5, history, before)
        self.assertTrue(health['available'])
        self.assertEqual(after.bid, 4001.)
        self.assertEqual(after.tick_time_msc, 2000)
        self.assertEqual(before.bid, 4000.)
        self.assertIs(after.candles, before.candles)
        history.refresh.assert_called_once()

    def test_failed_history_stays_unavailable_even_with_quote(self):
        history, mt5 = Mock(), Mock()
        history.refresh.return_value = ([], dict(available=False, error='history disconnected'))
        mt5.symbol_info_tick.return_value = SimpleNamespace(bid=4001., ask=4001.3, time_msc=2000)
        _, health = refresh_fast_snapshot(mt5, history, self.snapshot())
        self.assertFalse(health['available'])

    def test_invalid_quote_and_request_error_fail_closed(self):
        history, mt5 = Mock(), Mock()
        history.refresh.return_value = ([], dict(available=True))
        mt5.symbol_info_tick.return_value = None
        before = self.snapshot()
        after, health = refresh_fast_snapshot(mt5, history, before)
        self.assertFalse(health['available'])
        self.assertIs(after, before)
        history.refresh.side_effect = RuntimeError('offline')
        self.assertFalse(refresh_fast_snapshot(mt5, history, before)[1]['available'])


if __name__ == '__main__':
    unittest.main()
