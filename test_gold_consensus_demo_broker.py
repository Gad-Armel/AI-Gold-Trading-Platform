from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from services.execution.gold_consensus_demo_broker import (
    align_positions_to_consensus,
    basket_floating_profit,
    execution_safety,
    exposure_slots,
    open_consensus_position,
    recent_closed_consensus_trades,
    session_profit,
    horizon_floating_profit,
    open_horizon_position,
    close_horizon_positions,
)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PLACED = 10008
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 3
    DEAL_TYPE_BUY = 0

    def __init__(self) -> None:
        self.positions: list[SimpleNamespace] | None = []
        self.sent: list[dict] = []
        self.deals: list[SimpleNamespace] | None = []
        now_msc = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.tick = SimpleNamespace(bid=4000.0, ask=4000.2, time_msc=now_msc, time=now_msc // 1000)
        self.info = SimpleNamespace(visible=True, volume_min=0.01, volume_max=10.0, volume_step=0.01,
                                    filling_mode=1, trade_exemode=0, trade_contract_size=100.0, point=0.01)

    def account_info(self):
        return SimpleNamespace(trade_mode=0, login=1, server="Demo", trade_allowed=True, trade_expert=True, margin_mode=2, currency='USD')

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True, tradeapi_disabled=False)

    def positions_get(self, **_kwargs):
        return None if self.positions is None else tuple(self.positions)

    def symbol_info(self, _symbol):
        return self.info

    def symbol_info_tick(self, _symbol):
        return self.tick

    def symbol_select(self, _symbol, _enabled):
        return True

    def order_check(self, _request):
        return SimpleNamespace(retcode=0, comment="ok")

    def order_calc_profit(self, direction, symbol, volume, price, exit_price):
        return (exit_price-price)*volume*100*(1 if direction==0 else -1)

    def order_send(self, request):
        self.sent.append(request)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="done", order=10, deal=11)

    def history_deals_get(self, _start, _end):
        return None if self.deals is None else tuple(self.deals)

    def last_error(self):
        return (0, "ok")


def position(*, volume: float = 0.01, direction: int = 0, magic: int = 631005, ticket: int = 1,
             profit: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(volume=volume, type=direction, magic=magic, ticket=ticket, profit=profit)


class GoldConsensusDemoBrokerTests(unittest.TestCase):
    @patch('services.execution.gold_consensus_demo_broker._journal')
    def test_broker_close_only_blocks_new_entries_without_sending(self, journal):
        mt5 = FakeMT5()
        mt5.info.trade_mode = 3
        result = open_horizon_position(mt5, 'SCALP', dict(allowed=True,
            direction='BUY', take_profit=4004., stop_loss=3998.))
        self.assertEqual(result['action'], 'SYMBOL_SESSION_BLOCK')
        self.assertFalse(mt5.sent)

    @patch('services.execution.gold_consensus_demo_broker._journal')
    def test_quote_changed_during_order_check_prevents_submission(self, journal):
        mt5 = FakeMT5()
        def check(request):
            mt5.tick.bid += 1.
            mt5.tick.ask += 1.
            return SimpleNamespace(retcode=0, comment='ok')
        with patch.object(mt5, 'order_check', side_effect=check):
            result = open_horizon_position(mt5, 'SCALP', dict(allowed=True,
                direction='BUY', take_profit=4004., stop_loss=3998.))
        self.assertEqual(result['action'], 'FINAL_QUOTE_BLOCK')
        self.assertEqual(mt5.sent, [])

    @patch('services.execution.gold_consensus_demo_broker._journal')
    def test_horizon_audit_distinguishes_requested_and_broker_reported_price(self, journal):
        mt5 = FakeMT5()
        decision = dict(allowed=True, direction='BUY', take_profit=4004, stop_loss=3998,
                        m1_sequence_quality=dict(available=True, execution_enabled=False, spread_atr=.1),
                        staged_m1_observation=dict(required_bars=5, execution_enabled=True),
                        s30_shadow=dict(direction='BUY', execution_enabled=False),
                        candle_input_health=dict(available=True),
                        entry_observation=dict(signal_age_seconds=2.1, micro_flow=dict(available=False, reason='Warming up')),
                        evidence=80, contributors=[dict(advisor='MT5_CANDLES', source_usable=True,
                                                       valid_until='2026-10-08T14:00:00+00:00')],
                        candle_confirmation=dict(pending=False))
        with patch.object(mt5, 'order_send', return_value=SimpleNamespace(
                retcode=mt5.TRADE_RETCODE_DONE, comment='done', order=10, deal=11,
                price=4000.55, volume=.01)):
            result = open_horizon_position(mt5, 'SCALP', decision)
        self.assertTrue(result['success'])
        record = journal.call_args.args[0]
        self.assertEqual(record['entry_price'], mt5.tick.ask)
        self.assertEqual(record['broker_reported_price'], 4000.55)
        self.assertEqual(record['broker_reported_volume'], .01)
        self.assertEqual(record['entry_context']['quote']['bid'], mt5.tick.bid)
        self.assertEqual(record['entry_context']['decision']['contributors'], decision['contributors'])
        self.assertEqual(record['entry_context']['decision']['entry_observation'], decision['entry_observation'])
        for field in ('m1_sequence_quality', 'staged_m1_observation', 's30_shadow', 'candle_input_health'):
            self.assertEqual(record['entry_context']['decision'][field], decision[field])
        self.assertEqual(record['entry_context']['decision']['candle_confirmation'], dict(pending=False))

    @patch('services.execution.gold_consensus_demo_broker._journal')
    def test_horizon_audit_does_not_invent_missing_broker_fill_price(self, journal):
        result = open_horizon_position(FakeMT5(), 'SCALP', dict(
            allowed=True, direction='BUY', take_profit=4004, stop_loss=3998))
        self.assertTrue(result['success'])
        self.assertIsNone(journal.call_args.args[0]['broker_reported_price'])

    def test_shared_empty_history_snapshot_does_not_refetch(self):
        mt5 = FakeMT5()
        with patch.object(mt5, 'history_deals_get', side_effect=AssertionError('Duplicate broker history request')):
            for magic in (631011, 631012, 631013):
                self.assertEqual(recent_closed_consensus_trades(mt5, magic_number=magic, deals_snapshot=()), [])

    def test_five_positions_block_sixth_but_allow_management_startup(self):
        mt5=FakeMT5();mt5.positions=[position(magic=631011,ticket=ticket) for ticket in range(1, 6)]
        self.assertTrue(execution_safety(mt5)[0])
        result=open_horizon_position(mt5,'SCALP',dict(allowed=True,direction='BUY'))
        self.assertEqual(result['action'],'POSITION_CAP')
        self.assertEqual(mt5.sent,[])

    def test_three_position_account_cap_blocks_fourth_entry(self):
        from services.execution.gold_consensus_demo_broker import _entry_capacity_block
        mt5 = FakeMT5()
        mt5.positions = [position(magic=631011, ticket=ticket) for ticket in range(1, 4)]
        self.assertEqual(_entry_capacity_block(mt5)['action'], 'POSITION_CAP')
        mt5.positions[0].volume = .02
        self.assertEqual(_entry_capacity_block(mt5)['action'], 'POSITION_CAP')
        mt5.positions[0].volume = .01
        mt5.positions.append(position(magic=631011, ticket=4))
        self.assertEqual(_entry_capacity_block(mt5)['action'], 'POSITION_CAP')
        self.assertEqual(mt5.sent, [])

    @patch('services.execution.gold_consensus_demo_broker._journal')
    def test_third_position_in_another_lane_uses_exactly_point_zero_one(self,_journal):
        mt5=FakeMT5();mt5.positions=[position(magic=631011,ticket=1),position(magic=631013,ticket=2)]
        result=open_horizon_position(mt5,'INTRADAY',dict(allowed=True,direction='BUY',take_profit=4004,stop_loss=3998))
        self.assertTrue(result['success']);self.assertEqual(mt5.sent[0]['volume'],.01)

    def test_risk_budget_rejects_wide_structural_stop(self):
        mt5=FakeMT5()
        with patch('config.gold_consensus_settings.MAX_TRADE_RISK_USD', 4):
            result=open_horizon_position(mt5,'SWING',dict(allowed=True,direction='BUY',take_profit=4010,stop_loss=3995))
        self.assertEqual(result['action'],'RISK_BUDGET_BLOCK');self.assertEqual(mt5.sent,[])

    @patch('services.execution.gold_consensus_demo_broker._journal')
    def test_every_lane_has_individual_five_dollar_broker_stop(self, _journal):
        for lane in ('SCALP', 'INTRADAY', 'SWING'):
            for direction in ('BUY', 'SELL'):
                mt5 = FakeMT5()
                buy = direction == 'BUY'
                result = open_horizon_position(mt5, lane, dict(allowed=True, direction=direction,
                    take_profit=4010 if buy else 3990, stop_loss=3995 if buy else 4005))
                self.assertTrue(result['success'], result)
                request = mt5.sent[-1]
                loss = mt5.order_calc_profit(request['type'], 'XAUUSD', request['volume'], request['price'], request['sl'])
                self.assertAlmostEqual(loss, -5, places=2)
                self.assertEqual(request['volume'], .01)

    def test_volume_cannot_be_rounded_down_or_configured_up(self):
        mt5=FakeMT5();mt5.info.volume_min=.003;mt5.info.volume_step=.003
        result=open_horizon_position(mt5,'SCALP',dict(allowed=True,direction='BUY'))
        self.assertEqual(result['action'],'VOLUME_BLOCK')
        with patch('config.gold_consensus_settings.LOT_SIZE',.02):
            self.assertFalse(execution_safety(FakeMT5())[0])

    def test_capacity_rechecked_after_order_check(self):
        mt5=FakeMT5()
        def check(_request):
            mt5.positions=[position(magic=631011,ticket=ticket) for ticket in range(1, 6)]
            return SimpleNamespace(retcode=0,comment='ok')
        mt5.order_check=check
        result=open_horizon_position(mt5,'INTRADAY',dict(allowed=True,direction='BUY',take_profit=4004,stop_loss=3998))
        self.assertEqual(result['action'],'POSITION_CAP');self.assertEqual(mt5.sent,[])

    def test_pending_order_appearing_during_check_blocks_another_send(self):
        mt5 = FakeMT5()
        pending = []
        mt5.orders_get = lambda **kwargs: tuple(pending)

        def check(request):
            pending.append(SimpleNamespace(magic=631011))
            return SimpleNamespace(retcode=0, comment='ok')

        mt5.order_check = check
        result = open_horizon_position(mt5, 'SCALP', dict(allowed=True, direction='BUY', take_profit=4004, stop_loss=3998))
        self.assertEqual(result['action'], 'ENTRY_BLOCKED')
        self.assertEqual(mt5.sent, [])

    def test_manual_exit_keeps_controlled_position_costs_in_pnl(self):
        mt5=FakeMT5()
        mt5.deals=[SimpleNamespace(magic=631012,position_id=7,profit=0,commission=-.2),
                   SimpleNamespace(magic=0,position_id=7,profit=-3,commission=-.2),
                   SimpleNamespace(magic=0,position_id=9,profit=100,commission=0)]
        result=session_profit(mt5,datetime.now(timezone.utc))
        self.assertAlmostEqual(result['realized'],-3.4)

    def test_pending_order_prevents_duplicate_entry(self):
        mt5=FakeMT5();mt5.orders_get=lambda **kwargs:(SimpleNamespace(magic=631012),)
        allowed,reasons=execution_safety(mt5)
        self.assertFalse(allowed)
        self.assertTrue(any('pending' in r for r in reasons))

    def test_absolute_spread_limit_applies_even_with_distant_target(self):
        from config import gold_consensus_settings as settings
        mt5=FakeMT5();mt5.tick.ask=4000+settings.MAX_SPREAD_USD+0.05
        result=open_horizon_position(mt5,'SCALP',dict(allowed=True,direction='BUY',take_profit=4050,stop_loss=3990))
        self.assertEqual(result['action'],'COST_BLOCK')
        self.assertEqual(mt5.sent,[])

    @patch('services.execution.gold_consensus_demo_broker._journal')
    def test_profit_lock_closes_only_selected_owned_scalp_ticket(self, _journal):
        mt5 = FakeMT5()
        mt5.positions = [SimpleNamespace(ticket=t, magic=631011, type=0, volume=.01)
                         for t in (7, 8)]
        result = close_horizon_positions(mt5, 'SCALP', reason='Profit lock', tickets=[7, 99])
        self.assertEqual(result['closed_count'], 1)
        self.assertEqual([r['position'] for r in mt5.sent], [7])

    def test_session_query_uses_aware_utc_end_and_counts_swap(self):
        mt5 = FakeMT5()
        seen = []
        mt5.history_deals_get = lambda start, end: seen.append((start, end)) or ()
        mt5.positions = [SimpleNamespace(magic=631012, profit=2.0, swap=-0.5)]
        result = session_profit(mt5, datetime.now(timezone.utc))
        self.assertEqual(seen[0][1].tzinfo, timezone.utc)
        self.assertEqual(result['floating'], 1.5)

    def test_horizon_profit_failure_is_not_zero_exposure(self):
        mt5 = FakeMT5(); mt5.positions = None
        self.assertFalse(horizon_floating_profit(mt5, 'INTRADAY')['available'])

    def setUp(self) -> None:
        # Generic legacy execution tests exercise all lanes explicitly; the
        # deployed SCALP-only permission is covered by dedicated mode tests.
        from config import gold_consensus_settings as settings
        pairing = patch('config.gold_inverse_settings.PAIRING_ENABLED', False)
        pairing.start(); self.addCleanup(pairing.stop)
        fixed = patch.dict(settings.HORIZON_LANES['SCALP'], stop_mode='INDIVIDUAL', individual_stop_loss_usd=5.0)
        fixed.start(); self.addCleanup(fixed.stop)
        for name in ('INTRADAY', 'SWING'):
            enabled = patch.dict(settings.HORIZON_LANES[name], trade_enabled=True)
            enabled.start(); self.addCleanup(enabled.stop)
        clock_patch = patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0)
        clock_patch.start(); self.addCleanup(clock_patch.stop)
        self.identity = patch(
            "services.execution.gold_consensus_demo_broker.validate_demo_session_identity",
            return_value=(True, "demo"),
        )
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def test_position_read_failure_blocks_entry_safety(self) -> None:
        mt5 = FakeMT5()
        mt5.positions = None
        allowed, reasons = execution_safety(mt5)
        self.assertFalse(allowed)
        self.assertTrue(any("Unable to read MT5 positions" in reason for reason in reasons))

    def test_netting_account_is_blocked(self) -> None:
        mt5 = FakeMT5()
        mt5.account_info = lambda: SimpleNamespace(
            trade_mode=0, login=1, server="Demo", trade_allowed=True, trade_expert=True, margin_mode=0
        )
        allowed, reasons = execution_safety(mt5)
        self.assertFalse(allowed)
        self.assertTrue(any("hedging account" in reason for reason in reasons))

    def test_total_volume_is_converted_to_slots(self) -> None:
        mt5 = FakeMT5()
        mt5.positions = [position(volume=0.05)]
        self.assertEqual(exposure_slots(mt5), 5)

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_five_slot_cap_blocks_order(self, _journal) -> None:
        mt5 = FakeMT5()
        mt5.positions = [position(volume=0.05)]
        result = open_consensus_position(mt5, "BUY", {"allowed": True, "evidence": 90})
        self.assertEqual(result["action"], "POSITION_CAP")
        self.assertEqual(mt5.sent, [])

    def test_basket_profit_sums_only_consensus_positions(self) -> None:
        mt5 = FakeMT5()
        mt5.positions = [position(ticket=1, profit=6.0), position(ticket=2, profit=4.0),
                         position(ticket=3, profit=99.0, magic=99)]
        basket = basket_floating_profit(mt5)
        self.assertTrue(basket["available"])
        self.assertEqual(basket["position_count"], 2)
        self.assertEqual(basket["profit"], 10.0)

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_stale_tick_blocks_order(self, _journal) -> None:
        mt5 = FakeMT5()
        mt5.tick.time_msc -= 10_000
        result = open_consensus_position(mt5, "BUY", {"allowed": True, "evidence": 90})
        self.assertEqual(result["action"], "QUOTE_BLOCK")
        self.assertEqual(mt5.sent, [])

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_wide_spread_does_not_vote_or_block_demo_entry(self, _journal) -> None:
        mt5 = FakeMT5()
        mt5.tick.ask = mt5.tick.bid + 5.0
        result = open_consensus_position(mt5, "BUY", {"allowed": True, "evidence": 90})
        self.assertNotEqual(result["action"], "SPREAD_BLOCK")

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_wait_closes_only_consensus_position(self, _journal) -> None:
        mt5 = FakeMT5()
        own = position(ticket=1)
        external = position(ticket=2, magic=99)
        mt5.positions = [own, external]
        result = align_positions_to_consensus(mt5, {"allowed": False, "direction": "WAIT"})
        self.assertEqual(result["closed_count"], 1)
        self.assertEqual(len(mt5.sent), 1)
        self.assertEqual(mt5.sent[0]["position"], 1)

    def test_session_profit_includes_costs_and_floating(self) -> None:
        mt5 = FakeMT5()
        mt5.deals = [SimpleNamespace(magic=631011, profit=-5.0, commission=-0.2, swap=0.0, fee=0.0)]
        mt5.positions = [position(profit=-1.5, magic=631011)]
        result = session_profit(mt5, datetime.now(timezone.utc))
        self.assertTrue(result["available"])
        self.assertAlmostEqual(float(result["total"]), -6.7)

    def test_session_profit_excludes_retired_legacy_consensus_magic(self) -> None:
        mt5 = FakeMT5()
        mt5.deals = [SimpleNamespace(magic=631005, profit=-602.72, commission=0.0, swap=0.0, fee=0.0)]
        mt5.positions = []
        result = session_profit(mt5, datetime.now(timezone.utc))
        self.assertEqual(float(result["total"]), 0.0)

    def test_horizon_floating_profit_is_isolated_by_lane(self) -> None:
        mt5 = FakeMT5()
        mt5.positions = [position(magic=631011, profit=3.0), position(magic=631011, profit=2.1),
                         position(magic=631012, profit=99.0)]
        result = horizon_floating_profit(mt5, "SCALP")
        self.assertEqual(result["position_count"], 2)
        self.assertEqual(result["profit"], 5.1)

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_horizon_order_has_cumulative_tp_and_broker_side_sl(self, _journal) -> None:
        mt5 = FakeMT5()
        result = open_horizon_position(mt5, "SCALP", {"allowed": True, "direction": "BUY",
            "take_profit": 4002.0, "stop_loss": 3999.0, "evidence": 90.0})
        self.assertTrue(result["success"])
        self.assertEqual(mt5.sent[0]["tp"], 0.0)
        self.assertAlmostEqual(mt5.sent[0]["sl"], 3995.2, places=2)

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_horizon_entry_blocks_when_spread_consumes_target(self, _journal) -> None:
        mt5 = FakeMT5()
        mt5.tick.ask = 4001.5
        result = open_horizon_position(mt5, "SCALP", {"allowed": True, "direction": "BUY",
            "take_profit": 4002.0, "stop_loss": 3998.0, "evidence": 95.0})
        self.assertEqual(result["action"], "COST_BLOCK")
        self.assertEqual(mt5.sent, [])

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_horizon_entry_blocks_poor_analysed_reward_risk(self, _journal) -> None:
        mt5 = FakeMT5()
        result = open_horizon_position(mt5, "SCALP", {"allowed": True, "direction": "BUY",
            "take_profit": 4001.0, "stop_loss": 3990.0, "evidence": 95.0})
        self.assertEqual(result["action"], "RISK_REWARD_BLOCK")

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_horizon_entry_respects_analysis_entry_zone(self, _journal) -> None:
        mt5 = FakeMT5()
        result = open_horizon_position(mt5, "SCALP", {"allowed": True, "direction": "BUY",
            "take_profit": 4002.0, "stop_loss": 3998.0, "evidence": 95.0,
            "levels": {"entry_zone": [3990.0, 3991.0]}})
        self.assertEqual(result["action"], "ENTRY_ZONE_BLOCK")

    @patch("services.execution.gold_consensus_demo_broker._journal")
    def test_intraday_uses_five_dollar_individual_stop(self, _journal) -> None:
        mt5 = FakeMT5()
        result = open_horizon_position(mt5, "INTRADAY", {"allowed": True, "direction": "BUY",
            "take_profit": 4002.0, "stop_loss": 3998.0, "evidence": 90.0})
        self.assertTrue(result["success"])
        self.assertEqual(mt5.sent[0]["volume"], 0.01)
        self.assertAlmostEqual(mt5.sent[0]["sl"], 3995.2, places=2)

    def test_closed_history_keeps_only_latest_fifty(self) -> None:
        mt5 = FakeMT5()
        base = int(datetime.now(timezone.utc).timestamp() * 1000) - 120_000
        deals = []
        for position_id in range(1, 61):
            deals.append(SimpleNamespace(magic=631005, position_id=position_id, entry=0, type=0,
                volume=0.01, price=4000.0, time_msc=base + position_id * 1000,
                profit=0.0, commission=-0.1, swap=0.0, fee=0.0, comment="open"))
            deals.append(SimpleNamespace(magic=631005, position_id=position_id, entry=1, type=1,
                volume=0.01, price=4001.0, time_msc=base + position_id * 1000 + 500,
                profit=float(position_id), commission=-0.1, swap=0.0, fee=0.0, comment="tp"))
        mt5.deals = deals
        history = recent_closed_consensus_trades(mt5, limit=50)
        self.assertEqual(len(history), 50)
        self.assertEqual(history[0]["position_id"], 60)
        self.assertEqual(history[-1]["position_id"], 11)
        self.assertEqual(history[0]["direction"], "BUY")
        self.assertAlmostEqual(history[0]["profit"], 59.8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
