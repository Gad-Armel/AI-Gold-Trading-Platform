from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpingCycleState
from services.risk.scalping_risk_guard import (
    get_scalping_log_folder,
    load_scalping_trades,
)


def _metric(cycle: ScalpingCycleState, timeframe: str, key: str, default: Any = "") -> Any:
    if cycle.signal is None:
        return default
    metrics = cycle.signal.metrics.get(timeframe, {})
    return metrics.get(key, default) if isinstance(metrics, dict) else default


def _cycle_row(cycle: ScalpingCycleState) -> dict[str, Any]:
    snapshot = cycle.snapshot
    signal = cycle.signal
    news = cycle.news_risk or {}
    risk = cycle.risk or {}
    paper = cycle.paper or {}
    unified = signal.metrics if signal and isinstance(signal.metrics, dict) else {}
    regime = unified.get("regime", {}) if isinstance(unified, dict) else {}
    structure = unified.get("structure", {}) if isinstance(unified, dict) else {}
    zones = unified.get("zones", {}) if isinstance(unified, dict) else {}
    blocks = unified.get("order_blocks", {}) if isinstance(unified, dict) else {}
    factors = unified.get("factor_model", {}) if isinstance(unified, dict) else {}
    news_context = unified.get("news_context", {}) if isinstance(unified, dict) else {}
    verified_context = unified.get("verified_context", {}) if isinstance(unified, dict) else {}
    cross_market = unified.get("cross_market_context", {}) if isinstance(unified, dict) else {}
    trend_confirmation = unified.get("trend_confirmation", {}) if isinstance(unified, dict) else {}
    entry_quality = unified.get("score_diagnostics", {}).get("entry_quality_decision", {}) if isinstance(unified, dict) else {}

    return {
        "timestamp": cycle.finished_at.strftime("%Y-%m-%d %H:%M:%S"),
        "success": cycle.success,
        "symbol": cycle.symbol,
        "runtime_ms": round(cycle.runtime_ms, 3),
        "timing_snapshot_ms": cycle.timing_ms.get("snapshot", ""),
        "timing_news_filter_ms": cycle.timing_ms.get("news_filter", ""),
        "timing_news_context_ms": cycle.timing_ms.get("news_context", ""),
        "timing_signal_engine_ms": cycle.timing_ms.get("signal_engine", ""),
        "timing_risk_guard_ms": cycle.timing_ms.get("risk_guard", ""),
        "timing_paper_manager_ms": cycle.timing_ms.get("paper_manager", ""),
        "timing_core_total_ms": cycle.timing_ms.get("core_total", ""),
        "timing_trade_export_ms": cycle.timing_ms.get("trade_export", ""),
        "bid": getattr(snapshot, "bid", ""),
        "ask": getattr(snapshot, "ask", ""),
        "spread": getattr(snapshot, "spread", ""),
        "session": getattr(snapshot, "session", ""),
        "candle_cache_hit": getattr(snapshot, "candle_cache_hit", ""),
        "signal_action": getattr(signal, "action", ""),
        "signal_allowed": getattr(signal, "allowed", ""),
        "signal_score": getattr(signal, "score", ""),
        "signal_confidence": getattr(signal, "confidence", ""),
        "signal_pattern": getattr(signal, "pattern", ""),
        "signal_key": getattr(signal, "signal_key", ""),
        "target_profit_usd": getattr(signal, "target_profit_usd", ""),
        "stop_loss_usd": getattr(signal, "stop_loss_usd", ""),
        "buy_score": signal.metrics.get("buy_score", "") if signal else "",
        "sell_score": signal.metrics.get("sell_score", "") if signal else "",
        "trend20_direction": trend_confirmation.get("trend_direction", ""),
        "trend20_strength": trend_confirmation.get("trend_strength", ""),
        "trend20_net_move_atr": trend_confirmation.get("net_move_atr", ""),
        "trend20_slope_span_atr": trend_confirmation.get("slope_span_atr", ""),
        "trend20_efficiency": trend_confirmation.get("efficiency_ratio", ""),
        "confirmation3_direction": trend_confirmation.get("confirmation_direction", ""),
        "confirmation3_bullish_count": trend_confirmation.get("bullish_confirmation_candles", ""),
        "confirmation3_bearish_count": trend_confirmation.get("bearish_confirmation_candles", ""),
        "confirmation3_net_move_atr": trend_confirmation.get("confirmation_net_move_atr", ""),
        "confirmation3_three_of_three": trend_confirmation.get("three_of_three", ""),
        "entry_quality_passed": entry_quality.get("passed", ""),
        "entry_quality_support_votes": entry_quality.get("support_votes", ""),
        "entry_quality_opposition_votes": entry_quality.get("opposition_votes", ""),
        "entry_quality_failed_gates": json.dumps(entry_quality.get("failed_gates", []), ensure_ascii=False),
        "m1_close": _metric(cycle, "M1", "close"),
        "m1_atr": _metric(cycle, "M1", "atr"),
        "m1_rsi": _metric(cycle, "M1", "rsi"),
        "m1_momentum": _metric(cycle, "M1", "momentum"),
        "m1_distance_fast_atr_ratio": _metric(
            cycle, "M1", "distance_fast_atr_ratio"
        ),
        "m1_ema_fast": _metric(cycle, "M1", "ema_fast"),
        "m1_ema_slow": _metric(cycle, "M1", "ema_slow"),
        "m5_ema_fast": _metric(cycle, "M5", "ema_fast"),
        "m5_ema_slow": _metric(cycle, "M5", "ema_slow"),
        "m15_ema_fast": _metric(cycle, "M15", "ema_fast"),
        "m15_ema_slow": _metric(cycle, "M15", "ema_slow"),
        "market_regime": regime.get("mode", ""),
        "regime_direction": regime.get("direction", ""),
        "structure_direction": structure.get("direction", ""),
        "bos_buy": structure.get("bos_buy", ""),
        "bos_sell": structure.get("bos_sell", ""),
        "near_support": zones.get("near_support", ""),
        "near_resistance": zones.get("near_resistance", ""),
        "in_bullish_order_block": blocks.get("in_bullish", ""),
        "in_bearish_order_block": blocks.get("in_bearish", ""),
        "factor_direction": factors.get("preferred_direction", ""),
        "factor_score": factors.get("preferred_score", ""),
        "factor_status": factors.get("status", ""),
        "factor_error": factors.get("error", ""),
        "factor_count": factors.get("preferred_factor_count", ""),
        "confirming_family_count": unified.get("score_diagnostics", {}).get("confirming_family_count", ""),
        "confirming_families": json.dumps(unified.get("score_diagnostics", {}).get("confirming_families", []), ensure_ascii=False),
        "entry_trigger_family_present": unified.get("score_diagnostics", {}).get("entry_trigger_family_present", ""),
        "directional_context_family_present": unified.get("score_diagnostics", {}).get("directional_context_family_present", ""),
        "matching_directional_context_families": json.dumps(unified.get("score_diagnostics", {}).get("matching_directional_context_families", []), ensure_ascii=False),
        "buy_components": json.dumps(unified.get("buy_components", {}), ensure_ascii=False),
        "sell_components": json.dumps(unified.get("sell_components", {}), ensure_ascii=False),
        "m1_bars_received": unified.get("data_quality", {}).get("M1", {}).get("bars_received", ""),
        "m5_bars_received": unified.get("data_quality", {}).get("M5", {}).get("bars_received", ""),
        "m15_bars_received": unified.get("data_quality", {}).get("M15", {}).get("bars_received", ""),
        "h1_bars_received": unified.get("data_quality", {}).get("H1", {}).get("bars_received", ""),
        "h4_bars_received": unified.get("data_quality", {}).get("H4", {}).get("bars_received", ""),
        "m1_data_age_seconds": unified.get("data_quality", {}).get("M1", {}).get("live_data_age_seconds", ""),
        "m1_closed_data_age_seconds": unified.get("data_quality", {}).get("M1", {}).get("closed_data_age_seconds", ""),
        "m1_cache_status": unified.get("data_quality", {}).get("M1", {}).get("cache_status", ""),
        "m1_cache_age_seconds": unified.get("data_quality", {}).get("M1", {}).get("cache_age_seconds", ""),
        "m1_fetch_duration_ms": unified.get("data_quality", {}).get("M1", {}).get("fetch_duration_ms", ""),
        "m5_cache_status": unified.get("data_quality", {}).get("M5", {}).get("cache_status", ""),
        "m15_cache_status": unified.get("data_quality", {}).get("M15", {}).get("cache_status", ""),
        "h1_cache_status": unified.get("data_quality", {}).get("H1", {}).get("cache_status", ""),
        "h4_cache_status": unified.get("data_quality", {}).get("H4", {}).get("cache_status", ""),
        "m5_closed_data_age_seconds": unified.get("data_quality", {}).get("M5", {}).get("closed_data_age_seconds", ""),
        "m15_closed_data_age_seconds": unified.get("data_quality", {}).get("M15", {}).get("closed_data_age_seconds", ""),
        "h1_closed_data_age_seconds": unified.get("data_quality", {}).get("H1", {}).get("closed_data_age_seconds", ""),
        "h4_closed_data_age_seconds": unified.get("data_quality", {}).get("H4", {}).get("closed_data_age_seconds", ""),
        "market_clock_source": unified.get("clock_diagnostics", {}).get("market_clock_source", ""),
        "market_clock_offset_seconds": unified.get("clock_diagnostics", {}).get("market_clock_offset_seconds", ""),
        "news_directional_bias": news_context.get("directional_bias", ""),
        "news_data_mode": news_context.get("data_mode", ""),
        "news_directional_event_count": news_context.get("directional_event_count", ""),
        "news_provider_conflict": news_context.get("provider_conflict", ""),
        "news_provider_quality": news_context.get("provider_quality", ""),
        "news_provider_cache_age_hours": news_context.get("provider_cache_age_hours", ""),
        "verified_context_status": verified_context.get("status", ""),
        "verified_data_quality_score": verified_context.get("data_quality_score", ""),
        "relative_tick_volume": verified_context.get("relative_tick_volume", ""),
        "signed_tick_volume_proxy": verified_context.get("signed_tick_volume_proxy", ""),
        "rolling_vwap": verified_context.get("rolling_vwap", ""),
        "vwap_distance_atr": verified_context.get("vwap_distance_atr", ""),
        "adx_m5": verified_context.get("adx_m5", ""),
        "verified_trend_direction": verified_context.get("trend_direction", ""),
        "verified_liquidity_regime": verified_context.get("liquidity_regime", ""),
        "nearest_pivot": verified_context.get("nearest_pivot", ""),
        "nearest_pivot_distance_atr": verified_context.get("nearest_pivot_distance_atr", ""),
        "cross_market_status": cross_market.get("status", ""),
        "cross_market_usd_bias": cross_market.get("usd_bias", ""),
        "cross_market_gold_bias": cross_market.get("gold_bias", ""),
        "cross_market_pressure_score": cross_market.get("pressure_score", ""),
        "cross_market_available_symbols": cross_market.get("available_symbols", ""),
        "news_allowed": news.get("allowed", ""),
        "news_action": news.get("action", ""),
        "risk_allowed": risk.get("allowed", ""),
        "risk_entry_allowed": risk.get("entry_allowed", ""),
        "daily_trade_count": risk.get("daily_trade_count", ""),
        "daily_realized_profit": risk.get("daily_realized_profit", ""),
        "consecutive_losses": risk.get("consecutive_losses", ""),
        "loss_cooldown_active": risk.get("loss_cooldown_active", ""),
        "loss_cooldown_status": risk.get("loss_cooldown_status", ""),
        "loss_cooldown_remaining_seconds": risk.get("loss_cooldown_remaining_seconds", ""),
        "loss_cooldown_triggered_at": risk.get("loss_cooldown_triggered_at", ""),
        "max_drawdown": risk.get("max_drawdown", ""),
        "same_direction_open_count": risk.get("same_direction_open_count", ""),
        "existing_open_risk_usd": risk.get("existing_open_risk_usd", ""),
        "proposed_open_risk_usd": risk.get("proposed_open_risk_usd", ""),
        "paper_action": paper.get("action", ""),
        "open_trade_count": paper.get("open_trade_count", ""),
        "closed_trade_count": paper.get("closed_trade_count", ""),
        "realized_profit_usd": paper.get("realized_profit_usd", ""),
        "unrealized_profit_usd": paper.get("unrealized_profit_usd", ""),
        "win_rate": paper.get("win_rate", ""),
        "timing_direct_intermarket_ms": cycle.timing_ms.get("direct_intermarket", ""),
        "timing_tick_recorder_ms": cycle.timing_ms.get("tick_recorder", ""),
        "timing_microstructure_ms": cycle.timing_ms.get("microstructure", ""),
        "timing_agent_consensus_ms": cycle.timing_ms.get("agent_consensus", ""),
        "timing_execution_audit_ms": cycle.timing_ms.get("execution_audit", ""),
        "ticks_captured": cycle.tick_recorder.get("captured", ""),
        "recent_tick_count": cycle.tick_recorder.get("recent_tick_count", ""),
        "tick_fetch_error": cycle.tick_recorder.get("fetch_error", ""),
        "tick_storage_error": cycle.tick_recorder.get("storage", {}).get("last_error", ""),
        "microstructure_status": cycle.microstructure.get("status", ""),
        "microstructure_direction": cycle.microstructure.get("direction", ""),
        "microstructure_confidence": cycle.microstructure.get("confidence", ""),
        "microstructure_data_quality": cycle.microstructure.get("data_quality", ""),
        "microstructure_reason": cycle.microstructure.get("reason", ""),
        "micro_w1_arrival_rate": cycle.microstructure.get("windows", {}).get("1", {}).get("tick_arrival_rate", ""),
        "micro_w1_delta": cycle.microstructure.get("windows", {}).get("1", {}).get("synthetic_delta", ""),
        "micro_w1_ratio": cycle.microstructure.get("windows", {}).get("1", {}).get("directional_tick_ratio", ""),
        "micro_w1_velocity_atr_s": cycle.microstructure.get("windows", {}).get("1", {}).get("velocity_atr_per_second", ""),
        "micro_w3_arrival_rate": cycle.microstructure.get("windows", {}).get("3", {}).get("tick_arrival_rate", ""),
        "micro_w3_delta": cycle.microstructure.get("windows", {}).get("3", {}).get("synthetic_delta", ""),
        "micro_w3_ratio": cycle.microstructure.get("windows", {}).get("3", {}).get("directional_tick_ratio", ""),
        "micro_w3_velocity_atr_s": cycle.microstructure.get("windows", {}).get("3", {}).get("velocity_atr_per_second", ""),
        "micro_w3_stall_ratio": cycle.microstructure.get("windows", {}).get("3", {}).get("stall_ratio", ""),
        "micro_w3_spread_expansion": cycle.microstructure.get("windows", {}).get("3", {}).get("spread_expansion", ""),
        "micro_w5_arrival_rate": cycle.microstructure.get("windows", {}).get("5", {}).get("tick_arrival_rate", ""),
        "micro_w5_delta": cycle.microstructure.get("windows", {}).get("5", {}).get("synthetic_delta", ""),
        "micro_w5_ratio": cycle.microstructure.get("windows", {}).get("5", {}).get("directional_tick_ratio", ""),
        "micro_w5_velocity_atr_s": cycle.microstructure.get("windows", {}).get("5", {}).get("velocity_atr_per_second", ""),
        "meta_allowed": cycle.meta_controller.get("allowed", ""),
        "meta_direction": cycle.meta_controller.get("direction", ""),
        "meta_confidence": cycle.meta_controller.get("confidence", ""),
        "meta_checks": json.dumps(cycle.meta_controller.get("checks", {}), ensure_ascii=False),
        "meta_block_reasons": json.dumps(cycle.meta_controller.get("block_reasons", []), ensure_ascii=False),
        "direct_intermarket_status": getattr(snapshot, "intermarket_context", {}).get("status", "") if snapshot else "",
        "direct_intermarket_gold_bias": getattr(snapshot, "intermarket_context", {}).get("gold_bias", "") if snapshot else "",
        "direct_intermarket_pressure": getattr(snapshot, "intermarket_context", {}).get("pressure_score", "") if snapshot else "",
        "execution_audit_rows": cycle.execution_audit.get("rows_appended", ""),
        "execution_audit_entries": cycle.execution_audit.get("entry_events", ""),
        "execution_audit_exits": cycle.execution_audit.get("exit_events", ""),
        "agents_json": json.dumps(cycle.agents, ensure_ascii=False, default=str),
        "signal_reasons": json.dumps(
            getattr(signal, "reasons", []) if signal else [],
            ensure_ascii=False,
        ),
        "signal_block_reasons": json.dumps(
            getattr(signal, "block_reasons", []) if signal else [],
            ensure_ascii=False,
        ),
        "risk_block_reasons": json.dumps(
            risk.get("block_reasons", []),
            ensure_ascii=False,
        ),
        "paper_message": paper.get("message", ""),
        "error_message": cycle.error_message or "",
    }


def log_scalping_cycle(cycle: ScalpingCycleState) -> str:
    folder = get_scalping_log_folder()
    path = os.path.join(folder, scalping_settings.SCALPING_CYCLE_LOG_FILENAME)
    row = _cycle_row(cycle)
    file_exists = os.path.exists(path)

    with open(path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return path


def export_scalping_trade_history() -> str:
    folder = get_scalping_log_folder()
    path = os.path.join(folder, scalping_settings.SCALPING_TRADE_HISTORY_FILENAME)
    trades = load_scalping_trades()

    fieldnames = [
        "id",
        "strategy_id",
        "status",
        "symbol",
        "direction",
        "opened_at",
        "closed_at",
        "entry_price",
        "close_price",
        "entry_spread",
        "lot_size",
        "contract_size",
        "profit_calculation_method",
        "signal_score",
        "signal_confidence",
        "entry_pattern",
        "entry_candle_time",
        "entry_m1_atr",
        "entry_m1_rsi",
        "entry_m1_momentum",
        "entry_distance_fast_atr_ratio",
        "profit_target_usd",
        "stop_loss_usd",
        "best_profit_usd",
        "final_profit_usd",
        "close_reason",
        "hold_seconds",
        "session",
        "signal_key",
        "entry_market_regime",
        "entry_regime_direction",
        "entry_structure_direction",
        "entry_near_support",
        "entry_near_resistance",
        "entry_in_bullish_order_block",
        "entry_in_bearish_order_block",
        "entry_factor_direction",
        "entry_factor_score",
        "entry_factor_count",
        "entry_confirming_family_count",
        "entry_confirming_families",
        "entry_news_bias",
        "entry_news_data_mode",
        "entry_verified_data_quality_score",
        "entry_relative_tick_volume",
        "entry_signed_tick_volume_proxy",
        "entry_rolling_vwap",
        "entry_vwap_distance_atr",
        "entry_adx_m5",
        "entry_verified_trend_direction",
        "entry_verified_liquidity_regime",
        "entry_nearest_pivot",
        "entry_nearest_pivot_distance_atr",
        "entry_cross_market_status",
        "entry_cross_market_usd_bias",
        "entry_cross_market_gold_bias",
        "entry_cross_market_pressure_score",
        "worst_profit_usd",
        "max_favorable_excursion_usd",
        "max_adverse_excursion_usd",
    ]

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow({key: trade.get(key, "") for key in fieldnames})

    return path
