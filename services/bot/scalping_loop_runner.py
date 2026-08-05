from __future__ import annotations

import time
from datetime import datetime, timezone

from config import scalping_settings
from services.bot.emergency_stop import check_emergency_stop
from services.bot.scalping_cycle_runner import run_scalping_cycle
from services.bot.scalping_summary_printer import print_scalping_cycle_summary
from services.execution.execution_audit import (
    audit_paper_trade_transition,
    flush_execution_audit,
)
from services.execution.scalp_paper_trade_manager import (
    close_all_open_scalp_paper_trades,
)
from services.microstructure.feature_store import flush_microstructure_features
from services.microstructure.tick_recorder import flush_tick_recorder
from services.risk.scalping_risk_guard import load_scalping_trades


def run_scalping_loop(
    symbol: str,
    interval_seconds: float | None = None,
    max_cycles: int | None = None,
) -> None:
    interval = (
        float(interval_seconds)
        if interval_seconds is not None
        else float(scalping_settings.SCALPING_LOOP_INTERVAL_SECONDS)
    )
    open_position_interval = float(
        scalping_settings.SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS
    )

    configured_max = (
        int(max_cycles)
        if max_cycles is not None
        else int(scalping_settings.SCALPING_MAX_CYCLES)
    )
    cycle_limit = configured_max if configured_max > 0 else None

    print("")
    print("=" * 70)
    print("XAUUSD PAPER-SCALPING LOOP STARTED")
    print("=" * 70)
    print(f"Symbol: {symbol}")
    print(f"Strategy: {scalping_settings.SCALPING_STRATEGY_ID}")
    print(f"Log root: {scalping_settings.SCALPING_LOG_ROOT}")
    print(f"Idle entry-scan interval: {interval:.2f} second(s)")
    print(
        "Open-position monitoring interval: "
        f"{open_position_interval:.2f} second(s)"
    )
    print(f"Maximum cycles: {cycle_limit or 'Unlimited until CTRL+C'}")
    print(f"Maximum positions: {scalping_settings.SCALPING_MAX_OPEN_POSITIONS}")
    print(
        "Unified factor engine: "
        f"{'ON' if scalping_settings.SCALPING_UNIFIED_ATOME_FACTORS_ENABLED else 'OFF'}"
    )
    print(
        "Candle depth: "
        f"M1={scalping_settings.SCALPING_M1_CANDLES}, "
        f"M5={scalping_settings.SCALPING_M5_CANDLES}, "
        f"M15={scalping_settings.SCALPING_M15_CANDLES}, "
        f"H1={scalping_settings.SCALPING_H1_CANDLES}, "
        f"H4={scalping_settings.SCALPING_H4_CANDLES} "
        f"(minimum={scalping_settings.SCALPING_MIN_REQUIRED_CANDLES})"
    )
    print(
        "Candle cache policy: timeframe-boundary refresh + "
        f"live-M1 tick patch={'ON' if scalping_settings.SCALPING_PATCH_LIVE_M1_FROM_TICK else 'OFF'}"
    )
    print(
        "Required family gates: "
        f"entry-trigger={'ON' if scalping_settings.SCALPING_UNIFIED_REQUIRE_ENTRY_TRIGGER_FAMILY else 'OFF'} | "
        f"directional-context={'ON' if scalping_settings.SCALPING_UNIFIED_REQUIRE_DIRECTIONAL_CONTEXT_FAMILY else 'OFF'}"
    )
    print(
        "V5 tick recorder: "
        f"{'ON' if scalping_settings.SCALPING_TICK_RECORDER_ENABLED else 'OFF'} | "
        f"Parquet={scalping_settings.SCALPING_TICK_DATA_ROOT} | "
        f"flush={float(scalping_settings.SCALPING_TICK_FLUSH_INTERVAL_SECONDS):.1f}s"
    )
    print(
        "Microstructure windows: "
        f"{tuple(scalping_settings.SCALPING_MICROSTRUCTURE_WINDOWS_SECONDS)} | "
        f"minimum ticks={scalping_settings.SCALPING_MICROSTRUCTURE_MIN_TICKS} | "
        f"minimum quality={float(scalping_settings.SCALPING_MICROSTRUCTURE_MIN_DATA_QUALITY):.2f}"
    )
    print(
        "Agent meta-controller: "
        f"{'ON' if scalping_settings.SCALPING_META_CONTROLLER_ENABLED else 'OFF'} | "
        f"strict tick agreement={'ON' if scalping_settings.SCALPING_MICROSTRUCTURE_ENTRY_GATE_ENABLED else 'OFF'} | "
        "may veto only; cannot create a trade"
    )
    print(
        "Execution/slippage audit: "
        f"{'ON' if scalping_settings.SCALPING_EXECUTION_AUDIT_ENABLED else 'OFF'}"
    )
    print(
        "Entry spread ceiling: "
        f"${scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD:.2f}"
    )
    minimum_target = float(scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD)
    maximum_target = float(scalping_settings.SCALPING_MAX_PROFIT_TARGET_USD)
    if abs(minimum_target - maximum_target) < 1e-9:
        print(f"Fixed profit target: ${minimum_target:.2f}")
    else:
        print(
            "Profit target range: "
            f"${minimum_target:.2f}-${maximum_target:.2f}"
        )
    print(
        "Paper broker-side target/stop simulation: "
        f"{'ON' if scalping_settings.SCALPING_PAPER_PROTECTIVE_ORDERS_ENABLED else 'OFF'}"
    )
    print(
        "Flatten paper positions when runner stops: "
        f"{'YES' if scalping_settings.SCALPING_CLOSE_OPEN_POSITIONS_ON_RUNNER_STOP else 'NO'}"
    )
    print("Live MT5 orders: IMPOSSIBLE IN THIS RUNNER")
    print("=" * 70)

    cycle_number = 0
    last_cycle = None
    stop_reason = "Paper scalper runner stopped"

    try:
        while True:
            emergency_active, emergency_reason = check_emergency_stop()
            if emergency_active:
                print("")
                print("SCALPING LOOP STOPPED BY EMERGENCY STOP")
                print(emergency_reason)
                stop_reason = "Paper scalper emergency-stop flatten"
                break

            cycle_started = time.monotonic()
            cycle_number += 1
            last_cycle = run_scalping_cycle(symbol)

            if scalping_settings.SCALPING_PRINT_EVERY_CYCLE:
                print_scalping_cycle_summary(last_cycle, cycle_number)

            if cycle_limit is not None and cycle_number >= cycle_limit:
                print("")
                print(f"Scalping loop completed {cycle_number} cycle(s).")
                stop_reason = "Paper scalper finite-run flatten"
                break

            paper_state = (
                last_cycle.paper if isinstance(last_cycle.paper, dict) else {}
            )
            has_open_position = (
                int(paper_state.get("open_trade_count", 0) or 0) > 0
            )
            active_interval = (
                min(interval, open_position_interval)
                if has_open_position
                else interval
            )

            elapsed = time.monotonic() - cycle_started
            remaining = max(0.0, active_interval - elapsed)
            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:
        print("")
        print("=" * 70)
        print("PAPER-SCALPING LOOP MANUALLY STOPPED")
        print("User stopped the scalper with CTRL+C.")
        print("=" * 70)
        stop_reason = "Manual CTRL+C paper-scalper flatten"
    finally:
        if (
            bool(scalping_settings.SCALPING_CLOSE_OPEN_POSITIONS_ON_RUNNER_STOP)
            and last_cycle is not None
            and last_cycle.snapshot is not None
        ):
            before_trades = load_scalping_trades()
            decision_time = datetime.now(timezone.utc)
            request_time = datetime.now(timezone.utc)
            flattened = close_all_open_scalp_paper_trades(
                last_cycle.snapshot,
                reason=stop_reason,
            )
            response_time = datetime.now(timezone.utc)
            after_trades = load_scalping_trades()
            shutdown_audit = audit_paper_trade_transition(
                before_trades,
                after_trades,
                snapshot=last_cycle.snapshot,
                signal=last_cycle.signal,
                decision_timestamp=decision_time,
                request_timestamp=request_time,
                response_timestamp=response_time,
            )
            print("")
            print("=" * 70)
            print("PAPER POSITION SHUTDOWN PROTECTION")
            print("=" * 70)
            print(f"Positions closed: {flattened['closed_count']}")
            print(flattened["message"])
            print(
                "Shutdown execution-audit rows: "
                f"{shutdown_audit.get('rows_appended', 0)}"
            )
            print("=" * 70)

        # Persist every buffered research record before the process exits.
        tick_flush = flush_tick_recorder()
        feature_flush = flush_microstructure_features()
        audit_flush = flush_execution_audit()
        print("")
        print("V5 RESEARCH DATA FLUSH")
        print(
            f"Ticks buffered={tick_flush.get('buffered_rows', 0)} | "
            f"Features buffered={feature_flush.get('buffered_rows', 0)} | "
            f"Audit buffered={audit_flush.get('buffered_rows', 0)}"
        )
        errors = [
            item.get("last_error", "")
            for item in (tick_flush, feature_flush, audit_flush)
            if item.get("last_error")
        ]
        if errors:
            print(f"Research storage errors: {errors}")
