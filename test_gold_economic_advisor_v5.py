from __future__ import annotations

import unittest
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from services.research.gold_economic_advisor_v5 import build_gold_economic_advisor_v5


class GoldEconomicAdvisorV5Tests(unittest.TestCase):
    def test_each_horizon_confirmation_budget_is_exactly_one_hundred(self) -> None:
        report = build_gold_economic_advisor_v5({}, {}, institutional_path="missing.json")
        for horizon in report["horizons"].values():
            self.assertAlmostEqual(
                sum(float(item["maximum_points"]) for item in horizon["confidence_breakdown"]),
                100.0,
            )

    def test_verified_release_market_reaction_can_inform_scalp_and_intraday(self) -> None:
        now = datetime(2026, 9, 7, 16, 10, tzinfo=timezone.utc)
        candles = []
        for minutes_ago in range(30, -1, -1):
            candle_time = (now - timedelta(minutes=minutes_ago)).replace(tzinfo=None)
            candles.append({
                "time": candle_time, "open": 4400.0, "high": 4400.2,
                "low": 4399.8, "close": 4400.0,
            })
        snapshot = SimpleNamespace(
            mid=4402.0, spread=0.3, candles={"M1": candles},
            market_clock_offset_seconds=0.0,
        )
        news = {
            "relevant_events": [{
                "title": "FOMC Minutes",
                "event_time": (now - timedelta(minutes=5)).isoformat(),
                "calendar_confidence": "VERIFIED", "reaction_eligible": True,
                "source_url": "https://www.federalreserve.gov/",
            }],
        }
        report = build_gold_economic_advisor_v5(
            news, {}, snapshot=snapshot, institutional_path="missing.json", now=now,
        )
        scalp = report["horizons"]["SCALP"]
        intraday = report["horizons"]["INTRADAY"]
        self.assertEqual(scalp["bias"], "BUY")
        self.assertEqual(intraday["bias"], "BUY")
        self.assertGreater(scalp["confidence_points"], 0)
        self.assertLessEqual(scalp["confidence_points"], 30.0)

    def test_stronger_usd_and_real_yields_are_gold_negative(self) -> None:
        macro = {"observations": {
            "usd_broad": {"change_5": 1, "pct_change_5": 0.8, "age_days": 0},
            "us10y_real": {"change_5": 1, "age_days": 0},
            "us10y": {"change_5": 1, "age_days": 0},
            "vix": {"change_5": -1, "age_days": 0},
        }}
        report = build_gold_economic_advisor_v5({}, macro, institutional_path="missing.json")
        self.assertEqual(report["horizons"]["INTRADAY"]["bias"], "SELL")

    def test_rising_global_policy_uncertainty_confirms_swing_buy_only(self) -> None:
        now = datetime.now(timezone.utc)
        macro = {"observations": {"global_policy_uncertainty": {
            "pct_change_5": 40.0, "observation_time": (now - timedelta(days=10)).isoformat(),
        }}}
        report = build_gold_economic_advisor_v5({}, macro, institutional_path="missing.json", now=now)
        self.assertEqual(report["horizons"]["SCALP"]["bias"], "NEUTRAL")
        self.assertEqual(report["horizons"]["INTRADAY"]["bias"], "NEUTRAL")
        self.assertEqual(report["horizons"]["SWING"]["bias"], "BUY")
        points = {item["component"]: item for item in report["horizons"]["SWING"]["confidence_breakdown"]}
        self.assertGreater(points["global_policy_uncertainty"]["points"], 0)

    def test_falling_global_policy_uncertainty_confirms_swing_sell(self) -> None:
        now = datetime.now(timezone.utc)
        macro = {"observations": {"global_policy_uncertainty": {
            "pct_change_5": -40.0, "observation_time": (now - timedelta(days=10)).isoformat(),
        }}}
        report = build_gold_economic_advisor_v5({}, macro, institutional_path="missing.json", now=now)
        self.assertEqual(report["horizons"]["SWING"]["bias"], "SELL")

    def test_daily_policy_uncertainty_can_confirm_intraday_but_not_scalp(self) -> None:
        now = datetime.now(timezone.utc)
        macro = {"observations": {"us_policy_uncertainty": {
            "mean_5_minus_20": 100.0, "observation_time": now.isoformat(),
        }}}
        report = build_gold_economic_advisor_v5({}, macro, institutional_path="missing.json", now=now)
        self.assertEqual(report["horizons"]["SCALP"]["bias"], "NEUTRAL")
        self.assertEqual(report["horizons"]["INTRADAY"]["bias"], "BUY")
        self.assertEqual(report["horizons"]["SWING"]["bias"], "BUY")

    def test_tighter_systemic_financial_stress_confirms_swing_buy(self) -> None:
        now = datetime.now(timezone.utc)
        macro = {"observations": {
            "financial_stress_stl": {
                "value": 1.2, "mean_5_minus_20": 0.4, "observation_time": now.isoformat(),
            },
            "financial_conditions_chicago": {
                "value": 0.8, "mean_5_minus_20": 0.2, "observation_time": now.isoformat(),
            },
        }}
        report = build_gold_economic_advisor_v5({}, macro, institutional_path="missing.json", now=now)
        component = next(item for item in report["components"]
                         if item["name"] == "systemic_financial_stress")
        self.assertGreater(component["score"], 0.5)
        self.assertEqual(report["horizons"]["SWING"]["bias"], "BUY")

    def test_world_bank_growth_slowdown_is_small_swing_only_confirmation(self) -> None:
        now = datetime.now(timezone.utc)
        macro = {"observations": {"world_bank_global_growth": {
            "value": 2.5, "forecast_year": now.year,
            "change_from_previous_year": -0.4,
            "observation_time": (now - timedelta(days=30)).isoformat(),
            "source": "World Bank Global Economic Prospects", "source_quality": 0.98,
        }}}
        report = build_gold_economic_advisor_v5({}, macro, institutional_path="missing.json", now=now)
        self.assertEqual(report["horizons"]["SCALP"]["bias"], "NEUTRAL")
        self.assertEqual(report["horizons"]["INTRADAY"]["bias"], "NEUTRAL")
        self.assertEqual(report["horizons"]["SWING"]["bias"], "BUY")
        swing = report["horizons"]["SWING"]
        point = next(item for item in swing["confidence_breakdown"]
                     if item["component"] == "world_bank_growth_outlook")
        self.assertGreater(point["points"], 0)
        self.assertLessEqual(point["maximum_points"], 5.0)
        self.assertGreater(swing["data_coverage"], 0)

    def test_missing_data_remains_neutral_and_cannot_claim_quality(self) -> None:
        report = build_gold_economic_advisor_v5({}, {}, institutional_path="missing.json")
        for horizon in report["horizons"].values():
            self.assertEqual(horizon["bias"], "NEUTRAL")
            self.assertEqual(horizon["quality"], 0.0)

    def test_verified_release_can_inform_scalp_without_becoming_execution(self) -> None:
        news = {"data_mode": "VERIFIED_SURPRISE", "directional_event_count": 1,
                "directional_bias_value": 0.8, "provider_quality": 0.0}
        report = build_gold_economic_advisor_v5(news, {}, institutional_path="missing.json")
        self.assertEqual(report["horizons"]["SCALP"]["bias"], "BUY")
        self.assertAlmostEqual(report["horizons"]["SCALP"]["quality"], 0.525)
        self.assertLessEqual(report["horizons"]["SCALP"]["confidence_points"], 70.0)
        self.assertFalse(report["execution_enabled"])

    def test_unprovenanced_institutional_data_has_zero_quality(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "institutional.json"
            path.write_text(json.dumps({"central_bank_net_tonnes_change": 500, "age_days": 0}), encoding="utf-8")
            report = build_gold_economic_advisor_v5({}, {}, institutional_path=path)
        component = next(item for item in report["components"] if item["name"] == "institutional_demand_positioning")
        self.assertEqual(component["quality"], 0.0)
        self.assertEqual(report["horizons"]["SWING"]["bias"], "NEUTRAL")

    def test_stale_observations_are_ignored_not_given_negative_quality(self) -> None:
        macro = {"observations": {"usd_broad": {"pct_change_5": 5.0, "age_days": 30}}}
        report = build_gold_economic_advisor_v5({}, macro, institutional_path="missing.json")
        component = next(item for item in report["components"] if item["name"] == "usd_yields_risk_regime")
        self.assertEqual(component["quality"], 0.0)
        self.assertEqual(report["horizons"]["INTRADAY"]["bias"], "NEUTRAL")

    def test_institutional_magnitude_is_continuous_not_binary(self) -> None:
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "institutional.json"
            base = {"source": "verified publication", "observed_at": (now - timedelta(days=1)).isoformat(),
                    "etf_tonnes_change": 0, "managed_money_net_change_4w": 0}
            path.write_text(json.dumps({**base, "central_bank_net_tonnes_change": 1}), encoding="utf-8")
            small = build_gold_economic_advisor_v5({}, {}, institutional_path=path, now=now)
            path.write_text(json.dumps({**base, "central_bank_net_tonnes_change": 100}), encoding="utf-8")
            large = build_gold_economic_advisor_v5({}, {}, institutional_path=path, now=now)
        score_small = next(item["score"] for item in small["components"] if item["name"].startswith("institutional"))
        score_large = next(item["score"] for item in large["components"] if item["name"].startswith("institutional"))
        self.assertGreater(score_large, score_small)

    def test_central_bank_and_cftc_records_use_independent_freshness(self) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "schema_version": 2,
            "source": "WGC | CFTC",
            "observations": {
                "central_bank": {
                    "net_tonnes": 40, "period": "MONTHLY", "source": "WGC",
                    "source_quality": 0.9,
                    "observed_at": (now - timedelta(days=35)).isoformat(),
                    "published_at": (now - timedelta(days=3)).isoformat(),
                },
                "managed_money": {
                    "managed_money_net_change_4w": -20000, "open_interest": 400000,
                    "source": "CFTC", "source_quality": 0.98,
                    "observed_at": (now - timedelta(days=6)).isoformat(),
                    "published_at": (now - timedelta(days=2)).isoformat(),
                },
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "institutional.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            report = build_gold_economic_advisor_v5({}, {}, institutional_path=path, now=now)
        central = next(item for item in report["components"] if item["name"] == "central_bank_gold_demand")
        cftc = next(item for item in report["components"] if item["name"] == "cftc_managed_money_flow")
        self.assertGreater(central["score"], 0)
        self.assertLess(cftc["score"], 0)
        self.assertGreater(central["quality"], 0)
        self.assertGreater(cftc["quality"], 0)
        self.assertTrue(report["institutional_context_available"])

    def test_institutional_confirmation_points_follow_economic_direction(self) -> None:
        now = datetime.now(timezone.utc)

        def report_for(etf_tonnes: float) -> dict:
            payload = {
                "schema_version": 2,
                "source": "WGC",
                "observations": {
                    "central_bank": {
                        "net_tonnes": 60, "period": "MONTHLY", "source": "WGC central banks",
                        "source_quality": 0.9, "observed_at": now.isoformat(),
                        "published_at": now.isoformat(),
                    },
                    "gold_etf": {
                        "net_tonnes": etf_tonnes, "period": "MONTHLY", "source": "WGC ETF",
                        "source_quality": 0.9, "observed_at": now.isoformat(),
                        "published_at": now.isoformat(),
                    },
                },
            }
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "institutional.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                return build_gold_economic_advisor_v5({}, {}, institutional_path=path, now=now)

        conflicting = report_for(-30)
        aligned = report_for(30)
        conflict_swing = conflicting["horizons"]["SWING"]
        aligned_swing = aligned["horizons"]["SWING"]
        by_name = {item["component"]: item for item in conflict_swing["confidence_breakdown"]}
        self.assertEqual(conflict_swing["bias"], "BUY")
        self.assertGreater(by_name["central_bank_gold_demand"]["points"], 0)
        self.assertLess(by_name["gold_etf_physical_flows"]["points"], 0)
        self.assertGreater(conflict_swing["contradiction_points"], 0)
        self.assertGreater(aligned_swing["confidence_points"], conflict_swing["confidence_points"])

    def test_central_bank_net_sales_confirm_sell_not_buy(self) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "schema_version": 2, "source": "WGC",
            "observations": {"central_bank": {
                "net_tonnes": -50, "period": "MONTHLY", "source": "WGC central banks",
                "source_quality": 0.9, "observed_at": now.isoformat(), "published_at": now.isoformat(),
            }},
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "institutional.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            report = build_gold_economic_advisor_v5({}, {}, institutional_path=path, now=now)
        swing = report["horizons"]["SWING"]
        central = next(item for item in swing["confidence_breakdown"]
                       if item["component"] == "central_bank_gold_demand")
        self.assertEqual(swing["bias"], "SELL")
        self.assertEqual(central["source_direction"], "SELL")
        self.assertGreater(central["points"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
