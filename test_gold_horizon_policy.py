from __future__ import annotations

import unittest
from unittest.mock import patch
from config import gold_consensus_settings as settings

from services.research.gold_horizon_policy import (
    build_horizon_decisions as _build, evaluate_entry_timing, should_close_horizon,
)


def build_horizon_decisions(*args, **kwargs):
    kwargs.setdefault('market_context', {'SCALP': dict(available=True, atr=2., bid=4000., ask=4000.2)})
    with patch('config.gold_consensus_settings.CONTINUOUS_DIRECTIONAL_ENTRIES', False), patch.dict(settings.HORIZON_LANES['SCALP'], entry_mode='FLOW_PRIMARY', required_strong_advisors=('MT5_TICK_FLOW',)):
        return _build(*args, **kwargs)


def _advisor(bias: str, evidence: float, action: str = "WAIT") -> dict:
    return {"bias": bias, "evidence": evidence, "action": action,
            "levels": {"sl": 3990.0, "tp1": 4005.0, "tp2": 4010.0, "tp3": 4020.0,
                       "entry_zone": [3999.5, 4000.5]},
            "valid_until": "2026-08-11T12:00:00+00:00"}


def _consensus(mt5: tuple[str, float], api: tuple[str, float], tick: tuple[str, float]) -> dict:
    horizons = {}
    for name in ("SCALP", "INTRADAY", "SWING"):
        horizons[name] = {"advisors": {
            "MT5_CANDLES": _advisor(*mt5), "API_CANDLES": _advisor(*api),
            "MT5_TICK_FLOW": _advisor(*tick)},
            "suggested_levels": {"sl": 3990.0, "tp1": 4005.0, "tp2": 4010.0, "tp3": 4020.0},
            "valid_until": "2026-08-11T12:00:00+00:00"}
    return {"data_blocks": [], "horizons": horizons}


class ContinuousEntryTests(unittest.TestCase):
    def build(self, consensus):
        return _build(consensus, market_context={'SCALP': dict(available=True, atr=2., bid=4000., ask=4000.2)})

    def test_advisor1_scalp_wins_over_opposing_tick_flow(self):
        decisions = self.build(_consensus(('SELL', 95), ('SELL', 95), ('BUY', 50)))
        self.assertTrue(decisions['SCALP']['allowed'])
        self.assertEqual(decisions['SCALP']['direction'], 'SELL')
        self.assertEqual(decisions['SCALP']['evidence'], 95)
        self.assertEqual(decisions['SCALP']['levels']['source'], 'ADVISOR1_SCALP')

    def test_exact_fifteen_is_allowed(self):
        decisions = self.build(_consensus(('BUY', 15), ('BUY', 15), ('BUY', 15)))
        self.assertTrue(all(item['allowed'] for item in decisions.values()))

    def test_all_very_weak_pause_entries(self):
        decisions = self.build(_consensus(('BUY', 14.9), ('BUY', 14.9), ('BUY', 14.9)))
        self.assertTrue(all(item['all_lanes_very_weak'] and not item['allowed'] for item in decisions.values()))

    def test_single_usable_candle_source_can_authorize_its_lane(self):
        decisions = self.build(_consensus(('BUY', 50), ('WAIT', 0), ('WAIT', 0)))
        self.assertTrue(decisions['INTRADAY']['allowed'])
        self.assertTrue(decisions['SCALP']['allowed'])

    def test_missing_tick_flow_does_not_override_advisor1(self):
        consensus = _consensus(('BUY', 90), ('BUY', 90), ('BUY', 90))
        consensus['horizons']['SCALP']['advisors']['MT5_TICK_FLOW']['source_usable'] = False
        self.assertTrue(self.build(consensus)['SCALP']['allowed'])

    def test_unusable_advisor1_cannot_be_replaced_by_tick_flow(self):
        consensus = _consensus(('BUY', 90), ('BUY', 90), ('BUY', 90))
        consensus['horizons']['SCALP']['advisors']['MT5_CANDLES']['source_usable'] = False
        self.assertFalse(self.build(consensus)['SCALP']['allowed'])

    def test_advisor1_score_and_levels_are_preserved(self):
        consensus = _consensus(('BUY', 78.33), ('SELL', 99), ('SELL', 99))
        decision = self.build(consensus)['SCALP']
        self.assertTrue(decision['allowed'])
        self.assertEqual(decision['evidence'], 78.33)
        self.assertEqual(decision['take_profit'], 4005)
        self.assertEqual(decision['stop_loss'], 3990)
        self.assertEqual(decision['strong_advisors'], ['MT5_CANDLES'])

    def test_news_protection_still_blocks_continuous_entries(self):
        decisions = _build(_consensus(('BUY', 90), ('BUY', 90), ('BUY', 90)),
                           news_risk={'allowed': False, 'block_reasons': ['News window']},
                           market_context={'SCALP': dict(available=True, atr=2., bid=4000., ask=4000.2)})
        self.assertTrue(all(not item['allowed'] for item in decisions.values()))

    def test_missing_levels_still_blocks(self):
        consensus = _consensus(('BUY', 50), ('WAIT', 0), ('WAIT', 0))
        consensus['horizons']['INTRADAY']['advisors']['MT5_CANDLES']['levels'] = {}
        self.assertFalse(self.build(consensus)['INTRADAY']['allowed'])


class GoldHorizonPolicyTests(unittest.TestCase):
    def test_strong_bias_can_enter_when_action_is_wait(self) -> None:
        decisions = build_horizon_decisions(_consensus(("BUY", 88), ("BUY", 86), ("BUY", 90)))
        self.assertTrue(decisions["SCALP"]["allowed"])
        self.assertEqual(decisions["SCALP"]["direction"], "BUY")

    def test_two_strong_advisors_override_one_heavily_weighted_advisor(self) -> None:
        decisions = build_horizon_decisions(_consensus(("SELL", 95), ("SELL", 95), ("BUY", 90)))
        self.assertEqual(decisions["SCALP"]["dominant_bias"], "BUY")
        self.assertFalse(decisions["SCALP"]["allowed"])
        self.assertIn("Slower structure opposes", decisions["SCALP"]["blocks"][0])
        self.assertEqual(decisions["INTRADAY"]["dominant_bias"], "SELL")
        self.assertTrue(decisions["INTRADAY"]["allowed"])

    def test_intraday_and_swing_require_both_independent_candle_feeds(self) -> None:
        decisions = build_horizon_decisions(_consensus(("BUY", 95), ("WAIT", 0), ("BUY", 95)))
        self.assertTrue(decisions["SCALP"]["allowed"])
        self.assertFalse(decisions["INTRADAY"]["allowed"])
        self.assertFalse(decisions["SWING"]["allowed"])

    def test_stale_optional_api_does_not_disable_scalp(self) -> None:
        consensus = _consensus(("BUY", 92), ("BUY", 92), ("BUY", 92))
        consensus["source_blocks"] = {"API_CANDLES": ["API unavailable"]}
        for horizon in consensus["horizons"].values():
            horizon["advisors"]["API_CANDLES"]["source_usable"] = False
        decisions = build_horizon_decisions(consensus)
        self.assertTrue(decisions["SCALP"]["allowed"])
        self.assertFalse(decisions["INTRADAY"]["allowed"])

    def test_entry_confirmation_uses_elapsed_time_and_stricter_add_rule(self) -> None:
        decision = {"allowed": True, "evidence": 88.0}
        config = {"minimum_signal_seconds": 5, "add_position_evidence": 90,
                  "add_position_spacing_seconds": 15}
        self.assertFalse(evaluate_entry_timing(
            decision, open_position_count=0, signal_age_seconds=4.9,
            seconds_since_last_entry=999, lane_config=config)[0])
        self.assertTrue(evaluate_entry_timing(
            decision, open_position_count=0, signal_age_seconds=5.0,
            seconds_since_last_entry=999, lane_config=config)[0])
        self.assertFalse(evaluate_entry_timing(
            decision, open_position_count=1, signal_age_seconds=20,
            seconds_since_last_entry=20, lane_config=config)[0])

    def test_flow_authorizes_scalp_below_structure_veto_but_not_slower_lanes(self) -> None:
        decisions = build_horizon_decisions(_consensus(("SELL", 70), ("SELL", 70), ("BUY", 95)))
        self.assertEqual(decisions["SCALP"]["dominant_bias"], "BUY")
        self.assertTrue(decisions["SCALP"]["allowed"])
        self.assertEqual(decisions["SCALP"]["strong_advisor_count"], 1)
        self.assertFalse(decisions['INTRADAY']['allowed'])
        self.assertFalse(decisions['SWING']['allowed'])

    def test_each_horizon_uses_a_different_atr_target(self) -> None:
        decisions = build_horizon_decisions(_consensus(("BUY", 90), ("BUY", 90), ("BUY", 90)))
        self.assertEqual(decisions["SCALP"]["take_profit"], 4001.4)
        self.assertEqual(decisions["INTRADAY"]["take_profit"], 4010.0)
        self.assertEqual(decisions["SWING"]["take_profit"], 4020.0)

    def test_news_closes_fast_lanes_but_only_blocks_new_swing_entry(self) -> None:
        risk = {"allowed": False, "block_reasons": ["CPI window"], "active_events": []}
        decisions = build_horizon_decisions(_consensus(("BUY", 90), ("BUY", 90), ("BUY", 90)), risk)
        self.assertTrue(should_close_horizon(decisions["SCALP"], "BUY")[0])
        self.assertTrue(should_close_horizon(decisions["INTRADAY"], "BUY")[0])
        self.assertFalse(should_close_horizon(decisions["SWING"], "BUY")[0])

    def test_weak_scalp_bias_is_never_deterministically_inverted(self) -> None:
        decisions = build_horizon_decisions(_consensus(("BUY", 59), ("BUY", 59), ("BUY", 59)))
        scalp = decisions["SCALP"]
        self.assertFalse(scalp["allowed"])
        self.assertEqual(scalp["direction"], "WAIT")
        self.assertFalse(scalp["inverse_active"])

    def test_weak_scalp_bias_from_only_one_advisor_cannot_invert(self) -> None:
        decisions = build_horizon_decisions(_consensus(("WAIT", 0), ("WAIT", 0), ("BUY", 59)))
        self.assertFalse(decisions["SCALP"]["allowed"])
        self.assertFalse(decisions["SCALP"]["inverse_active"])

    def test_strong_fresh_economic_conflict_blocks_swing_not_scalp(self) -> None:
        economic = {"horizons": {
            "SCALP": {"bias": "SELL", "score": -0.8, "quality": 0.9},
            "INTRADAY": {"bias": "SELL", "score": -0.8, "quality": 0.9},
            "SWING": {"bias": "SELL", "score": -0.8, "quality": 0.9},
        }}
        decisions = build_horizon_decisions(
            _consensus(("BUY", 90), ("BUY", 90), ("BUY", 90)), economic_advisor=economic)
        self.assertTrue(decisions["SCALP"]["allowed"])
        self.assertFalse(decisions["INTRADAY"]["allowed"])
        self.assertFalse(decisions["SWING"]["allowed"])

    def test_economic_context_cannot_authorize_weak_technicals(self) -> None:
        economic = {"horizons": {name: {"bias": "BUY", "score": 1.0, "quality": 1.0}
                                  for name in ("SCALP", "INTRADAY", "SWING")}}
        decisions = build_horizon_decisions(
            _consensus(("BUY", 59), ("BUY", 59), ("BUY", 59)), economic_advisor=economic)
        self.assertTrue(all(not item["allowed"] for item in decisions.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
