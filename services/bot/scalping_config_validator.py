from __future__ import annotations

import importlib.util

from config import scalping_settings
from config import settings as core_settings


def validate_scalping_config() -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if not scalping_settings.SCALPING_ENABLED:
        errors.append("SCALPING_ENABLED must be True to run the scalping engine.")

    if scalping_settings.SCALPING_PAPER_ONLY:
        if bool(scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED):
            errors.append("Demo execution cannot be enabled while SCALPING_PAPER_ONLY=True.")
    elif not bool(scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED):
        warnings.append(
            "SCALPING_PAPER_ONLY=False while demo execution is disabled; no runner should start."
        )

    if bool(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED):
        errors.append("Real-account scalping execution is not implemented and must remain False.")

    if (
        scalping_settings.REQUIRE_CORE_LIVE_TRADING_DISABLED
        and bool(getattr(core_settings, "ENABLE_LIVE_TRADING", False))
    ):
        errors.append("Core ENABLE_LIVE_TRADING must remain False.")

    positive_settings = {
        "SCALPING_LOT_SIZE": scalping_settings.SCALPING_LOT_SIZE,
        "SCALPING_LOOP_INTERVAL_SECONDS": scalping_settings.SCALPING_LOOP_INTERVAL_SECONDS,
        "SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS": scalping_settings.SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS,
        "SCALPING_OFFLINE_GAP_THRESHOLD_SECONDS": scalping_settings.SCALPING_OFFLINE_GAP_THRESHOLD_SECONDS,
        "SCALPING_CANDLE_MISSING_BAR_RETRY_SECONDS": scalping_settings.SCALPING_CANDLE_MISSING_BAR_RETRY_SECONDS,
        "SCALPING_CACHE_HIT_RUNTIME_TARGET_MS": scalping_settings.SCALPING_CACHE_HIT_RUNTIME_TARGET_MS,
        "SCALPING_MAX_ENTRY_SPREAD_USD": scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD,
        "SCALPING_ADAPTIVE_HARD_MAX_ENTRY_SPREAD_USD": scalping_settings.SCALPING_ADAPTIVE_HARD_MAX_ENTRY_SPREAD_USD,
        "SCALPING_ADAPTIVE_SPREAD_MIN_WINNER_SCORE": scalping_settings.SCALPING_ADAPTIVE_SPREAD_MIN_WINNER_SCORE,
        "SCALPING_ADAPTIVE_SPREAD_MIN_SCORE_MARGIN": scalping_settings.SCALPING_ADAPTIVE_SPREAD_MIN_SCORE_MARGIN,
        "SCALPING_ADAPTIVE_MAX_SPREAD_TARGET_RATIO": scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_TARGET_RATIO,
        "SCALPING_ADAPTIVE_MAX_SPREAD_ATR_RATIO": scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_ATR_RATIO,
        "SCALPING_ADAPTIVE_MIN_REWARD_RISK_RATIO": scalping_settings.SCALPING_ADAPTIVE_MIN_REWARD_RISK_RATIO,
        "SCALPING_TARGET_SPREAD_MULTIPLIER": scalping_settings.SCALPING_TARGET_SPREAD_MULTIPLIER,
        "SCALPING_MIN_DIRECTIONAL_MOMENTUM_USD": scalping_settings.SCALPING_MIN_DIRECTIONAL_MOMENTUM_USD,
        "SCALPING_MAX_BREAKOUT_DISTANCE_ATR_RATIO": scalping_settings.SCALPING_MAX_BREAKOUT_DISTANCE_ATR_RATIO,
        "SCALPING_MAX_PULLBACK_DISTANCE_ATR_RATIO": scalping_settings.SCALPING_MAX_PULLBACK_DISTANCE_ATR_RATIO,
        "SCALPING_UNIFIED_TREND_RECLAIM_TRIGGER_POINTS": scalping_settings.SCALPING_UNIFIED_TREND_RECLAIM_TRIGGER_POINTS,
        "SCALPING_UNIFIED_STANDARD_TRIGGER_POINTS": scalping_settings.SCALPING_UNIFIED_STANDARD_TRIGGER_POINTS,
        "SCALPING_UNIFIED_TREND_RECLAIM_MAX_FAST_EMA_DISTANCE_ATR": scalping_settings.SCALPING_UNIFIED_TREND_RECLAIM_MAX_FAST_EMA_DISTANCE_ATR,
        "SCALPING_UNIFIED_TREND_RECLAIM_MAX_VWAP_DISTANCE_ATR": scalping_settings.SCALPING_UNIFIED_TREND_RECLAIM_MAX_VWAP_DISTANCE_ATR,
        "SCALPING_UNIFIED_TREND_RECLAIM_MIN_BODY_RATIO": scalping_settings.SCALPING_UNIFIED_TREND_RECLAIM_MIN_BODY_RATIO,
        "SCALPING_UNIFIED_TREND_RECLAIM_MIN_RELATIVE_VOLUME": scalping_settings.SCALPING_UNIFIED_TREND_RECLAIM_MIN_RELATIVE_VOLUME,
        "SCALPING_UNIFIED_TREND_RECLAIM_MIN_ADX": scalping_settings.SCALPING_UNIFIED_TREND_RECLAIM_MIN_ADX,
        "SCALPING_UNIFIED_MAX_ENTRY_VWAP_DISTANCE_ATR": scalping_settings.SCALPING_UNIFIED_MAX_ENTRY_VWAP_DISTANCE_ATR,
        "SCALPING_MIN_PROFIT_TARGET_USD": scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD,
        "SCALPING_MIN_STOP_LOSS_USD": scalping_settings.SCALPING_MIN_STOP_LOSS_USD,
        "SCALPING_SCORE_MARGIN_MIN_WINNER_SCORE": scalping_settings.SCALPING_SCORE_MARGIN_MIN_WINNER_SCORE,
        "SCALPING_SCORE_MARGIN_MIN_CONTEXT_ALIGNMENT": scalping_settings.SCALPING_SCORE_MARGIN_MIN_CONTEXT_ALIGNMENT,
        "SCALPING_SCORE_MARGIN_MAX_ABS_VWAP_ATR": scalping_settings.SCALPING_SCORE_MARGIN_MAX_ABS_VWAP_ATR,
        "SCALPING_SCORE_MARGIN_EXTENDED_VWAP_ATR": scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_VWAP_ATR,
        "SCALPING_SCORE_MARGIN_EXTENDED_MIN_MICRO_CONFIDENCE": scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_MIN_MICRO_CONFIDENCE,
        "SCALPING_SCORE_MARGIN_MIN_RELATIVE_VOLUME": scalping_settings.SCALPING_SCORE_MARGIN_MIN_RELATIVE_VOLUME,
        "SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE": scalping_settings.SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE,
        "SCALPING_TREND_LOOKBACK_CANDLES": scalping_settings.SCALPING_TREND_LOOKBACK_CANDLES,
        "SCALPING_CONFIRMATION_CANDLES": scalping_settings.SCALPING_CONFIRMATION_CANDLES,
        "SCALPING_TREND_MIN_NET_MOVE_ATR": scalping_settings.SCALPING_TREND_MIN_NET_MOVE_ATR,
        "SCALPING_TREND_MIN_SLOPE_SPAN_ATR": scalping_settings.SCALPING_TREND_MIN_SLOPE_SPAN_ATR,
        "SCALPING_TREND_MIN_EFFICIENCY": scalping_settings.SCALPING_TREND_MIN_EFFICIENCY,
        "SCALPING_ENTRY_MIN_SCORE_MARGIN": scalping_settings.SCALPING_ENTRY_MIN_SCORE_MARGIN,
        "SCALPING_ENTRY_MAX_ABS_VWAP_DISTANCE_ATR": scalping_settings.SCALPING_ENTRY_MAX_ABS_VWAP_DISTANCE_ATR,
        "SCALPING_ENTRY_MAX_FAST_EMA_DISTANCE_ATR": scalping_settings.SCALPING_ENTRY_MAX_FAST_EMA_DISTANCE_ATR,
        "SCALPING_ENTRY_MIN_RELATIVE_VOLUME": scalping_settings.SCALPING_ENTRY_MIN_RELATIVE_VOLUME,
        "SCALPING_TREND_ENTRY_MIN_WINNER_SCORE": scalping_settings.SCALPING_TREND_ENTRY_MIN_WINNER_SCORE,
        "SCALPING_TREND_ENTRY_MIN_MARGIN": scalping_settings.SCALPING_TREND_ENTRY_MIN_MARGIN,
        "SCALPING_TREND_CONTINUATION_MIN_SCORE": scalping_settings.SCALPING_TREND_CONTINUATION_MIN_SCORE,
        "SCALPING_TREND_CONTINUATION_MIN_MARGIN": scalping_settings.SCALPING_TREND_CONTINUATION_MIN_MARGIN,
        "SCALPING_TREND_CONTINUATION_MIN_ADX": scalping_settings.SCALPING_TREND_CONTINUATION_MIN_ADX,
        "SCALPING_TREND_CONTINUATION_MIN_RELATIVE_VOLUME": scalping_settings.SCALPING_TREND_CONTINUATION_MIN_RELATIVE_VOLUME,
        "SCALPING_TREND_CONTINUATION_MAX_VWAP_ATR": scalping_settings.SCALPING_TREND_CONTINUATION_MAX_VWAP_ATR,
        "SCALPING_TREND_CONTINUATION_MAX_EMA_ATR": scalping_settings.SCALPING_TREND_CONTINUATION_MAX_EMA_ATR,
        "SCALPING_NEUTRAL_TREND_MAX_SPREAD_USD": scalping_settings.SCALPING_NEUTRAL_TREND_MAX_SPREAD_USD,
        "SCALPING_NEUTRAL_TREND_MIN_WINNER_SCORE": scalping_settings.SCALPING_NEUTRAL_TREND_MIN_WINNER_SCORE,
        "SCALPING_NEUTRAL_TREND_MIN_MARGIN": scalping_settings.SCALPING_NEUTRAL_TREND_MIN_MARGIN,
        "SCALPING_NEUTRAL_TREND_MIN_CONFIRMATION_STRENGTH": scalping_settings.SCALPING_NEUTRAL_TREND_MIN_CONFIRMATION_STRENGTH,
        "SCALPING_NEUTRAL_TREND_MIN_CONFIRMATION_NET_ATR": scalping_settings.SCALPING_NEUTRAL_TREND_MIN_CONFIRMATION_NET_ATR,
        "SCALPING_NEUTRAL_TREND_MIN_RELATIVE_VOLUME": scalping_settings.SCALPING_NEUTRAL_TREND_MIN_RELATIVE_VOLUME,
        "SCALPING_NEUTRAL_TREND_MAX_ABS_VWAP_DISTANCE_ATR": scalping_settings.SCALPING_NEUTRAL_TREND_MAX_ABS_VWAP_DISTANCE_ATR,
        "SCALPING_NEUTRAL_TREND_MAX_FAST_EMA_DISTANCE_ATR": scalping_settings.SCALPING_NEUTRAL_TREND_MAX_FAST_EMA_DISTANCE_ATR,
        "SCALPING_ELEVATED_SPREAD_START_USD": scalping_settings.SCALPING_ELEVATED_SPREAD_START_USD,
        "SCALPING_ELEVATED_SPREAD_MIN_WINNER_SCORE": scalping_settings.SCALPING_ELEVATED_SPREAD_MIN_WINNER_SCORE,
        "SCALPING_ELEVATED_SPREAD_MIN_MARGIN": scalping_settings.SCALPING_ELEVATED_SPREAD_MIN_MARGIN,
        "SCALPING_STOP_ATR_PROFIT_RATIO": scalping_settings.SCALPING_STOP_ATR_PROFIT_RATIO,
        "SCALPING_MAX_HOLD_SECONDS": scalping_settings.SCALPING_MAX_HOLD_SECONDS,
        "SCALPING_LOSS_STREAK_COOLDOWN_AFTER_LOSSES": scalping_settings.SCALPING_LOSS_STREAK_COOLDOWN_AFTER_LOSSES,
        "SCALPING_LOSS_STREAK_COOLDOWN_SECONDS": scalping_settings.SCALPING_LOSS_STREAK_COOLDOWN_SECONDS,
        "SCALPING_MAX_DAILY_TRADES": scalping_settings.SCALPING_MAX_DAILY_TRADES,
        "SCALPING_MAX_TOTAL_OPEN_RISK_USD": scalping_settings.SCALPING_MAX_TOTAL_OPEN_RISK_USD,
        "SCALPING_MAX_SAME_DIRECTION_POSITIONS": scalping_settings.SCALPING_MAX_SAME_DIRECTION_POSITIONS,
        "SCALPING_DEMO_MAX_OPEN_POSITIONS": scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS,
        "SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD": scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD,
        "SCALPING_DEMO_MAX_LOT_SIZE": scalping_settings.SCALPING_DEMO_MAX_LOT_SIZE,
        "SCALPING_DEMO_MAX_DRAWDOWN_USD": scalping_settings.SCALPING_DEMO_MAX_DRAWDOWN_USD,
        "SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES": scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES,
        "SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS": scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS,
        "SCALPING_DEMO_MAX_SESSION_MINUTES": scalping_settings.SCALPING_DEMO_MAX_SESSION_MINUTES,
        "SCALPING_DEMO_MIN_PROFIT_TARGET_USD": scalping_settings.SCALPING_DEMO_MIN_PROFIT_TARGET_USD,
        "SCALPING_DEMO_MAX_PROFIT_TARGET_USD": scalping_settings.SCALPING_DEMO_MAX_PROFIT_TARGET_USD,
        "SCALPING_DEMO_MIN_STOP_LOSS_USD": scalping_settings.SCALPING_DEMO_MIN_STOP_LOSS_USD,
        "SCALPING_DEMO_MAX_STOP_LOSS_USD": scalping_settings.SCALPING_DEMO_MAX_STOP_LOSS_USD,
        "SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_CYCLES": scalping_settings.SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_CYCLES,
        "SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_SECONDS": scalping_settings.SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_SECONDS,
        "SCALPING_DEMO_ENTRY_MIN_WINNER_SCORE": scalping_settings.SCALPING_DEMO_ENTRY_MIN_WINNER_SCORE,
        "SCALPING_DEMO_ENTRY_MIN_SCORE_MARGIN": scalping_settings.SCALPING_DEMO_ENTRY_MIN_SCORE_MARGIN,
        "SCALPING_DEMO_MAX_DECISION_AGE_SECONDS": scalping_settings.SCALPING_DEMO_MAX_DECISION_AGE_SECONDS,
        "SCALPING_DEMO_MAX_ADVERSE_PRICE_MOVE_USD": scalping_settings.SCALPING_DEMO_MAX_ADVERSE_PRICE_MOVE_USD,
        "SCALPING_DEMO_MAX_ENTRY_SLIPPAGE_USD": scalping_settings.SCALPING_DEMO_MAX_ENTRY_SLIPPAGE_USD,
        "SCALPING_DEMO_EDGE_MEMORY_MIN_BUCKET_TRADES": scalping_settings.SCALPING_DEMO_EDGE_MEMORY_MIN_BUCKET_TRADES,
        "SCALPING_TICK_MAX_CURSOR_LAG_SECONDS": scalping_settings.SCALPING_TICK_MAX_CURSOR_LAG_SECONDS,
        "SCALPING_TICK_FUTURE_TOLERANCE_SECONDS": scalping_settings.SCALPING_TICK_FUTURE_TOLERANCE_SECONDS,
        "SCALPING_MAX_QUOTE_STALE_SECONDS": scalping_settings.SCALPING_MAX_QUOTE_STALE_SECONDS,
        "SCALPING_REAL_REVIEW_MIN_CLOSED_DEMO_TRADES": scalping_settings.SCALPING_REAL_REVIEW_MIN_CLOSED_DEMO_TRADES,
        "SCALPING_REAL_REVIEW_MIN_ACTIVE_DAYS": scalping_settings.SCALPING_REAL_REVIEW_MIN_ACTIVE_DAYS,
    }
    for name, value in positive_settings.items():
        if float(value) <= 0:
            errors.append(f"{name} must be greater than zero.")

    if float(scalping_settings.SCALPING_TICK_MAX_CURSOR_LAG_SECONDS) <= float(
        scalping_settings.SCALPING_TICK_INITIAL_LOOKBACK_SECONDS
    ):
        errors.append(
            "SCALPING_TICK_MAX_CURSOR_LAG_SECONDS must exceed the initial tick lookback."
        )
    if float(scalping_settings.SCALPING_MAX_QUOTE_STALE_SECONDS) < float(
        scalping_settings.SCALPING_LOOP_INTERVAL_SECONDS
    ):
        errors.append(
            "SCALPING_MAX_QUOTE_STALE_SECONDS cannot be shorter than the idle loop interval."
        )

    if float(scalping_settings.SCALPING_LOOP_INTERVAL_SECONDS) < 0.25:
        errors.append("SCALPING_LOOP_INTERVAL_SECONDS must be at least 0.25 seconds.")
    if float(scalping_settings.SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS) < 0.05:
        errors.append(
            "SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS must be at least 0.05 seconds."
        )
    if float(scalping_settings.SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS) > float(
        scalping_settings.SCALPING_LOOP_INTERVAL_SECONDS
    ):
        warnings.append(
            "Open-position monitoring is slower than the idle loop; profit protection may react late."
        )

    positions = int(scalping_settings.SCALPING_MAX_OPEN_POSITIONS)
    if positions < 1:
        errors.append("SCALPING_MAX_OPEN_POSITIONS must be at least 1.")
    if positions > 3:
        errors.append("Scalping supports at most 3 positions in the staged design.")
    if int(scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS) > 3:
        errors.append("Controlled demo mode supports at most 3 open positions.")
    if int(scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS) < 1:
        errors.append("SCALPING_DEMO_MAX_OPEN_POSITIONS must be at least 1.")
    if bool(scalping_settings.SCALPING_DEMO_TRADE_LIMIT_ENABLED):
        errors.append("Controlled demo trade-count limit must remain disabled in V6.")
    if int(scalping_settings.SCALPING_DEMO_MAX_DAILY_TRADES) != 0:
        warnings.append("Legacy SCALPING_DEMO_MAX_DAILY_TRADES should be 0 when trade limit is disabled.")
    if float(scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD) != 100.0:
        errors.append("Controlled demo cumulative loss limit must be exactly $100.")
    if int(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES) != 3:
        errors.append("V6 controlled demo circuit breaker must trigger after exactly 3 consecutive losses.")
    if float(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS) != 300.0:
        errors.append("V6 controlled demo cooldown must be exactly 300 seconds before returning to shadow validation.")
    recovery_after = int(scalping_settings.SCALPING_DEMO_RECOVERY_MODE_AFTER_LOSSES)
    if str(scalping_settings.SCALPING_STRATEGY_ID).startswith("XAUUSD_SCALP_V6_"):
        if recovery_after != 0:
            errors.append("V6 must disable the legacy loss-recovery entry policy; use approval revocation instead.")
    else:
        if recovery_after < 1:
            errors.append("Loss-recovery mode must activate after at least one loss.")
        if recovery_after >= int(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES):
            errors.append("Loss-recovery mode must activate before the full cooldown threshold.")
    if not 0.0 <= float(scalping_settings.SCALPING_DEMO_RECOVERY_MIN_MICRO_CONFIDENCE) <= 1.0:
        errors.append("Recovery microstructure confidence must be between 0 and 1.")
    if float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_FLOOR_USD) >= float(
        scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_USD
    ):
        errors.append("Demo stage-1 profit floor must remain below its trigger.")
    if float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_FLOOR_USD) >= float(
        scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_USD
    ):
        errors.append("Demo stage-2 profit floor must remain below its trigger.")
    if float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_USD) <= float(
        scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_USD
    ):
        errors.append("Demo stage-2 profit trigger must exceed stage 1.")
    if float(scalping_settings.SCALPING_DEMO_MAX_PROFIT_TARGET_USD) < float(
        scalping_settings.SCALPING_DEMO_MIN_PROFIT_TARGET_USD
    ):
        errors.append("Demo maximum profit target cannot be below its minimum target.")
    if float(scalping_settings.SCALPING_DEMO_MAX_STOP_LOSS_USD) < float(
        scalping_settings.SCALPING_DEMO_MIN_STOP_LOSS_USD
    ):
        errors.append("Demo maximum stop cannot be below its minimum stop.")
    if int(scalping_settings.SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_CYCLES) < 2:
        errors.append("Demo signal persistence must require at least two cycles.")
    if int(scalping_settings.SCALPING_DEMO_EDGE_MEMORY_PROBATION_MIN_TRADES) < 3:
        errors.append("Edge-memory probation must require at least three comparable trades.")
    if not 0.0 <= float(scalping_settings.SCALPING_DEMO_EDGE_MEMORY_PROBATION_MAX_QUALITY_PENALTY) <= 0.25:
        errors.append("Edge-memory probation quality penalty must be between 0 and 0.25.")
    for name in (
        "SCALPING_DEMO_ENTRY_MIN_QUALITY_INDEX",
        "SCALPING_DEMO_ELEVATED_SPREAD_MIN_QUALITY_INDEX",
        "SCALPING_DEMO_RECOVERY_MIN_QUALITY_INDEX",
        "SCALPING_DEMO_PYRAMID_MIN_QUALITY_INDEX",
        "SCALPING_DEMO_MAX_ADVERSE_MOVE_ATR_RATIO",
        "SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_RATIO",
        "SCALPING_DEMO_PROFIT_STAGE_1_FLOOR_RATIO",
        "SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_RATIO",
        "SCALPING_DEMO_PROFIT_STAGE_2_FLOOR_RATIO",
        "SCALPING_DEMO_PROFIT_STAGE_3_TRIGGER_RATIO",
        "SCALPING_DEMO_PROFIT_STAGE_3_FLOOR_RATIO",
    ):
        value = float(getattr(scalping_settings, name))
        if not 0.0 < value <= 1.0:
            errors.append(f"{name} must be in (0, 1].")
    if not (
        float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_RATIO)
        < float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_RATIO)
        < float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_3_TRIGGER_RATIO)
    ):
        errors.append("Dynamic demo profit-protection triggers must increase by stage.")
    if float(scalping_settings.SCALPING_DEMO_MAX_SPREAD_TARGET_RATIO) > float(
        scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_TARGET_RATIO
    ):
        errors.append("V5.2 demo spread/target limit cannot exceed the adaptive execution ceiling.")
    if float(scalping_settings.SCALPING_DEMO_MAX_DECISION_AGE_SECONDS) > float(
        scalping_settings.SCALPING_MAX_QUOTE_STALE_SECONDS
    ):
        errors.append("Decision-age limit cannot exceed the quote-staleness limit.")
    if bool(scalping_settings.SCALPING_DEMO_PEAK_DRAWDOWN_STOP_ENABLED):
        warnings.append("Peak-drawdown stop is enabled in addition to the requested cumulative -$100 stop.")
    if int(scalping_settings.SCALPING_MAX_SAME_DIRECTION_POSITIONS) > positions:
        warnings.append(
            "Same-direction limit exceeds the current total position limit; the total limit still applies."
        )

    minimum_target = float(scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD)
    maximum_target = float(scalping_settings.SCALPING_MAX_PROFIT_TARGET_USD)
    if maximum_target < minimum_target:
        errors.append("Maximum scalp target cannot be below the minimum target.")

    trailing_trigger = float(scalping_settings.SCALPING_BREAKEVEN_TRIGGER_USD)
    minimum_locked_profit = float(scalping_settings.SCALPING_MIN_LOCKED_PROFIT_USD)
    trailing_giveback = float(scalping_settings.SCALPING_TRAILING_GIVEBACK_USD)
    stage_2_trigger = float(scalping_settings.SCALPING_PROFIT_STAGE_2_TRIGGER_USD)
    stage_2_lock = float(scalping_settings.SCALPING_PROFIT_STAGE_2_LOCK_USD)
    stage_3_trigger = float(scalping_settings.SCALPING_PROFIT_STAGE_3_TRIGGER_USD)
    stage_3_lock = float(scalping_settings.SCALPING_PROFIT_STAGE_3_LOCK_USD)
    if trailing_trigger <= 0:
        errors.append("SCALPING_BREAKEVEN_TRIGGER_USD must be greater than zero.")
    if minimum_locked_profit < 0:
        errors.append("SCALPING_MIN_LOCKED_PROFIT_USD cannot be negative.")
    if not (trailing_trigger < stage_2_trigger < stage_3_trigger):
        errors.append("Profit-protection triggers must increase from stage 1 to stage 3.")
    if not (minimum_locked_profit <= stage_2_lock <= stage_3_lock):
        errors.append("Profit-protection lock values must increase from stage 1 to stage 3.")
    if stage_2_lock > stage_2_trigger or stage_3_lock > stage_3_trigger:
        errors.append("A profit-protection lock cannot exceed its trigger.")
    if trailing_giveback <= 0:
        errors.append("SCALPING_TRAILING_GIVEBACK_USD must be greater than zero.")

    minimum_stop = float(scalping_settings.SCALPING_MIN_STOP_LOSS_USD)
    maximum_stop = float(scalping_settings.SCALPING_MAX_STOP_LOSS_USD)

    paper_stop_slippage = float(
        scalping_settings.SCALPING_PAPER_STOP_SLIPPAGE_USD
    )
    if paper_stop_slippage < 0:
        errors.append("SCALPING_PAPER_STOP_SLIPPAGE_USD cannot be negative.")
    if paper_stop_slippage > maximum_stop:
        warnings.append(
            "Paper stop slippage exceeds the maximum configured stop size."
        )
    if not bool(scalping_settings.SCALPING_PAPER_PROTECTIVE_ORDERS_ENABLED):
        warnings.append(
            "Paper broker-side target/stop simulation is disabled."
        )
    if not bool(scalping_settings.SCALPING_CLOSE_OPEN_POSITIONS_ON_RUNNER_STOP):
        warnings.append(
            "Open paper scalps can remain unmanaged after the runner stops."
        )

    if maximum_stop < minimum_stop:
        errors.append("Maximum scalp stop cannot be below the minimum stop.")

    if not 0 <= float(scalping_settings.SCALPING_MIN_ENTRY_SCORE) <= 100:
        errors.append("SCALPING_MIN_ENTRY_SCORE must be between 0 and 100.")

    minimum_candles = max(55, int(scalping_settings.SCALPING_MIN_REQUIRED_CANDLES))
    for name in ("SCALPING_M1_CANDLES", "SCALPING_M5_CANDLES", "SCALPING_M15_CANDLES", "SCALPING_H1_CANDLES", "SCALPING_H4_CANDLES"):
        if int(getattr(scalping_settings, name)) < minimum_candles:
            errors.append(f"{name} must be at least {minimum_candles}.")
    timeframe_resync_minimums = {
        "SCALPING_M1_FULL_RESYNC_SECONDS": 60.0,
        "SCALPING_M5_FULL_RESYNC_SECONDS": 300.0,
        "SCALPING_M15_FULL_RESYNC_SECONDS": 900.0,
        "SCALPING_H1_FULL_RESYNC_SECONDS": 3600.0,
        "SCALPING_H4_FULL_RESYNC_SECONDS": 14400.0,
    }
    for name, minimum in timeframe_resync_minimums.items():
        if float(getattr(scalping_settings, name)) < minimum:
            errors.append(f"{name} must be at least {minimum:.0f} seconds.")
    if float(scalping_settings.SCALPING_CANDLE_BOUNDARY_GRACE_SECONDS) < 0:
        errors.append("SCALPING_CANDLE_BOUNDARY_GRACE_SECONDS cannot be negative.")
    if float(scalping_settings.SCALPING_SPREAD_COMPARISON_TOLERANCE_USD) < 0:
        errors.append("SCALPING_SPREAD_COMPARISON_TOLERANCE_USD cannot be negative.")
    if not bool(scalping_settings.SCALPING_PATCH_LIVE_M1_FROM_TICK):
        warnings.append("Live M1 tick patching is disabled; fast candle triggers may update late.")
    if float(scalping_settings.SCALPING_SLOW_PHASE_WARNING_MS) <= 0:
        errors.append("SCALPING_SLOW_PHASE_WARNING_MS must be greater than zero.")
    if not bool(scalping_settings.SCALPING_TIMING_DIAGNOSTICS_ENABLED):
        warnings.append("Per-phase timing diagnostics are disabled.")

    if not bool(scalping_settings.SCALPING_UNIFIED_INTELLIGENCE_ENABLED):
        errors.append("SCALPING_UNIFIED_INTELLIGENCE_ENABLED must remain True for V5.0.5.")
    if not bool(scalping_settings.SCALPING_UNIFIED_ATOME_FACTORS_ENABLED):
        errors.append("SCALPING_UNIFIED_ATOME_FACTORS_ENABLED must remain True for V5.0.5.")
    if not bool(scalping_settings.SCALPING_UNIFIED_REQUIRE_FACTOR_ENGINE):
        warnings.append("The unified factor-engine health gate is disabled.")
    if not 0 <= float(scalping_settings.SCALPING_UNIFIED_MIN_ENTRY_SCORE) <= 100:
        errors.append("SCALPING_UNIFIED_MIN_ENTRY_SCORE must be between 0 and 100.")
    if int(scalping_settings.SCALPING_UNIFIED_MIN_CONFIRMING_FAMILIES) < 2:
        errors.append("SCALPING_UNIFIED_MIN_CONFIRMING_FAMILIES must be at least 2.")
    if not bool(scalping_settings.SCALPING_UNIFIED_REQUIRE_ENTRY_TRIGGER_FAMILY):
        warnings.append("The mandatory entry-trigger family gate is disabled.")
    if not bool(scalping_settings.SCALPING_UNIFIED_REQUIRE_DIRECTIONAL_CONTEXT_FAMILY):
        warnings.append("The mandatory directional-context family gate is disabled.")
    if bool(getattr(scalping_settings, "SCALPING_DIRECT_SCORE_PAPER_ENABLED", False)):
        score_runtime = bool(
            scalping_settings.SCALPING_PAPER_ONLY
            or (
                scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED
                and not scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED
            )
        )
        if not score_runtime:
            errors.append("Direct-score mode requires paper mode or controlled demo mode.")
        if not 0.0 < float(scalping_settings.SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE) <= 100.0:
            errors.append("SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE must be in (0, 100].")

    if bool(getattr(scalping_settings, "SCALPING_SCORE_MARGIN_ENTRY_ENABLED", False)):
        score_runtime = bool(
            scalping_settings.SCALPING_PAPER_ONLY
            or (
                scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED
                and not scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED
            )
        )
        if not score_runtime:
            errors.append("Score-margin entry mode requires paper mode or controlled demo mode.")
        margin = float(scalping_settings.SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE)
        if not 0.0 < margin <= 100.0:
            errors.append("SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE must be in (0, 100].")
        opposition = float(scalping_settings.SCALPING_SCORE_MARGIN_STRONG_OPPOSITION_CONFIDENCE)
        if not 0.0 <= opposition <= 1.0:
            errors.append("SCALPING_SCORE_MARGIN_STRONG_OPPOSITION_CONFIDENCE must be between 0 and 1.")

    if float(scalping_settings.SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE) <= 0:
        errors.append("SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE must be greater than zero.")
    if float(scalping_settings.SCALPING_SCORE_MARGIN_MIN_WINNER_SCORE) > 100.0:
        errors.append("SCALPING_SCORE_MARGIN_MIN_WINNER_SCORE cannot exceed 100.")
    if int(scalping_settings.SCALPING_SCORE_MARGIN_MIN_CONTEXT_ALIGNMENT) < 1:
        errors.append("Score-margin context alignment must be at least one source.")
    if int(scalping_settings.SCALPING_SCORE_MARGIN_MAX_CONTEXT_OPPOSITION) < 0:
        errors.append("Score-margin context opposition cannot be negative.")
    if not 0.0 < float(scalping_settings.SCALPING_SCORE_MARGIN_MIN_RELATIVE_VOLUME) <= 5.0:
        errors.append("Score-margin relative-volume floor must be in (0, 5].")
    if float(scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_VWAP_ATR) >= float(
        scalping_settings.SCALPING_SCORE_MARGIN_MAX_ABS_VWAP_ATR
    ):
        errors.append("Extended VWAP threshold must remain below the absolute score-margin VWAP limit.")
    if not 0.0 < float(scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_MIN_MICRO_CONFIDENCE) <= 1.0:
        errors.append("Extended score-margin micro confidence must be in (0, 1].")

    if not bool(scalping_settings.SCALPING_TREND_CONFIRMATION_ENABLED):
        warnings.append("The retained V4 technical trend-context engine is disabled in V5.0.5.")
    if int(scalping_settings.SCALPING_TREND_LOOKBACK_CANDLES) < 10:
        errors.append("SCALPING_TREND_LOOKBACK_CANDLES must be at least 10.")
    if int(scalping_settings.SCALPING_CONFIRMATION_CANDLES) != 3:
        errors.append("SCALPING_CONFIRMATION_CANDLES must remain 3 for V5.0.5.")
    if not 2 <= int(scalping_settings.SCALPING_CONFIRMATION_MIN_DIRECTIONAL_CANDLES) <= 3:
        errors.append("SCALPING_CONFIRMATION_MIN_DIRECTIONAL_CANDLES must be 2 or 3.")
    if float(scalping_settings.SCALPING_ELEVATED_SPREAD_START_USD) >= float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD):
        errors.append("Elevated-spread threshold must be below the hard spread limit.")
    if bool(scalping_settings.SCALPING_ADAPTIVE_SPREAD_ENABLED) and float(scalping_settings.SCALPING_ADAPTIVE_HARD_MAX_ENTRY_SPREAD_USD) <= float(
        scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD
    ):
        errors.append("Adaptive hard spread ceiling must exceed the normal spread ceiling when adaptive spread is enabled.")
    if float(scalping_settings.SCALPING_ADAPTIVE_HARD_MAX_ENTRY_SPREAD_USD) > 0.40:
        errors.append("Adaptive hard spread ceiling cannot exceed $0.40 for this micro-scalp pilot.")
    if float(scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_TARGET_RATIO) <= float(
        scalping_settings.SCALPING_MAX_SPREAD_TARGET_RATIO
    ):
        errors.append("Adaptive spread/target ratio must exceed the normal ratio.")
    if float(scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_TARGET_RATIO) > 0.60:
        errors.append("Adaptive spread/target ratio cannot exceed 0.60.")
    if float(scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_ATR_RATIO) > 0.25:
        errors.append("Adaptive spread/ATR ratio cannot exceed 0.25.")
    if float(scalping_settings.SCALPING_ADAPTIVE_SPREAD_MIN_SCORE_MARGIN) < float(
        scalping_settings.SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE
    ):
        errors.append("Adaptive spread margin must be at least the normal score-margin threshold.")
    if float(scalping_settings.SCALPING_ADAPTIVE_SPREAD_MIN_WINNER_SCORE) < float(
        scalping_settings.SCALPING_SCORE_MARGIN_MIN_WINNER_SCORE
    ):
        errors.append("Adaptive spread winner floor cannot be below the score-margin winner floor.")
    if float(scalping_settings.SCALPING_ELEVATED_SPREAD_MIN_WINNER_SCORE) < float(scalping_settings.SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE):
        errors.append("Elevated-spread winner score cannot be below the normal winner score.")
    if int(scalping_settings.SCALPING_ENTRY_MIN_CONTEXT_SUPPORT_VOTES) < 1:
        errors.append("SCALPING_ENTRY_MIN_CONTEXT_SUPPORT_VOTES must be at least 1.")
    if int(scalping_settings.SCALPING_ENTRY_MAX_CONTEXT_OPPOSITION_VOTES) < 0:
        errors.append("SCALPING_ENTRY_MAX_CONTEXT_OPPOSITION_VOTES cannot be negative.")

    if float(scalping_settings.SCALPING_NEUTRAL_TREND_MAX_SPREAD_USD) >= float(scalping_settings.SCALPING_ELEVATED_SPREAD_START_USD):
        errors.append("Neutral-trend impulse spread must remain below the elevated-spread tier.")
    if float(scalping_settings.SCALPING_NEUTRAL_TREND_MIN_WINNER_SCORE) < float(scalping_settings.SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE):
        errors.append("Neutral-trend impulse score cannot be below the direct-score prefilter.")
    if not 0.0 < float(scalping_settings.SCALPING_NEUTRAL_TREND_MIN_CONFIRMATION_STRENGTH) <= 1.0:
        errors.append("Neutral-trend confirmation strength must be in (0, 1].")
    if int(scalping_settings.SCALPING_NEUTRAL_TREND_MIN_CONTEXT_SUPPORT_VOTES) < 2:
        errors.append("Neutral-trend impulse requires at least two context support votes.")
    if int(scalping_settings.SCALPING_NEUTRAL_TREND_MAX_CONTEXT_OPPOSITION_VOTES) < 0:
        errors.append("Neutral-trend opposition votes cannot be negative.")

    if int(scalping_settings.SCALPING_MICRO_BREAK_LOOKBACK_CANDLES) < 3:
        errors.append("SCALPING_MICRO_BREAK_LOOKBACK_CANDLES must be at least 3.")
    if not 0.0 < float(scalping_settings.SCALPING_MICRO_BREAK_BUFFER_ATR) <= 0.25:
        errors.append("SCALPING_MICRO_BREAK_BUFFER_ATR must be in (0, 0.25].")
    if float(scalping_settings.SCALPING_MICRO_BREAK_MAX_SPREAD_USD) > float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD):
        errors.append("Micro-break spread limit cannot exceed the global spread limit.")
    if int(scalping_settings.SCALPING_MICRO_BREAK_MIN_SUPPORT) < 3:
        errors.append("Micro-break continuation requires at least three context support votes.")
    if float(scalping_settings.SCALPING_MICRO_BREAK_MAX_VWAP_ATR) <= 0:
        errors.append("Micro-break VWAP distance must be greater than zero.")

    if not tuple(scalping_settings.SCALPING_UNIFIED_DIRECTIONAL_CONTEXT_FAMILIES):
        errors.append("SCALPING_UNIFIED_DIRECTIONAL_CONTEXT_FAMILIES cannot be empty.")
    if int(scalping_settings.SCALPING_UNIFIED_FACTOR_ATR_LOOKBACK) < 20:
        errors.append("SCALPING_UNIFIED_FACTOR_ATR_LOOKBACK must be at least 20.")
    if float(scalping_settings.SCALPING_UNIFIED_ASIAN_MAX_SPREAD_USD) > float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD):
        errors.append("The Asian-session spread limit cannot exceed the global spread limit.")
    if float(scalping_settings.SCALPING_UNIFIED_ASIAN_MIN_SCORE) < float(scalping_settings.SCALPING_UNIFIED_MIN_ENTRY_SCORE):
        errors.append("The Asian-session minimum score must be at least the global unified score.")

    if not bool(scalping_settings.SCALPING_VERIFIED_MARKET_CONTEXT_ENABLED):
        errors.append("SCALPING_VERIFIED_MARKET_CONTEXT_ENABLED must remain True for V5.0.5.")
    if not 0.0 <= float(scalping_settings.SCALPING_VERIFIED_MIN_DATA_QUALITY_SCORE) <= 1.0:
        errors.append("SCALPING_VERIFIED_MIN_DATA_QUALITY_SCORE must be between 0 and 1.")
    for name, minimum in {
        "SCALPING_VERIFIED_VOLUME_LOOKBACK": 10,
        "SCALPING_VERIFIED_DELTA_PROXY_LOOKBACK": 5,
        "SCALPING_VERIFIED_VWAP_LOOKBACK": 30,
        "SCALPING_CROSS_MARKET_M5_LOOKBACK": 1,
        "SCALPING_CROSS_MARKET_MIN_SYMBOLS": 1,
        "SCALPING_MIN_REAL_TRADES_BEFORE_ML_RESEARCH": 50,
    }.items():
        if int(getattr(scalping_settings, name)) < minimum:
            errors.append(f"{name} must be at least {minimum}.")
    if float(scalping_settings.SCALPING_CROSS_MARKET_REFRESH_SECONDS) < 15.0:
        errors.append("SCALPING_CROSS_MARKET_REFRESH_SECONDS must be at least 15 seconds.")
    if float(scalping_settings.SCALPING_CROSS_MARKET_RETURN_SCALE) <= 0:
        errors.append("SCALPING_CROSS_MARKET_RETURN_SCALE must be greater than zero.")
    if not 0.0 < float(scalping_settings.SCALPING_CROSS_MARKET_BIAS_THRESHOLD) <= 1.0:
        errors.append("SCALPING_CROSS_MARKET_BIAS_THRESHOLD must be in (0, 1].")

    # V5 tick/microstructure/execution-audit validation.
    for dependency in ("pyarrow", "duckdb", "sklearn", "joblib"):
        if importlib.util.find_spec(dependency) is None:
            errors.append(
                f"Required research dependency '{dependency}' is missing. "
                "Run: pip install -r requirements.txt"
            )

    instance_lock_path = str(scalping_settings.SCALPING_INSTANCE_LOCK_PATH).strip()
    if not instance_lock_path:
        errors.append("SCALPING_INSTANCE_LOCK_PATH cannot be empty.")

    if bool(scalping_settings.SCALPING_META_PROMOTE_TICK_CONFIRMED_CANDIDATE):
        if not bool(scalping_settings.SCALPING_META_CONTROLLER_ENABLED):
            errors.append("Tick-confirmed candidate promotion requires the meta-controller.")
        if not 0.0 < float(scalping_settings.SCALPING_META_PROMOTION_MIN_SCORE) <= 100.0:
            errors.append("SCALPING_META_PROMOTION_MIN_SCORE must be in (0, 100].")
        if float(scalping_settings.SCALPING_META_PROMOTION_MIN_MARGIN) <= 0:
            errors.append("SCALPING_META_PROMOTION_MIN_MARGIN must be greater than zero.")
        if int(scalping_settings.SCALPING_META_PROMOTION_MIN_CONTEXT_SUPPORT) < 3:
            errors.append("Tick promotion requires at least three context support votes.")
        if int(scalping_settings.SCALPING_META_PROMOTION_MAX_CONTEXT_OPPOSITION) < 0:
            errors.append("Tick-promotion opposition votes cannot be negative.")
        if not 0.0 < float(scalping_settings.SCALPING_META_PROMOTION_MIN_MICRO_CONFIDENCE) <= 1.0:
            errors.append("SCALPING_META_PROMOTION_MIN_MICRO_CONFIDENCE must be in (0, 1].")
        if float(scalping_settings.SCALPING_META_PROMOTION_MIN_ADX) <= 0:
            errors.append("SCALPING_META_PROMOTION_MIN_ADX must be greater than zero.")
        if float(scalping_settings.SCALPING_META_PROMOTION_MIN_RELATIVE_VOLUME) <= 0:
            errors.append("SCALPING_META_PROMOTION_MIN_RELATIVE_VOLUME must be greater than zero.")
        if float(scalping_settings.SCALPING_META_PROMOTION_MAX_VWAP_ATR) <= 0:
            errors.append("SCALPING_META_PROMOTION_MAX_VWAP_ATR must be greater than zero.")
        if float(scalping_settings.SCALPING_META_PROMOTION_MAX_EMA_ATR) <= 0:
            errors.append("SCALPING_META_PROMOTION_MAX_EMA_ATR must be greater than zero.")

    if bool(scalping_settings.SCALPING_MICROSTRUCTURE_ENTRY_GATE_ENABLED):
        if not bool(scalping_settings.SCALPING_TICK_RECORDER_ENABLED):
            errors.append(
                "The microstructure entry gate requires SCALPING_TICK_RECORDER_ENABLED=True."
            )
        if not bool(scalping_settings.SCALPING_MICROSTRUCTURE_ENABLED):
            errors.append(
                "The microstructure entry gate requires SCALPING_MICROSTRUCTURE_ENABLED=True."
            )
        if not bool(scalping_settings.SCALPING_META_CONTROLLER_ENABLED):
            errors.append(
                "The microstructure entry gate requires SCALPING_META_CONTROLLER_ENABLED=True."
            )

    windows = tuple(float(value) for value in scalping_settings.SCALPING_MICROSTRUCTURE_WINDOWS_SECONDS)
    if not {1.0, 3.0, 5.0}.issubset(set(windows)):
        errors.append(
            "SCALPING_MICROSTRUCTURE_WINDOWS_SECONDS must include 1, 3 and 5 seconds."
        )
    for name in (
        "SCALPING_TICK_BUFFER_MAX_ROWS",
        "SCALPING_TICK_MAX_BATCH",
        "SCALPING_MICROSTRUCTURE_MIN_TICKS",
        "SCALPING_MICROSTRUCTURE_FEATURE_BUFFER_MAX_ROWS",
        "SCALPING_EXECUTION_AUDIT_BUFFER_MAX_ROWS",
    ):
        if int(getattr(scalping_settings, name)) <= 0:
            errors.append(f"{name} must be greater than zero.")
    for name in (
        "SCALPING_TICK_FLUSH_INTERVAL_SECONDS",
        "SCALPING_TICK_INITIAL_LOOKBACK_SECONDS",
        "SCALPING_TICK_CURSOR_OVERLAP_SECONDS",
        "SCALPING_TICK_RECENT_MEMORY_SECONDS",
        "SCALPING_MICROSTRUCTURE_MIN_SPAN_SECONDS",
        "SCALPING_MICROSTRUCTURE_FEATURE_FLUSH_INTERVAL_SECONDS",
        "SCALPING_EXECUTION_AUDIT_FLUSH_INTERVAL_SECONDS",
    ):
        if float(getattr(scalping_settings, name)) <= 0:
            errors.append(f"{name} must be greater than zero.")
    for name in (
        "SCALPING_MICROSTRUCTURE_MIN_DATA_QUALITY",
        "SCALPING_V6_MIN_MICRO_DATA_QUALITY",
        "SCALPING_V6_MIN_ALIGNED_QUOTE_FLOW_IMBALANCE",
        "SCALPING_V6_MAX_SPREAD_EXPANSION_ATR",
        "SCALPING_META_MIN_CONFIDENCE",
        "SCALPING_INTERMARKET_STRONG_OPPOSITION_THRESHOLD",
    ):
        value = float(getattr(scalping_settings, name))
        if not 0.0 <= value <= 1.0:
            errors.append(f"{name} must be between 0 and 1.")
    blocked_regimes = {str(value).upper() for value in scalping_settings.SCALPING_V6_BLOCKED_MICRO_REGIMES}
    if not {"STALLED", "DISLOCATED"}.issubset(blocked_regimes):
        errors.append("SCALPING_V6_BLOCKED_MICRO_REGIMES must block STALLED and DISLOCATED.")
    context_regimes = {str(value).upper() for value in scalping_settings.SCALPING_V6_STRICT_BLOCKED_CONTEXT_REGIMES}
    if "NO_TRADE" not in context_regimes:
        errors.append("SCALPING_V6_STRICT_BLOCKED_CONTEXT_REGIMES must block NO_TRADE.")
    if not bool(scalping_settings.SCALPING_V6_STRICT_REQUIRE_CONTEXT_DIRECTION_ALIGNMENT):
        errors.append("STRICT V6 must require context-regime direction alignment.")
    if not 0.0 < float(scalping_settings.SCALPING_V6_FAST_MAX_SPREAD_USD) <= float(scalping_settings.SCALPING_V6_MAX_SPREAD_USD):
        errors.append("FAST spread ceiling must be positive and no wider than STRICT.")
    if not 0.0 < float(scalping_settings.SCALPING_V6_FAST_MAX_HOLD_SECONDS) < float(scalping_settings.SCALPING_V6_MAX_HOLD_SECONDS):
        errors.append("FAST hold must be positive and shorter than STRICT.")
    if not 0.0 <= float(scalping_settings.SCALPING_V6_FAST_MIN_MICRO_DATA_QUALITY) <= 1.0:
        errors.append("FAST micro data quality must be between 0 and 1.")
    if not bool(scalping_settings.SCALPING_EXECUTION_AUDIT_ENABLED):
        warnings.append(
            "Execution audit is disabled; V5 cannot diagnose slippage or lifecycle timing."
        )

    staged_counts = [
        int(scalping_settings.SCALPING_BASELINE_MIN_CLOSED_TRADES),
        int(scalping_settings.SCALPING_TWO_POSITION_MIN_TRADES),
        int(scalping_settings.SCALPING_DEMO_MIN_PAPER_TRADES),
        int(scalping_settings.SCALPING_THREE_POSITION_MIN_TRADES),
    ]
    if any(value <= 0 for value in staged_counts):
        errors.append("All staged readiness trade requirements must be positive.")
    if int(scalping_settings.SCALPING_TWO_POSITION_MIN_TRADES) < int(
        scalping_settings.SCALPING_BASELINE_MIN_CLOSED_TRADES
    ):
        errors.append("Two-position review cannot require fewer trades than baseline.")
    if int(scalping_settings.SCALPING_THREE_POSITION_MIN_TRADES) < int(
        scalping_settings.SCALPING_TWO_POSITION_MIN_TRADES
    ):
        errors.append("Three-position review cannot require fewer trades than two-position review.")

    if int(scalping_settings.SCALPING_MAX_DAILY_TRADES) > 50:
        warnings.append(
            "Daily scalp limit is above the V2 50-trade validation ceiling."
        )
    if positions > 1:
        warnings.append(
            "More than one paper scalp position is enabled; verify the readiness report first."
        )
    if bool(scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED):
        warnings.append("Controlled MT5 demo code is available but remains locked behind V6 walk-forward approval.")
        if bool(scalping_settings.SCALPING_PAPER_ONLY):
            errors.append("Demo execution requires SCALPING_PAPER_ONLY=False.")
        if float(scalping_settings.SCALPING_LOT_SIZE) > float(scalping_settings.SCALPING_DEMO_MAX_LOT_SIZE) + 1e-12:
            errors.append("SCALPING_LOT_SIZE exceeds the controlled demo pilot cap.")
        if bool(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED):
            errors.append("Real execution must remain disabled in demo pilot mode.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "settings_checked": sum(1 for name in dir(scalping_settings) if name.startswith("SCALPING_")),
    }


def print_scalping_config_report() -> dict:
    result = validate_scalping_config()
    print("")
    print("=" * 70)
    print("SCALPING CONFIGURATION REPORT")
    print("=" * 70)
    print(f"Status: {'VALID' if result['valid'] else 'INVALID'}")
    print(f"Settings Checked: {result['settings_checked']}")
    print(f"Paper Only: {'YES' if scalping_settings.SCALPING_PAPER_ONLY else 'NO'}")
    print(
        "Demo Execution Enabled: "
        f"{'YES' if scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED else 'NO'}"
    )
    print(
        "Real Account Execution Enabled: "
        f"{'YES' if scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED else 'NO'}"
    )
    print(
        "Core Live Trading Disabled: "
        f"{'YES' if not core_settings.ENABLE_LIVE_TRADING else 'NO'}"
    )

    if result["errors"]:
        print("Errors:")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Errors: None")

    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    else:
        print("Warnings: None")

    print("=" * 70)
    print("")
    return result
