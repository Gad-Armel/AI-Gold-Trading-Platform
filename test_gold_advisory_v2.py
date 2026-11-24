from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from services.market_data.twelve_data_gold import TwelveDataError, fetch_twelve_data_snapshot
from services.market_data.oanda_gold import fetch_oanda_gold_snapshot
from services.research.gold_advisory_v2 import build_gold_advisory_v2


def api_getter(url: str, timeout: float) -> dict:
    del timeout
    interval = parse_qs(urlparse(url).query)["interval"][0]
    minutes = {"1min": 1, "5min": 5, "15min": 15, "1h": 60, "4h": 240}[interval]
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    values = []
    for index in range(90):
        close = 4000.0 + index * 0.10
        values.append({"datetime": (start + timedelta(minutes=index * minutes)).strftime("%Y-%m-%d %H:%M:%S"),
                       "open": str(close - 0.04), "high": str(close + 0.08), "low": str(close - 0.08), "close": str(close)})
    return {"status": "ok", "values": list(reversed(values))}


def oanda_getter(url: str, token: str, timeout: float) -> dict:
    del token, timeout
    if url.endswith("/v3/accounts"):
        return {"accounts": [{"id": "auto-discovered"}]}
    granularity = parse_qs(urlparse(url).query)["granularity"][0]
    minutes = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240}[granularity]
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(90):
        close = 4100.0 + index * 0.10
        candles.append({"time": (start + timedelta(minutes=index * minutes)).isoformat(), "volume": 10,
                        "complete": True, "mid": {"o": str(close - .04), "h": str(close + .08),
                        "l": str(close - .08), "c": str(close)}})
    return {"instrument": "XAU_USD", "candles": candles}


def oanda_live_only_getter(url: str, token: str, timeout: float) -> dict:
    if "api-fxpractice" in url:
        raise PermissionError("practice rejected")
    return oanda_getter(url, token, timeout)


class GoldAdvisoryV2Tests(unittest.TestCase):
    def test_missing_key_is_clear(self) -> None:
        with self.assertRaisesRegex(TwelveDataError, "TWELVE_DATA_API_KEY"):
            fetch_twelve_data_snapshot("", getter=api_getter)

    def test_api_adapter_builds_all_frames(self) -> None:
        snapshot = fetch_twelve_data_snapshot("test-key", getter=api_getter)
        self.assertEqual(set(snapshot.candles), {"M1", "M5", "M15", "H1", "H4"})
        self.assertEqual(snapshot.market_clock_source, "TWELVE_DATA_UTC")
        self.assertEqual(snapshot.mid, 4008.9)

    def test_oanda_adapter_discovers_account_and_builds_all_frames(self) -> None:
        snapshot = fetch_oanda_gold_snapshot("test-token", getter=oanda_getter)
        self.assertEqual(set(snapshot.candles), {"M1", "M5", "M15", "H1", "H4"})
        self.assertEqual(snapshot.market_clock_source, "OANDA_V20")
        self.assertEqual(snapshot.mid, 4108.9)

    def test_oanda_adapter_automatically_falls_back_to_live_environment(self) -> None:
        snapshot = fetch_oanda_gold_snapshot("live-token", environment="practice", getter=oanda_live_only_getter)
        self.assertEqual(snapshot.market_clock_source, "OANDA_V20")
        self.assertEqual(snapshot.mid, 4108.9)

    @patch("services.research.gold_advisory.build_v6_market_structure", return_value={"direction": "BUY"})
    @patch("services.research.gold_advisory.build_verified_market_context", return_value={"vwap_distance_atr": 0.4})
    def test_v2_is_read_only_and_source_labelled(self, _context, _structure) -> None:
        report = build_gold_advisory_v2(fetch_twelve_data_snapshot("test-key", getter=api_getter))
        self.assertEqual(report["overall"], "BUY")
        self.assertEqual(report["data_source"], "Twelve Data XAU/USD OHLC")
        self.assertTrue(report["reference_price_only"])
        self.assertFalse(report["execution_enabled"])
        self.assertFalse(report["orders_sent"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
