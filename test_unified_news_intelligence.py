from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.news.unified_news_intelligence import (
    _event_gold_bias, _safe_float, build_unified_news_context,
)
from services.risk.automatic_economic_calendar import _convert_fmp_event_to_internal


class UnifiedNewsIntelligenceTests(unittest.TestCase):
    def test_fmp_normalization_preserves_surprise_fields(self) -> None:
        event = _convert_fmp_event_to_internal({
            "date": "2026-09-07 12:30:00", "event": "CPI", "actual": 3.2,
            "estimate": 3.0, "previous": 2.9, "impact": "High",
        })
        self.assertIsNotNone(event)
        self.assertEqual(event["actual"], 3.2)
        self.assertEqual(event["forecast"], 3.0)
        self.assertEqual(event["calendar_confidence"], "PROVIDER_VERIFIED")

    def test_common_economic_units_are_parsed(self) -> None:
        self.assertEqual(_safe_float("250K"), 250.0)
        self.assertEqual(_safe_float("3.2%"), 3.2)
        self.assertIsNone(_safe_float("unknown"))

    def test_extended_verified_release_mappings_are_directional_and_scaled(self) -> None:
        ppi_bias, ppi_reason, ppi_surprise = _event_gold_bias({
            "title": "US Core PPI", "actual": "0.5%", "forecast": "0.3%",
        })
        adp_bias, adp_reason, adp_surprise = _event_gold_bias({
            "title": "US ADP Nonfarm Employment Change", "actual": "210K", "forecast": "160K",
        })
        self.assertLess(ppi_bias, 0)
        self.assertAlmostEqual(ppi_surprise or 0.0, 1.0)
        self.assertIn("PRODUCER_INFLATION", ppi_reason)
        self.assertLess(adp_bias, 0)
        self.assertAlmostEqual(adp_surprise or 0.0, 1.0)
        self.assertIn("ADP_EMPLOYMENT", adp_reason)

    @patch("services.news.unified_news_intelligence._load_provider_cache", return_value={})
    @patch("services.news.unified_news_intelligence.load_events")
    def test_verified_payroll_surprise_is_scaled_and_gold_negative(self, events, _cache) -> None:
        now = datetime.now(timezone.utc)
        events.return_value = [{"title": "US Nonfarm Payrolls", "currency": "USD", "impact": "HIGH",
            "event_time": (now - timedelta(minutes=5)).isoformat(), "actual": "250K", "forecast": "200K",
            "calendar_confidence": "VERIFIED", "source": "BLS"}]
        result = build_unified_news_context("New York", {"allowed": True}, now)
        self.assertEqual(result["data_mode"], "VERIFIED_SURPRISE")
        self.assertEqual(result["directional_bias"], "SELL")
        self.assertAlmostEqual(result["relevant_events"][0]["surprise"], 1.0)
        self.assertEqual(result["directional_data_quality"], 1.0)

    @patch("services.news.unified_news_intelligence._load_provider_cache", return_value={})
    @patch("services.news.unified_news_intelligence.load_events")
    def test_estimated_or_future_event_protects_but_never_predicts(self, events, _cache) -> None:
        now = datetime.now(timezone.utc)
        events.return_value = [{"title": "US CPI", "currency": "USD", "impact": "HIGH",
            "event_time": (now + timedelta(minutes=5)).isoformat(), "actual": 3.5, "forecast": 3.2,
            "calendar_confidence": "ESTIMATED", "source": "FALLBACK"}]
        result = build_unified_news_context("New York", {"allowed": False, "block_reasons": ["CPI window"]}, now)
        self.assertEqual(result["directional_event_count"], 0)
        self.assertEqual(result["directional_bias"], "NEUTRAL")
        self.assertTrue(result["hard_block"])

    @patch("services.news.unified_news_intelligence._load_provider_cache", return_value={})
    @patch("services.news.unified_news_intelligence.load_events", return_value=[])
    def test_official_previous_release_change_is_separate_and_quality_capped(self, _events, _cache) -> None:
        now = datetime.now(timezone.utc)
        result = build_unified_news_context(
            "New York", {"allowed": True}, now,
            extra_events=[{
                "title": "US GDP", "currency": "USD", "impact": "HIGH",
                "event_time": (now - timedelta(minutes=3)).isoformat(),
                "actual": 1.5, "forecast": None, "previous": 2.1,
                "comparison_basis": "PREVIOUS_RELEASE", "directional_quality": 0.9,
                "calendar_confidence": "VERIFIED", "source": "OFFICIAL_BEA_API",
                "reaction_eligible": True,
            }],
        )
        self.assertEqual(result["data_mode"], "OFFICIAL_CHANGE_NOT_CONSENSUS")
        self.assertEqual(result["consensus_event_count"], 0)
        self.assertEqual(result["official_change_event_count"], 1)
        self.assertLessEqual(result["official_change_data_quality"], 0.35)
        self.assertEqual(result["directional_bias"], "BUY")

    @patch("services.news.unified_news_intelligence._load_provider_cache", return_value={})
    @patch("services.news.unified_news_intelligence.load_events")
    def test_small_opposing_surprise_reduces_quality_without_erasing_stronger_signal(self, events, _cache) -> None:
        now = datetime.now(timezone.utc)
        common = {"currency": "USD", "impact": "HIGH", "event_time": (now - timedelta(minutes=5)).isoformat(),
                  "calendar_confidence": "VERIFIED", "source": "OFFICIAL"}
        events.return_value = [
            {**common, "title": "US CPI", "actual": 3.3, "forecast": 3.0},
            {**common, "title": "US Unemployment Rate", "actual": 4.01, "forecast": 4.0},
        ]
        result = build_unified_news_context("New York", {"allowed": True}, now)
        self.assertTrue(result["provider_conflict"])
        self.assertEqual(result["directional_bias"], "SELL")
        self.assertGreater(result["directional_data_quality"], 0.5)
        self.assertLess(result["directional_data_quality"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
