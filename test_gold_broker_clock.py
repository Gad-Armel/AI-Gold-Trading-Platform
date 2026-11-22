import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from services.market_data.gold_broker_clock import to_broker_time, broker_epoch_to_utc, quote_age
from services.research.gold_runtime_health import market_health
from types import SimpleNamespace


class BrokerClockTests(unittest.TestCase):
    def test_explicit_three_hour_conversion_round_trip(self):
        now=datetime(2026,9,10,13,0,tzinfo=timezone.utc)
        with patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS',10800):
            encoded=to_broker_time(now)
            self.assertEqual(encoded.hour,16)
            self.assertEqual(broker_epoch_to_utc(encoded.timestamp()),now)

    def test_unconfigured_future_clock_is_not_fresh(self):
        with patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS',0):
            self.assertEqual(quote_age(datetime.now(timezone.utc).timestamp()+10800),float('inf'))

    def test_naive_query_is_rejected(self):
        with self.assertRaises(ValueError):to_broker_time(datetime.now())

    def test_small_future_skew_is_usable_in_health_and_execution(self):
        now = datetime.now(timezone.utc).timestamp()
        with patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0):
            snapshot = SimpleNamespace(tick_time_msc=(now + 2.6)*1000, bid=4131.98, ask=4132.30)
            health = market_health(snapshot, SimpleNamespace(connected=True), now=now)
            self.assertTrue(health['available'])
            self.assertEqual(health['quote_age_seconds'], -2.6)
            self.assertEqual(quote_age(now + 2.6), 0.0)

    def test_large_future_skew_still_blocks(self):
        now = datetime.now(timezone.utc).timestamp()
        with patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0):
            snapshot = SimpleNamespace(tick_time_msc=(now + 60)*1000, bid=4131.98, ask=4132.30)
            self.assertFalse(market_health(snapshot, SimpleNamespace(connected=True), now=now)['available'])
            self.assertEqual(quote_age(now + 60), float('inf'))

    def test_stale_quote_still_blocks(self):
        now = datetime.now(timezone.utc).timestamp()
        with patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0):
            snapshot = SimpleNamespace(tick_time_msc=(now - 600)*1000, bid=4131.98, ask=4132.30)
            self.assertFalse(market_health(snapshot, SimpleNamespace(connected=True), now=now)['available'])

    def test_micro_flow_accepts_small_clock_skew_but_rejects_large_skew(self):
        from services.research.gold_micro_flow import MicroFlow
        flow = MicroFlow()
        self.assertTrue(flow.observe(quote_time=102.6, bid=4000, ask=4000.2, now=100))
        self.assertNotEqual(flow.read(now=100)['reason'], 'No fresh quote-flow observation')
        self.assertFalse(flow.observe(quote_time=160, bid=4000, ask=4000.2, now=100))


if __name__=='__main__':unittest.main()
