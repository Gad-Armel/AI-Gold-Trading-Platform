from __future__ import annotations

from config import scalping_settings
from models.scalping_state import ScalpingCycleState


def _metric(cycle: ScalpingCycleState, timeframe: str, key: str, default="N/A"):
    if cycle.signal is None:
        return default
    data = cycle.signal.metrics.get(timeframe, {})
    return data.get(key, default) if isinstance(data, dict) else default


def _format_components(components: dict) -> str:
    if not isinstance(components, dict) or not components:
        return "N/A"
    return " | ".join(f"{name}={float(value):+.1f}" for name, value in components.items())


def print_scalping_cycle_summary(cycle: ScalpingCycleState, cycle_number: int) -> None:
    snapshot = cycle.snapshot
    signal = cycle.signal
    risk = cycle.risk or {}
    paper = cycle.paper or {}
    news = cycle.news_risk or {}

    print("")
    print("=" * 70)
    print(f"SCALPING CYCLE {cycle_number} | {cycle.symbol} | PAPER ONLY")
    print("=" * 70)
    print(f"Cycle Status: {'SUCCESS' if cycle.success else 'FAILED'}")
    print(f"Runtime: {cycle.runtime_ms:.1f} ms")
    if bool(getattr(scalping_settings, "SCALPING_TIMING_DIAGNOSTICS_ENABLED", False)) and cycle.timing_ms:
        ordered = ("snapshot", "news_filter", "news_context", "signal_engine", "risk_guard", "paper_manager")
        timing_text = " | ".join(
            f"{name}={float(cycle.timing_ms.get(name, 0.0)):.1f}ms" for name in ordered
        )
        print(f"Timing Detail: {timing_text}")
        slow_limit = float(getattr(scalping_settings, "SCALPING_SLOW_PHASE_WARNING_MS", 200.0))
        slow_phases = [
            f"{name}={float(value):.1f}ms"
            for name, value in cycle.timing_ms.items()
            if name not in {"core_total", "trade_export", "cycle_log"} and float(value) > slow_limit
        ]
        if slow_phases:
            print("Slow Phase Warning: " + " | ".join(slow_phases))

    if snapshot is not None:
        print(f"Price: Bid={snapshot.bid:.5f} | Ask={snapshot.ask:.5f} | Spread={snapshot.spread:.3f}")
        print(f"Session: {snapshot.session} | Candle Cache: {'HIT' if snapshot.candle_cache_hit else 'REFRESHED'}")

    print("-" * 70)
    print("SCALP SIGNAL")
    print("-" * 70)
    if signal is not None:
        print(f"Action: {signal.action}")
        print(f"Allowed: {'YES' if signal.allowed else 'NO'}")
        print(f"Score: {signal.score:.1f} / 100")
        print(f"Pattern: {signal.pattern}")
        print(f"BUY Score: {signal.metrics.get('buy_score', 0.0):.1f} | SELL Score: {signal.metrics.get('sell_score', 0.0):.1f}")
        print(
            f"M1 ATR: {_metric(cycle, 'M1', 'atr')} | "
            f"M1 RSI: {_metric(cycle, 'M1', 'rsi')} | "
            f"M1 Momentum: {_metric(cycle, 'M1', 'momentum')} | "
            f"EMA Distance/ATR: {_metric(cycle, 'M1', 'distance_fast_atr_ratio')}"
        )
        if signal.allowed:
            print(f"Target: ${signal.target_profit_usd:.2f} | Stop: ${signal.stop_loss_usd:.2f}")
        elif scalping_settings.SCALPING_PRINT_WAIT_REASONS:
            print(f"Wait Reasons: {signal.block_reasons}")

        unified = signal.metrics if isinstance(signal.metrics, dict) else {}
        regime = unified.get("regime", {}) if isinstance(unified, dict) else {}
        structure = unified.get("structure", {}) if isinstance(unified, dict) else {}
        zones = unified.get("zones", {}) if isinstance(unified, dict) else {}
        order_blocks = unified.get("order_blocks", {}) if isinstance(unified, dict) else {}
        factors = unified.get("factor_model", {}) if isinstance(unified, dict) else {}
        news_context = unified.get("news_context", {}) if isinstance(unified, dict) else {}
        verified_context = unified.get("verified_context", {}) if isinstance(unified, dict) else {}
        cross_market = unified.get("cross_market_context", {}) if isinstance(unified, dict) else {}
        score_diag = unified.get("score_diagnostics", {}) if isinstance(unified, dict) else {}
        data_quality = unified.get("data_quality", {}) if isinstance(unified, dict) else {}
        clock_diag = unified.get("clock_diagnostics", {}) if isinstance(unified, dict) else {}

        factor_status = factors.get("status", "N/A")
        factor_error = factors.get("error", "")
        print(
            "Unified Context: "
            f"Regime={regime.get('mode', 'N/A')}({regime.get('direction', 'N/A')}) | "
            f"Structure={structure.get('direction', 'N/A')} | "
            f"Factor={factors.get('preferred_direction', 'N/A')} "
            f"{float(factors.get('preferred_score', 0.0) or 0.0):.1f} | Status={factor_status}"
        )
        if factor_error:
            print(f"Factor Error: {factor_error}")
        print(f"Regime Reason: {regime.get('reason', 'N/A')}")
        print(
            "Zones/Blocks: "
            f"NearSupport={zones.get('near_support', False)} | "
            f"NearResistance={zones.get('near_resistance', False)} | "
            f"BullOB={order_blocks.get('in_bullish', False)} | "
            f"BearOB={order_blocks.get('in_bearish', False)}"
        )
        print(
            "Unified News: "
            f"Bias={news_context.get('directional_bias', 'NEUTRAL')} | "
            f"Mode={news_context.get('data_mode', 'CALENDAR_PROTECTION_ONLY')} | "
            f"Providers={news_context.get('provider_healthy_count', 0)}/{news_context.get('provider_configured_count', 0)} | "
            f"DirectionalEvents={news_context.get('directional_event_count', 0)}"
        )
        print(
            "Verified Market Context: "
            f"Status={verified_context.get('status', 'N/A')} | "
            f"DataCompleteness={float(verified_context.get('data_completeness_score', verified_context.get('data_quality_score', 0.0)) or 0.0):.2f} | "
            f"RelVolume={float(verified_context.get('relative_tick_volume', 0.0) or 0.0):.2f} | "
            f"DeltaProxy={float(verified_context.get('signed_tick_volume_proxy', 0.0) or 0.0):+.2f} | "
            f"VWAPDist={float(verified_context.get('vwap_distance_atr', 0.0) or 0.0):+.2f}ATR | "
            f"ADX={float(verified_context.get('adx_m5', 0.0) or 0.0):.1f} "
            f"{verified_context.get('trend_direction', 'NEUTRAL')} | "
            f"Liquidity={verified_context.get('liquidity_regime', 'N/A')} | "
            f"Cache={'HIT' if verified_context.get('cache_hit', False) else 'REFRESH'} "
            f"{float(verified_context.get('calculation_duration_ms', 0.0) or 0.0):.1f}ms"
        )
        print(
            "Cross-Market Context: "
            f"Status={cross_market.get('status', 'N/A')} | "
            f"USD={cross_market.get('usd_bias', 'NEUTRAL')} | "
            f"Gold={cross_market.get('gold_bias', 'NEUTRAL')} | "
            f"Pressure={float(cross_market.get('pressure_score', 0.0) or 0.0):+.2f} | "
            f"Symbols={cross_market.get('available_symbols', 0)}/{cross_market.get('required_symbols', 0)}"
        )

        if bool(getattr(scalping_settings, "SCALPING_UNIFIED_DIAGNOSTICS_ENABLED", False)):
            print(
                "Confirming Families: "
                f"{score_diag.get('confirming_family_count', 0)}/{score_diag.get('minimum_confirming_families', 'N/A')} "
                f"{score_diag.get('confirming_families', [])}"
            )
            print(
                "Required Family Gates: "
                f"EntryTrigger={score_diag.get('entry_trigger_family_present', False)} | "
                f"DirectionalContext={score_diag.get('directional_context_family_present', False)} "
                f"{score_diag.get('matching_directional_context_families', [])}"
            )
            print(
                "Entry Readiness: "
                f"Pattern={score_diag.get('selected_pattern', signal.pattern)} | "
                f"ScoreShortfall={float(score_diag.get('score_shortfall', 0.0) or 0.0):.2f} | "
                f"Authorization={score_diag.get('score_authorization_mode', 'N/A')} | "
                f"Tolerance={float(score_diag.get('score_threshold_tolerance', 0.0) or 0.0):.2f} | "
                f"VWAP={float(score_diag.get('selected_vwap_distance_atr', 0.0) or 0.0):+.2f}ATR/"
                f"{float(score_diag.get('max_entry_vwap_distance_atr', 0.0) or 0.0):.2f} | "
                f"Overextended={score_diag.get('vwap_overextended', False)}"
            )
            direct = score_diag.get("direct_score_decision", {}) if isinstance(score_diag, dict) else {}
            if direct:
                print(
                    "Direct Score Decision: "
                    f"Accepted={direct.get('passed', False)} | "
                    f"Direction={direct.get('winner_direction', 'NONE')} | "
                    f"BUY={float(direct.get('buy_score', 0.0) or 0.0):.1f} | "
                    f"SELL={float(direct.get('sell_score', 0.0) or 0.0):.1f} | "
                    f"Margin={float(direct.get('margin', 0.0) or 0.0):.1f} | "
                    f"WinnerFloor={float(direct.get('minimum_winner_score', 0.0) or 0.0):.1f} | "
                    f"Mode={direct.get('mode', 'N/A')} | "
                    f"Failed={direct.get('failed_gates', [])}"
                )
            trend20 = unified.get("trend_confirmation", {}) if isinstance(unified, dict) else {}
            quality = score_diag.get("entry_quality_decision", {}) if isinstance(score_diag, dict) else {}
            if trend20:
                print(
                    "20-Candle Trend: "
                    f"Direction={trend20.get('trend_direction', 'NEUTRAL')} | "
                    f"Strength={float(trend20.get('trend_strength', 0.0) or 0.0):.2f} | "
                    f"Net={float(trend20.get('net_move_atr', 0.0) or 0.0):+.2f}ATR | "
                    f"Slope={float(trend20.get('slope_span_atr', 0.0) or 0.0):+.2f}ATR | "
                    f"Efficiency={float(trend20.get('efficiency_ratio', 0.0) or 0.0):.2f}"
                )
                print(
                    "3-Candle Confirmation: "
                    f"Direction={trend20.get('confirmation_direction', 'NEUTRAL')} | "
                    f"Bull={trend20.get('bullish_confirmation_candles', 0)} | "
                    f"Bear={trend20.get('bearish_confirmation_candles', 0)} | "
                    f"Net={float(trend20.get('confirmation_net_move_atr', 0.0) or 0.0):+.2f}ATR | "
                    f"3of3={trend20.get('three_of_three', False)}"
                )
            playbook = unified.get("playbook", {}) if isinstance(unified, dict) else {}
            if playbook:
                print(
                    "Closed-Candle Playbooks: "
                    f"3Closed={playbook.get('three_closed_direction', 'NEUTRAL')} | "
                    f"Pressure={playbook.get('three_closed_pressure_direction', 'NEUTRAL')} "
                    f"({float(playbook.get('three_closed_pressure_strength', 0.0) or 0.0):.2f}) | "
                    f"Pullback={playbook.get('trend_pullback_direction', 'NEUTRAL')} | "
                    f"Retest={playbook.get('breakout_retest_direction', 'NEUTRAL')} | "
                    f"MicroBreak={quality.get('micro_break_direction', 'NEUTRAL') if quality else 'NEUTRAL'} | "
                    f"Rejection={playbook.get('range_rejection_direction', 'NEUTRAL')}"
                )
            if quality:
                economics = quality.get("economics", {}) if isinstance(quality, dict) else {}
                print(
                    "Entry Quality Gate: "
                    f"Accepted={quality.get('passed', False)} | "
                    f"Path={quality.get('selected_path', quality.get('mode', 'QUALITY_WAIT'))} | "
                    f"Support={quality.get('support_votes', 0)} "
                    f"{quality.get('support_sources', [])} | "
                    f"Opposition={quality.get('opposition_votes', 0)} "
                    f"{quality.get('opposition_sources', [])} | "
                    f"Spread/ATR={float(quality.get('spread_atr_ratio', 0.0) or 0.0):.2f} | "
                    f"Failed={quality.get('failed_gates', [])}"
                )
                if economics:
                    print(
                        "Trade Economics: "
                        f"Target=${float(economics.get('target_usd', 0.0) or 0.0):.2f} | "
                        f"Stop=${float(economics.get('stop_usd', 0.0) or 0.0):.2f} | "
                        f"R/R={float(economics.get('reward_risk_ratio', 0.0) or 0.0):.2f} | "
                        f"Spread/Target={float(economics.get('spread_target_ratio', 0.0) or 0.0):.2f}"
                    )
            mtf = unified.get("multi_timeframe_alignment", {}) if isinstance(unified, dict) else {}
            print(
                "Multi-Timeframe Direction: "
                f"Dominant={mtf.get('dominant_direction', 'NEUTRAL')} | "
                f"BUY={mtf.get('buy_count', 0)} | SELL={mtf.get('sell_count', 0)} | "
                f"NEUTRAL={mtf.get('neutral_count', 0)} | Resolved={mtf.get('resolved', False)}"
            )
            signal_timing = unified.get("signal_timing_ms", {}) if isinstance(unified, dict) else {}
            if signal_timing:
                print(
                    "Signal Engine Timing: "
                    + " | ".join(f"{name}={float(value):.1f}ms" for name, value in signal_timing.items())
                )
            print(f"BUY Components: {_format_components(unified.get('buy_components', {}))}")
            print(f"SELL Components: {_format_components(unified.get('sell_components', {}))}")
            counts = []
            cache_records = []
            for timeframe in ("M1", "M5", "M15", "H1", "H4"):
                record = data_quality.get(timeframe, {}) if isinstance(data_quality, dict) else {}
                counts.append(
                    f"{timeframe}={record.get('bars_received', 'N/A')} bars | "
                    f"live={record.get('live_data_age_seconds', 'N/A')}s | "
                    f"closed={record.get('closed_data_age_seconds', 'N/A')}s"
                )
                cache_records.append(
                    f"{timeframe}={record.get('cache_status', 'UNKNOWN')} "
                    f"cache={record.get('cache_age_seconds', 'N/A')}s "
                    f"fetch={record.get('fetch_duration_ms', 'N/A')}ms "
                    f"reason={record.get('refresh_reason', '')}"
                )
            print("Candle Data: " + " || ".join(counts))
            print("Candle Cache Detail: " + " || ".join(cache_records))
            print(
                "Market Clock: "
                f"source={clock_diag.get('market_clock_source', 'N/A')} | "
                f"offset_vs_system={clock_diag.get('market_clock_offset_seconds', 'N/A')}s | "
                f"market={clock_diag.get('market_clock_time', 'N/A')} | "
                f"system={clock_diag.get('system_clock_time', 'N/A')}"
            )
            if snapshot is not None and snapshot.candle_cache_hit and cycle.runtime_ms > float(
                getattr(scalping_settings, "SCALPING_CACHE_HIT_RUNTIME_TARGET_MS", 200.0)
            ):
                print(
                    "Runtime Diagnostic: cache-hit cycle exceeded target "
                    f"({cycle.runtime_ms:.1f}ms > "
                    f"{float(getattr(scalping_settings, 'SCALPING_CACHE_HIT_RUNTIME_TARGET_MS', 200.0)):.1f}ms)."
                )

    print("-" * 70)
    print("V5 TICK MICROSTRUCTURE AND AGENT CONSENSUS")
    print("-" * 70)
    micro = cycle.microstructure if isinstance(cycle.microstructure, dict) else {}
    tick_state = cycle.tick_recorder if isinstance(cycle.tick_recorder, dict) else {}
    meta = cycle.meta_controller if isinstance(cycle.meta_controller, dict) else {}
    windows = micro.get("windows", {}) if isinstance(micro, dict) else {}
    print(
        "Tick Recorder: "
        f"captured={tick_state.get('captured', 0)} | "
        f"recent={tick_state.get('recent_tick_count', 0)} | "
        f"fetch_error={tick_state.get('fetch_error', '') or 'None'} | "
        f"storage_error={tick_state.get('storage', {}).get('last_error', '') or 'None'}"
    )
    print(
        "Microstructure: "
        f"status={micro.get('status', 'N/A')} | "
        f"direction={micro.get('direction', 'NEUTRAL')} | "
        f"confidence={float(micro.get('confidence', 0.0) or 0.0):.2f} | "
        f"quality={float(micro.get('data_quality', 0.0) or 0.0):.2f} | "
        f"ticks={micro.get('total_recent_ticks', 0)} | "
        f"span={float(micro.get('recent_span_seconds', 0.0) or 0.0):.2f}s"
    )
    for window_name in ("1", "3", "5"):
        record = windows.get(window_name, {}) if isinstance(windows, dict) else {}
        if record:
            print(
                f"Window {window_name}s: "
                f"arrival={float(record.get('tick_arrival_rate', 0.0) or 0.0):.1f}/s | "
                f"delta={int(record.get('synthetic_delta', 0) or 0)} | "
                f"ratio={float(record.get('directional_tick_ratio', 0.0) or 0.0):+.2f} | "
                f"velocity={float(record.get('velocity_atr_per_second', 0.0) or 0.0):+.4f} ATR/s | "
                f"stall={float(record.get('stall_ratio', 0.0) or 0.0):.2f} | "
                f"spread_expand={float(record.get('spread_expansion', 0.0) or 0.0):.4f}"
            )
    print(f"Microstructure Reason: {micro.get('reason', '')}")
    if cycle.agents:
        compact_agents = []
        for name, agent in cycle.agents.items():
            compact_agents.append(
                f"{name}={agent.get('direction', 'N/A')}"
                f"/{float(agent.get('confidence', 0.0) or 0.0):.2f}"
            )
        print("Agents: " + " | ".join(compact_agents))
    print(
        "Meta Controller: "
        f"allowed={'YES' if meta.get('allowed', False) else 'NO'} | "
        f"direction={meta.get('direction', 'WAIT')} | "
        f"entry_mode={meta.get('entry_mode', 'WAIT')} | "
        f"confidence={float(meta.get('confidence', 0.0) or 0.0):.2f} | "
        f"checks={meta.get('checks', {})}"
    )
    quality_details = meta.get("score_margin_quality_details", {})
    if quality_details:
        print(
            "Score-Margin Quality: "
            f"VWAP={float(quality_details.get('vwap_distance_atr', 0.0) or 0.0):.2f}ATR | "
            f"RelVolume={float(quality_details.get('relative_volume', 0.0) or 0.0):.2f} | "
            f"Support={quality_details.get('support_sources', [])} | "
            f"Opposition={quality_details.get('opposition_sources', [])} | "
            f"Triggers={quality_details.get('trigger_sources', [])} | "
            f"Extended={quality_details.get('extended', False)}"
        )
    if meta.get("block_reasons"):
        print(f"Meta Block Reasons: {meta.get('block_reasons')}")
    if meta.get("advisory_warnings"):
        print(f"Meta Advisory Warnings: {meta.get('advisory_warnings')}")
    intermarket = getattr(snapshot, "intermarket_context", {}) if snapshot else {}
    print(
        "Direct Intermarket: "
        f"status={intermarket.get('status', 'N/A')} | "
        f"bias={intermarket.get('gold_bias', 'NEUTRAL')} | "
        f"pressure={float(intermarket.get('pressure_score', 0.0) or 0.0):+.2f} | "
        f"symbols={intermarket.get('resolved_symbols', {})}"
    )
    print(
        "Execution Audit: "
        f"rows={cycle.execution_audit.get('rows_appended', 0)} | "
        f"entries={cycle.execution_audit.get('entry_events', 0)} | "
        f"exits={cycle.execution_audit.get('exit_events', 0)}"
    )

    print("-" * 70)
    print("SAFETY")
    print("-" * 70)
    print(f"News Allowed: {'YES' if news.get('allowed', False) else 'NO'}")
    print(f"Risk Allowed: {'YES' if risk.get('allowed', False) else 'NO'}")
    print(f"Entry Allowed: {'YES' if risk.get('entry_allowed', False) else 'NO'}")
    print(f"Daily Trades: {risk.get('daily_trade_count', 0)}")
    print(f"Daily Realized P/L: ${risk.get('daily_realized_profit', 0.0):.2f}")
    print(f"Consecutive Losses: {risk.get('consecutive_losses', 0)}")
    print(
        "Loss Cooldown: "
        f"{risk.get('loss_cooldown_status', 'INACTIVE')} | "
        f"remaining={risk.get('loss_cooldown_remaining_seconds', 0.0):.1f}s | "
        f"duration={risk.get('loss_cooldown_duration_seconds', 0.0):.0f}s"
    )
    print(f"Maximum Drawdown: ${risk.get('max_drawdown', 0.0):.2f}")
    print(
        "Open Risk: "
        f"${risk.get('existing_open_risk_usd', 0.0):.2f} existing | "
        f"${risk.get('proposed_open_risk_usd', 0.0):.2f} proposed"
    )
    if risk.get("block_reasons"):
        print(f"Risk Block Reasons: {risk.get('block_reasons')}")

    print("-" * 70)
    print("PAPER SCALPING")
    print("-" * 70)
    print(f"Action: {paper.get('action', 'N/A')}")
    print(f"Message: {paper.get('message', '')}")
    print(f"Open Scalp Trades: {paper.get('open_trade_count', 0)}")
    print(f"Closed Scalp Trades: {paper.get('closed_trade_count', 0)}")
    print(f"Realized Scalp Profit: ${paper.get('realized_profit_usd', 0.0):.2f}")
    print(f"Unrealized Scalp Profit: ${paper.get('unrealized_profit_usd', 0.0):.2f}")
    print(f"Scalp Win Rate: {paper.get('win_rate', 0.0):.2f}%")

    if cycle.error_message:
        print("-" * 70)
        print(f"ERROR: {cycle.error_message}")
    print("=" * 70)
