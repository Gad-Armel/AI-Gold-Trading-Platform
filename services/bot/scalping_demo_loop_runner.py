from __future__ import annotations

import time
from typing import Any

from config import scalping_settings
from services.bot.emergency_stop import check_emergency_stop
from services.bot.scalping_demo_cycle_runner import run_scalping_demo_cycle
from services.execution.scalp_demo_position_manager import close_all_demo_scalp_positions
from services.microstructure.feature_store import flush_microstructure_features
from services.microstructure.tick_recorder import flush_tick_recorder


def run_scalping_demo_loop(symbol: str, *, max_minutes: float | None = None, mt5_module: Any | None = None) -> None:
    if mt5_module is None:
        import MetaTrader5 as mt5_module  # type: ignore
    duration = float(max_minutes if max_minutes is not None else scalping_settings.SCALPING_DEMO_MAX_SESSION_MINUTES)
    print("")
    print("=" * 70)
    print("CONTROLLED XAUUSD MT5 DEMO — V6.3 STRICT + CALIBRATED MODEL APPROVAL ONLY")
    print("=" * 70)
    print("Orders require a valid, unexpired V6 walk-forward approval and a locked MT5 DEMO account.")
    print(f"Symbol: {symbol} | Lot: {scalping_settings.SCALPING_LOT_SIZE:.2f}")
    print(f"Maximum positions: {scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS}")
    print("Daily trade-count limit: DISABLED")
    print(f"Cumulative loss-session stop: -${scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD:.2f} (no midnight reset)")
    print(
        f"Cooldown: after {scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES} "
        f"consecutive losses for {scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS:.0f}s"
    )
    print(f"Session limit: {duration:.0f} minute(s)")
    print("=" * 70)

    cycle = 0
    started = time.monotonic()
    try:
        while True:
            stopped, reason = check_emergency_stop()
            if stopped:
                print(reason)
                break
            if duration > 0 and time.monotonic() - started >= duration * 60.0:
                print("Controlled demo session time limit reached.")
                break
            cycle += 1
            cycle_started = time.monotonic()
            result = run_scalping_demo_cycle(symbol, mt5_module=mt5_module)
            if not result.get("success"):
                print(f"FATAL DEMO SESSION BLOCK: {result.get('message', '')}")
                break
            snapshot = result["snapshot"]
            signal = result["signal"]
            risk = result["risk"]
            micro = result.get("microstructure", {})
            meta = result.get("meta_controller", {})
            print("")
            metrics = signal.metrics if isinstance(signal.metrics, dict) else {}
            buy_score = float(metrics.get("buy_score", 0.0) or 0.0)
            sell_score = float(metrics.get("sell_score", 0.0) or 0.0)
            score_margin = abs(buy_score - sell_score)
            tick_status = result.get("tick_recorder", {})
            cursor = tick_status.get("cursor", {}) if isinstance(tick_status, dict) else {}
            storage = tick_status.get("storage", {}) if isinstance(tick_status, dict) else {}
            print(
                f"Demo Cycle {cycle} | Bid={snapshot.bid:.5f} Ask={snapshot.ask:.5f} "
                f"Spread={snapshot.spread:.3f} | QuoteAge={float(getattr(snapshot, 'quote_age_seconds', 0.0) or 0.0):.1f}s"
            )
            print(
                f"Signal: {signal.action} | Allowed={signal.allowed} | Score={signal.score:.1f} | "
                f"BUY={buy_score:.1f} SELL={sell_score:.1f} Margin={score_margin:.1f} | Pattern={signal.pattern}"
            )
            print(
                f"Microstructure: {micro.get('direction', 'NEUTRAL')}/"
                f"{float(micro.get('confidence', 0.0) or 0.0):.2f} | "
                f"Meta allowed={meta.get('allowed', False)} mode={meta.get('entry_mode', 'WAIT')}"
            )
            persistence = result.get("signal_persistence", {}) or {}
            print(
                f"Signal Persistence: passed={bool(persistence.get('passed', False))} "
                f"streak={int(persistence.get('consecutive_cycles', 0) or 0)} "
                f"required={int(persistence.get('minimum_cycles', 0) or 0)} "
                f"elapsed={float(persistence.get('elapsed_seconds', 0.0) or 0.0):.2f}s/"
                f"{float(persistence.get('minimum_seconds', 0.0) or 0.0):.2f}s "
                f"instant={bool(persistence.get('instant_override', False))}"
            )
            print(
                f"Tick Feed: captured={int(tick_status.get('captured', 0) or 0)} "
                f"recent={int(tick_status.get('recent_tick_count', 0) or 0)} "
                f"resynced={bool(cursor.get('cursor_resynced', False))} "
                f"cursor_lag={float(cursor.get('cursor_lag_before_seconds', 0.0) or 0.0):.1f}s "
                f"cursor_saved={bool(cursor.get('cursor_persisted', True))} "
                f"pending={int(storage.get('buffered_rows', 0) or 0)}"
            )
            cursor_warning = str(cursor.get("cursor_write_error", "") or "").strip()
            if cursor_warning:
                print(
                    "Cursor Warning: persistence was temporarily unavailable; "
                    "the in-memory cursor remains active and the runner will continue. "
                    + cursor_warning
                )
            print(f"Risk: {'ALLOWED' if risk.get('allowed') else 'BLOCKED'} | session trades={risk.get('session_trade_count', 0)} realized=${float(risk.get('session_realized_profit', 0.0)):.2f} total=${float(risk.get('session_total_profit', 0.0)):.2f} cooldown={float(risk.get('loss_cooldown_remaining_seconds', 0.0)):.1f}s")
            if bool(risk.get("loss_recovery_mode", False)):
                checks = risk.get("loss_recovery_checks", {}) or {}
                failed = [name for name, passed in checks.items() if not passed]
                print(
                    "Loss Recovery: ACTIVE | "
                    + ("ready" if not failed else "waiting for " + ", ".join(failed))
                )
            spread_policy = risk.get("spread_policy", {}) if isinstance(risk, dict) else {}
            if spread_policy:
                print(
                    f"Spread Policy: {spread_policy.get('mode', 'REJECT')} | "
                    f"normal<=${float(spread_policy.get('normal_limit_usd', 0.0) or 0.0):.2f} "
                    f"hard<=${float(spread_policy.get('hard_limit_usd', 0.0) or 0.0):.2f} | "
                    f"spread/target={float(spread_policy.get('spread_target_ratio', 0.0) or 0.0):.2f} "
                    f"spread/ATR={float(spread_policy.get('spread_atr_ratio', 0.0) or 0.0):.2f} "
                    f"R/R={float(spread_policy.get('reward_risk_ratio', 0.0) or 0.0):.2f}"
                )
            v6_gate = result.get("v6_candidate_gate", {}) or {}
            structure = result.get("v6_market_structure", {}) or {}
            if v6_gate:
                failed_gate = list(v6_gate.get("failed_checks", []) or [])
                print(
                    f"V6 Candidate Gate: allowed={bool(v6_gate.get('allowed', False))} "
                    f"direction={v6_gate.get('direction', 'NEUTRAL')} "
                    f"score={float(v6_gate.get('winner_score', 0.0) or 0.0):.1f} "
                    f"margin={float(v6_gate.get('score_margin', 0.0) or 0.0):.1f} "
                    f"failed={failed_gate or 'none'}"
                )
            if structure:
                families = structure.get("families", {}) or {}
                family_text = []
                for family_name in ("htf_trend", "support_resistance", "order_block"):
                    family = families.get(family_name, {}) if isinstance(families, dict) else {}
                    family_text.append(
                        f"{family_name}={family.get('direction', 'NEUTRAL')}/"
                        f"{float(family.get('confidence', 0.0) or 0.0):.2f}"
                    )
                print(
                    f"Structure Consensus: {structure.get('consensus_direction', 'NEUTRAL')} "
                    f"votes={int(structure.get('consensus_votes', 0) or 0)}/3 "
                    f"confidence={float(structure.get('confidence', 0.0) or 0.0):.2f} "
                    f"location_safe={bool(structure.get('location_safe', False))} "
                    f"room=${float(structure.get('room_to_target_usd', 0.0) or 0.0):.2f} | "
                    + " | ".join(family_text)
                )
            market_map = result.get("market_map", {}) or {}
            if market_map.get("rendered") and market_map.get("path"):
                print(f"Market Map: {market_map.get('path')}")
            all_blocks: list[str] = []
            for source in (
                list(getattr(signal, "block_reasons", []) or []),
                list(meta.get("block_reasons", []) or []),
                list(risk.get("block_reasons", []) or []),
            ):
                for reason in source:
                    text = str(reason).strip()
                    if text and text not in all_blocks:
                        all_blocks.append(text)
            if all_blocks:
                print("Blocks: " + " | ".join(all_blocks[:6]))
            print(f"Position Manager: {result['position_management']['message']}")
            print(f"Execution: {result['execution']['action']} — {result['execution']['message']}")
            if bool(risk.get("return_to_shadow_required", False)):
                print(
                    "V6 CONTROLLED-DEMO CIRCUIT BREAKER: approval revoked after three "
                    "consecutive losses. The runner will stop and must return to shadow calibration."
                )
                break
            if bool(risk.get("session_stop_required", False)):
                print(
                    "CONTROLLED DEMO TOTAL STOP: cumulative loss-session reached -$100. "
                    "The runner will flatten controlled demo positions, latch the stop, and require a manual reset."
                )
                break
            open_count = int(result["position_management"].get("open_position_count", 0) or 0)
            interval = float(scalping_settings.SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS if open_count else scalping_settings.SCALPING_LOOP_INTERVAL_SECONDS)
            time.sleep(max(0.0, interval - (time.monotonic() - cycle_started)))
    except KeyboardInterrupt:
        print("Controlled demo scalping loop stopped with CTRL+C.")
    finally:
        if bool(scalping_settings.SCALPING_DEMO_CLOSE_POSITIONS_ON_RUNNER_STOP):
            closed = close_all_demo_scalp_positions(mt5_module=mt5_module)
            print("")
            print("DEMO SHUTDOWN PROTECTION")
            print(f"Positions found/closed: {closed.get('found_count', 0)}/{closed.get('closed_count', 0)}")
            print(closed.get("message", ""))
        tick_flush = flush_tick_recorder()
        feature_flush = flush_microstructure_features()
        print(
            "Research storage: "
            f"ticks_flushed_now={int(tick_flush.get('flushed_rows', 0) or 0)} "
            f"ticks_written_session={int(tick_flush.get('rows_written', 0) or 0)} "
            f"ticks_pending={int(tick_flush.get('buffered_rows', 0) or 0)} | "
            f"features_flushed_now={int(feature_flush.get('flushed_rows', 0) or 0)} "
            f"features_written_session={int(feature_flush.get('rows_written', 0) or 0)} "
            f"features_pending={int(feature_flush.get('buffered_rows', 0) or 0)}"
        )
