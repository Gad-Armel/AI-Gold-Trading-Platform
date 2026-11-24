import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

from config import gold_consensus_settings as settings
from services.research.gold_tick_history import TickHistoryBuffer


class TickCursorTests(unittest.TestCase):
    def refresh(self, cached_epoch, fresh_epoch):
        now = datetime.fromtimestamp(1793226000., timezone.utc)
        buffer = TickHistoryBuffer()
        buffer.frame = pd.DataFrame([dict(timestamp=cached_epoch, bid=4000., ask=4000.2)])
        calls = []
        class Broker:
            COPY_TICKS_ALL = 0
            def copy_ticks_range(self, symbol, start, end, flags):
                calls.append((start, end))
                return [1]
        fresh = pd.DataFrame([dict(timestamp=fresh_epoch+settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                                   bid=4000., ask=4000.2)])
        with patch('services.research.gold_advisory_v3._tick_frame', return_value=fresh):
            _, health = buffer.refresh(Broker(), 'XAUUSD', now)
        start = calls[0][0].timestamp()-settings.MT5_SERVER_UTC_OFFSET_SECONDS
        return now.timestamp(), start, health

    def test_tolerated_future_tick_never_moves_request_start_into_future(self):
        now, start, health = self.refresh(1793226004., 1793226004.)
        self.assertLessEqual(start, now-1.)
        self.assertGreaterEqual(health['request_seconds'], 1.)
        self.assertTrue(health['available'])

    def test_past_tick_keeps_existing_overlap(self):
        now, start, health = self.refresh(1793225998., 1793226000.)
        self.assertEqual(start, now-3.)
        self.assertTrue(health['available'])

    def test_excessive_future_quote_is_still_rejected(self):
        _, _, health = self.refresh(1793226000., 1793226020.)
        self.assertFalse(health['available'])
        self.assertIn('future timestamps', health['error'])


if __name__ == '__main__':
    unittest.main()
