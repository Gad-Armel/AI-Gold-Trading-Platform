from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.market_data.gold_institutional_context import (
    discover_latest_wgc_central_bank_url,
    parse_cftc_gold_records,
    parse_wgc_gold_etf_article,
    parse_wgc_central_bank_article,
    sync_gold_institutional_context_if_needed,
)


class GoldInstitutionalContextTests(unittest.TestCase):
    def test_discovers_latest_central_bank_statistics_article(self) -> None:
        page = """
        <a href="/goldhub/gold-focus/2026/08/central-bank-gold-statistics-june-2026">old</a>
        <a href="/goldhub/gold-focus/2026/09/central-bank-gold-statistics-latest">new</a>
        """
        self.assertEqual(
            discover_latest_wgc_central_bank_url(page),
            "https://www.gold.org/goldhub/gold-focus/2026/09/central-bank-gold-statistics-latest",
        )

    def test_parses_attributable_wgc_net_buying_without_country_double_counting(self) -> None:
        article = """
        <meta name="description" content="Central banks continued accumulating in July with net buying
        reported at 23t. China bought 20t and Poland 8t. Y-t-d purchases totalled around 130t." />
        <p>3 September, 2026</p><p>*Data to 31 July 2026, where available.</p>
        """
        result = parse_wgc_central_bank_article(
            article,
            "https://www.gold.org/goldhub/gold-focus/2026/09/central-bank-gold-statistics-latest",
        )
        self.assertEqual(result["net_tonnes"], 23.0)
        self.assertEqual(result["period"], "MONTHLY")
        self.assertEqual(result["observed_at"], "2026-07-31T00:00:00+00:00")
        self.assertIn("World Gold Council", result["source"])

    def test_wgc_net_sales_are_negative_even_when_ytd_purchases_appear_later(self) -> None:
        article = """
        <meta name="description" content="Central banks recorded net sales reported at 7t in August." />
        <p>4 September, 2026</p><p>Data to 31 August 2026.</p>
        <p>Year-to-date net purchases reached 100t.</p>
        """
        result = parse_wgc_central_bank_article(
            article,
            "https://www.gold.org/goldhub/gold-focus/2026/09/central-bank-gold-statistics-latest",
        )
        self.assertEqual(result["net_tonnes"], -7.0)

    def test_cftc_uses_four_week_change_and_52_week_percentile(self) -> None:
        records = []
        latest = datetime(2026, 9, 1, tzinfo=timezone.utc)
        for index in range(52):
            records.append({
                "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
                "report_date_as_yyyy_mm_dd": (latest - timedelta(days=7 * index)).isoformat(),
                "m_money_positions_long_all": str(150_000 - index * 1_000),
                "m_money_positions_short_all": "50000",
                "open_interest_all": "400000",
            })
        result = parse_cftc_gold_records(records)
        self.assertEqual(result["managed_money_net"], 100_000.0)
        self.assertEqual(result["managed_money_net_change_4w"], 4_000.0)
        self.assertEqual(result["managed_money_percentile_52w"], 1.0)

    def test_parses_monthly_wgc_etf_tonnage_with_point_in_time_dates(self) -> None:
        article = """
        <script type="application/ld+json">{"datePublished":"2026-08-06T08:00:00+01:00"}</script>
        <p>Global gold ETFs' collective holdings rebounded by 23t to 4,068t.</p>
        <p>*As of 31 July 2026.</p>
        """
        result = parse_wgc_gold_etf_article(article)
        self.assertEqual(result["net_tonnes"], 23.0)
        self.assertEqual(result["observed_at"], "2026-07-31T00:00:00+00:00")
        self.assertEqual(result["published_at"], "2026-08-06T07:00:00+00:00")

    def test_wgc_etf_outflow_is_negative(self) -> None:
        article = """
        <script>{"datePublished":"2026-08-06T08:00:00+00:00"}</script>
        <p>Global gold ETFs' collective holdings fell by 11t.</p><p>As of 31 July 2026.</p>
        """
        self.assertEqual(parse_wgc_gold_etf_article(article)["net_tonnes"], -11.0)

    def test_refresh_merges_automatic_sources_with_existing_manual_etf(self) -> None:
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "institutional.json"
            path.write_text(json.dumps({
                "source": "Verified WGC ETF workbook",
                "observed_at": "2026-08-31T00:00:00+00:00",
                "recorded_at": "2026-09-03T00:00:00+00:00",
                "etf_tonnes_change": 12.0,
            }), encoding="utf-8")
            result = sync_gold_institutional_context_if_needed(
                cache_path=path, force=True, now=now,
                wgc_fetch=lambda: {
                    "net_tonnes": 23.0, "period": "MONTHLY", "available": True,
                    "observed_at": "2026-07-31T00:00:00+00:00",
                    "published_at": "2026-09-03T00:00:00+00:00",
                    "source": "World Gold Council", "source_quality": 0.9,
                },
                etf_fetch=lambda: {
                    "net_tonnes": 12.0, "period": "MONTHLY", "available": True,
                    "observed_at": "2026-08-31T00:00:00+00:00",
                    "published_at": "2026-09-03T00:00:00+00:00",
                    "source": "Verified WGC ETF workbook", "source_quality": 0.9,
                },
                cftc_fetch=lambda: {
                    "managed_money_net_change_4w": 6000.0, "available": True,
                    "observed_at": "2026-09-01T00:00:00+00:00",
                    "published_at": "2026-09-04T20:30:00+00:00",
                    "source": "U.S. CFTC", "source_quality": 0.98,
                },
            )
            stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result["refresh_status"], "LIVE_REFRESH")
        self.assertEqual(stored["schema_version"], 2)
        self.assertEqual(stored["etf_tonnes_change"], 12.0)
        self.assertEqual(stored["central_bank_net_tonnes_change"], 23.0)
        self.assertEqual(stored["managed_money_net_change_4w"], 6000.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
