from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from services.research.gold_advisory_consensus import build_gold_advisory_consensus
from services.research.gold_horizon_policy import build_horizon_decisions


def report(action: str = "BUY", bias: str = "BUY", score: float = 90.0, *, age: float = 0.0) -> dict:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=age)
    return {
        "generated_at": stamp.isoformat(), "bid": 4000.0, "ask": 4000.2, "mid": 4000.1,
        "source_bar_age_seconds": 30.0,
        "horizons": {name: {"action": action, "bias": bias, "directional_score": score,
            "valid_until": (stamp + timedelta(minutes=30)).isoformat(), "blocks": [],
            "levels": {"sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0, "tp3": 4030.0,
                       "entry_zone": [3999.0, 4001.0]}}
            for name in ("SCALP", "INTRADAY", "SWING")},
    }


class GoldAdvisoryConsensusTests(unittest.TestCase):
    def test_three_advisors_agree(self) -> None:
        result = build_gold_advisory_consensus(report(score=88), report(score=94), report(score=91))
        self.assertTrue(result["allowed"])
        self.assertEqual(result["direction"], "BUY")
        self.assertEqual(result["evidence"], 91.0)
        self.assertEqual(result["horizons"]["SCALP"]["suggested_levels"]["tp1"], 4010.0)
        self.assertIsNotNone(result["horizons"]["SCALP"]["valid_until"])

    def test_wait_action_is_ignored_when_biases_dominate(self) -> None:
        result = build_gold_advisory_consensus(report(), report(), report(action="WAIT", bias="BUY", score=86))
        self.assertTrue(result["allowed"])
        self.assertEqual(result["direction"], "BUY")
        self.assertEqual(result["horizons"]["SCALP"]["wait_count"], 0)

    def test_two_wait_actions_do_not_override_dominant_bias(self) -> None:
        result = build_gold_advisory_consensus(
            report(action="WAIT", bias="BUY", score=95), report(action="WAIT", bias="SELL", score=95),
            report(action="BUY", bias="BUY", score=95),
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["direction"], "BUY")

    def test_two_wait_biases_force_wait(self) -> None:
        result = build_gold_advisory_consensus(
            report(action="BUY", bias="WAIT", score=99), report(action="SELL", bias="WAIT", score=99),
            report(action="BUY", bias="BUY", score=99),
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["direction"], "WAIT")

    def test_three_wait_biases_make_wait_effective(self) -> None:
        result = build_gold_advisory_consensus(report(bias="WAIT"), report(bias="WAIT"), report(bias="WAIT"))
        self.assertFalse(result["allowed"])
        self.assertEqual(result["direction"], "WAIT")
        self.assertIn("3/3 advisor biases are WAIT", result["horizons"]["SCALP"]["notes"][0])

    def test_two_horizons_determine_final_direction(self) -> None:
        left, right, tick = report(), report(), report()
        for item in (left, right, tick):
            item["horizons"]["SWING"].update(action="SELL", bias="SELL", directional_score=95)
        result = build_gold_advisory_consensus(left, right, tick)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["direction"], "BUY")

    def test_expired_horizon_cannot_vote(self) -> None:
        tick = report()
        tick["horizons"]["SCALP"]["valid_until"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        result = build_gold_advisory_consensus(report(), report(), tick)
        self.assertTrue(result["allowed"])  # INTRADAY and SWING still dominate.
        self.assertFalse(result["horizons"]["SCALP"]["confirmed"])
        self.assertFalse(result['horizons']['SCALP']['v3']['source_usable'])
        self.assertTrue(result['horizons']['INTRADAY']['v3']['source_usable'])

    def test_expired_api_forecast_cannot_authorize_main_secondary_entry(self):
        now=datetime.now(timezone.utc)
        api=report()
        api['horizons']['INTRADAY']['valid_until']=(now-timedelta(seconds=1)).isoformat()
        consensus=build_gold_advisory_consensus(report(bias='WAIT'),api,report(bias='WAIT'),now=now)
        decisions=build_horizon_decisions(consensus)
        self.assertFalse(decisions['INTRADAY']['allowed'])
        self.assertIsNone(decisions['INTRADAY']['take_profit'])
        source=next(c for c in decisions['INTRADAY']['contributors'] if c['advisor']=='API_CANDLES')
        self.assertFalse(source['source_usable'])
        self.assertIn('expired',source['validity_reason'])

    def test_expired_other_advisor_does_not_block_fresh_primary_scalp(self):
        now=datetime.now(timezone.utc)
        api=report()
        api['horizons']['SCALP']['valid_until']=(now-timedelta(seconds=1)).isoformat()
        consensus=build_gold_advisory_consensus(report(),api,report(bias='WAIT'),now=now)
        decisions=build_horizon_decisions(consensus,market_context={
            'SCALP':dict(available=True,bid=4000.,ask=4000.2,atr=3.)})
        self.assertTrue(decisions['SCALP']['allowed'])
        self.assertEqual(decisions['SCALP']['direction'],'BUY')

    def test_missing_horizon_validity_cannot_vote_despite_fresh_report(self):
        api=report()
        api['horizons']['SWING'].pop('valid_until')
        consensus=build_gold_advisory_consensus(report(),api,report())
        self.assertFalse(consensus['horizons']['SWING']['api']['source_usable'])
        self.assertTrue(consensus['horizons']['INTRADAY']['api']['source_usable'])

    def test_stale_source_blocks_all_execution(self) -> None:
        result = build_gold_advisory_consensus(report(), report(age=500), report())
        self.assertFalse(result["allowed"])
        self.assertTrue(any("stale" in reason for reason in result["blocks"]))

    def test_stale_api_bar_blocks_all_execution(self) -> None:
        api = report(); api["source_bar_age_seconds"] = 600.0
        result = build_gold_advisory_consensus(report(), api, report())
        self.assertFalse(result["allowed"])

    def test_cross_feed_price_divergence_blocks_execution(self) -> None:
        api = report(); api["mid"] = 4010.0
        result = build_gold_advisory_consensus(report(), api, report())
        self.assertFalse(result["allowed"])

    def test_fresh_report_cannot_hide_stale_underlying_api_candle(self):
        now=datetime.now(timezone.utc)
        api=report()
        api['source_bar_time']=(now-timedelta(seconds=240)).isoformat()
        result=build_gold_advisory_consensus(report(),api,report(),now=now)
        self.assertEqual(result['sources']['API_CANDLES']['bar_age_seconds'],240.)
        self.assertFalse(result['horizons']['SCALP']['api']['source_usable'])
        self.assertTrue(result['horizons']['SCALP']['mt5']['source_usable'])

    def test_legacy_bar_age_advances_while_report_is_cached(self):
        now=datetime.now(timezone.utc)
        api=report()
        api['generated_at']=(now-timedelta(seconds=60)).isoformat()
        api['source_bar_age_seconds']=150.
        result=build_gold_advisory_consensus(report(),api,report(),now=now)
        source=result['sources']['API_CANDLES']
        self.assertTrue(source['fresh'])
        self.assertEqual(source['bar_age_seconds'],210.)
        self.assertFalse(source['bar_fresh'])
        self.assertFalse(result['horizons']['SCALP']['api']['source_usable'])

    def test_source_timestamp_updates_age_without_mutating_cached_report(self):
        now=datetime.now(timezone.utc)
        api=report()
        api['source_bar_time']=(now-timedelta(seconds=50)).isoformat()
        original=deepcopy(api)
        first=build_gold_advisory_consensus(report(),api,report(),now=now)
        later=build_gold_advisory_consensus(report(),api,report(),now=now+timedelta(seconds=20))
        self.assertEqual(first['sources']['API_CANDLES']['bar_age_seconds'],50.)
        self.assertEqual(later['sources']['API_CANDLES']['bar_age_seconds'],70.)
        self.assertEqual(api,original)

    def test_future_or_invalid_candle_timestamp_cannot_vote(self):
        now=datetime.now(timezone.utc)
        for value in ((now+timedelta(seconds=300)).isoformat(),'invalid timestamp'):
            api=report()
            api['source_bar_time']=value
            result=build_gold_advisory_consensus(report(),api,report(),now=now)
            self.assertFalse(result['horizons']['SCALP']['api']['source_usable'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
