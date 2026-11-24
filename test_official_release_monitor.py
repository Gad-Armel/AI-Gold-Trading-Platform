from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.news.official_release_monitor import (
    build_official_release_context,
    parse_census_release_events,
    parse_fed_release_events,
    parse_fed_target_midpoint,
)


class OfficialReleaseMonitorTests(unittest.TestCase):
    def test_census_rss_preserves_release_time_and_prior_comparison(self) -> None:
        now = datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc)
        payload = b"""<?xml version='1.0'?><rss><channel><item>
          <title>Advance Monthly Sales for Retail and Food Services</title>
          <link>https://www.census.gov/retail/</link><guid>retail</guid>
          <description><![CDATA[August 2026: +0.7 % Change<br>July 2026 (r): -0.2 % Change]]></description>
          <pubDate>Mon, 07 Sep 2026 15:55:00 GMT</pubDate>
        </item></channel></rss>"""
        events = parse_census_release_events(payload, now=now)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "US Retail Sales")
        self.assertEqual(events[0]["actual"], 0.7)
        self.assertEqual(events[0]["previous"], -0.2)
        self.assertEqual(events[0]["comparison_basis"], "PREVIOUS_RELEASE")
        self.assertTrue(events[0]["reaction_eligible"])

    def test_fed_fractional_target_range_is_parsed_to_midpoint(self) -> None:
        html = (
            b"<p>The Committee decided to maintain the target range for the "
            b"federal funds rate at 3-1/2 to 3-3/4 percent.</p>"
        )
        self.assertEqual(parse_fed_target_midpoint(html), 3.625)

    def test_fed_feed_compares_current_and_prior_official_statements(self) -> None:
        now = datetime(2026, 9, 7, 18, 5, tzinfo=timezone.utc)
        feed = b"""<rss><channel>
          <item><title>Federal Reserve issues FOMC statement</title>
          <link>https://fed/current</link><guid>current</guid>
          <pubDate>Mon, 07 Sep 2026 18:00:00 GMT</pubDate></item>
          <item><title>Federal Reserve issues FOMC statement</title>
          <link>https://fed/prior</link><guid>prior</guid>
          <pubDate>Wed, 29 Jul 2026 18:00:00 GMT</pubDate></item>
        </channel></rss>"""
        pages = {
            "https://fed/current": b"target range for the federal funds rate at 3-1/4 to 3-1/2 percent",
            "https://fed/prior": b"target range for the federal funds rate at 3-1/2 to 3-3/4 percent",
        }
        events = parse_fed_release_events(
            feed, now=now, fetch=lambda url, _timeout: pages[url], timeout=2,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["actual"], 3.375)
        self.assertEqual(events[0]["previous"], 3.625)
        self.assertEqual(events[0]["source"], "OFFICIAL_FED_RSS")

    def test_bea_bootstrap_is_neutral_then_new_period_emits_events_without_key_leak(self) -> None:
        empty_feed = b"<rss><channel></channel></rss>"
        state = {"round": 0}

        def bea_payload(table: str) -> bytes:
            if table == "T10101":
                rows = [
                    {"LineNumber": "1", "TimePeriod": "2026Q1", "DataValue": "2.1",
                     "LineDescription": "Gross domestic product"},
                ]
                if state["round"]:
                    rows.append({"LineNumber": "1", "TimePeriod": "2026Q2", "DataValue": "1.5",
                                 "LineDescription": "Gross domestic product"})
            else:
                rows = [
                    {"LineNumber": "25", "TimePeriod": "2026M07", "DataValue": "0.2",
                     "LineDescription": "PCE excluding food and energy"},
                ]
                if state["round"]:
                    rows.append({"LineNumber": "25", "TimePeriod": "2026M08", "DataValue": "0.3",
                                 "LineDescription": "PCE excluding food and energy"})
            return json.dumps({"BEAAPI": {"Results": {"Data": rows}}}).encode()

        def fetch(url: str, _timeout: float) -> bytes:
            if "TableName=T10101" in url:
                return bea_payload("T10101")
            if "TableName=T20807" in url:
                return bea_payload("T20807")
            return empty_feed

        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "official.json"
            first = build_official_release_context(
                cache_path=cache, refresh_seconds=1, timeout=2,
                bea_api_key="SECRET-KEY", now=datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc),
                fetch=fetch,
            )
            self.assertEqual(first["events"], [])
            state["round"] = 1
            second = build_official_release_context(
                cache_path=cache, refresh_seconds=1, timeout=2,
                bea_api_key="SECRET-KEY", now=datetime(2026, 9, 7, 16, 2, tzinfo=timezone.utc),
                fetch=fetch,
            )
            self.assertEqual({event["title"] for event in second["events"]}, {
                "US GDP", "US Core PCE Inflation",
            })
            self.assertNotIn("SECRET-KEY", cache.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
