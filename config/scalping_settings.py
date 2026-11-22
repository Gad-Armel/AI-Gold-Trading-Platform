"""V6.3.6 tick-horizon fast-shadow research settings.

The signal engine retains the V5.0.5 quality rules, tick capture, 1/3/5-second
microstructure features and agent consensus. The distributed demo runner can
submit orders only after a process-local confirmation and repeated verification
that the connected MT5 account is DEMO. Core live/real execution remains off.
"""

import os

from config import settings as core_settings


# ======================================================================
# MODE AND SAFETY
# ======================================================================

SCALPING_ENABLED = True
SCALPING_PAPER_ONLY = False
SCALPING_INSTANCE_LOCK_PATH = "data/runtime/scalping_loop.lock"
SCALPING_STRATEGY_ID = "XAUUSD_SCALP_V6_3_6_TICK_HORIZON_RESEARCH"

# The scalping runner refuses to start if the main platform has live
# trading enabled. This keeps the development phase strictly paper-only.
REQUIRE_CORE_LIVE_TRADING_DISABLED = True


# ======================================================================
# SYMBOL AND POSITION SIZE
# ======================================================================

SCALPING_SYMBOL = core_settings.SYMBOL
SCALPING_LOT_SIZE = core_settings.LOT_SIZE
SCALPING_MAGIC_NUMBER = 2026075110
SCALPING_CONTRACT_SIZE_FALLBACK = 100.0

# Start with one simulated position. Increase only after a successful
# paper-trading review. The manager already supports 2 or 3 later.
SCALPING_MAX_OPEN_POSITIONS = 1


# ======================================================================
# LOOP SPEED
# ======================================================================

SCALPING_LOOP_INTERVAL_SECONDS = 0.25

# When a position is open, monitor profit more frequently than idle entry scans.
# This reduces profit giveback and makes the paper model closer to fast scalping.
SCALPING_OPEN_POSITION_MONITOR_INTERVAL_SECONDS = 0.10

# Zero means unlimited cycles until CTRL+C or the emergency stop is used.
SCALPING_MAX_CYCLES = 0


# ======================================================================
# PRICE, SPREAD, AND SESSION FILTERS
# ======================================================================

SCALPING_MAX_ENTRY_SPREAD_USD = 0.27
# The normal ceiling remains $0.32. A narrow elevated band up to $0.38 is
# available only to strong score-margin candidates with favorable economics,
# fresh quotes and acceptable spread/ATR. Spreads above $0.38 always block.
SCALPING_ADAPTIVE_SPREAD_ENABLED = False
SCALPING_ADAPTIVE_HARD_MAX_ENTRY_SPREAD_USD = 0.27
SCALPING_ADAPTIVE_SPREAD_MIN_WINNER_SCORE = 30.0
SCALPING_ADAPTIVE_SPREAD_MIN_SCORE_MARGIN = 15.0
SCALPING_ADAPTIVE_MAX_SPREAD_TARGET_RATIO = 0.55
SCALPING_ADAPTIVE_MAX_SPREAD_ATR_RATIO = 0.20
SCALPING_ADAPTIVE_MIN_REWARD_RISK_RATIO = 1.20
# Floating-point tolerance prevents an apparent 0.320 spread from being
# rejected when the broker value is internally 0.3200000000001.
SCALPING_SPREAD_COMPARISON_TOLERANCE_USD = 0.000001
SCALPING_EMERGENCY_EXIT_SPREAD_USD = 1.25
SCALPING_BLOCK_OFF_SESSION = True
SCALPING_ALLOW_ASIAN_SESSION = False
SCALPING_ALLOW_LONDON_SESSION = True
SCALPING_ALLOW_NEW_YORK_SESSION = True


# ======================================================================
# CANDLE DATA
# ======================================================================

SCALPING_M1_CANDLES = 180
SCALPING_M5_CANDLES = 160
SCALPING_M15_CANDLES = 140
SCALPING_H1_CANDLES = 120
SCALPING_H4_CANDLES = 100
SCALPING_MIN_REQUIRED_CANDLES = 55


# ======================================================================
# SIGNAL ENGINE
# ======================================================================

SCALPING_FAST_EMA_PERIOD = 5
SCALPING_SLOW_EMA_PERIOD = 13
SCALPING_CONTEXT_EMA_PERIOD = 34
SCALPING_ATR_PERIOD = 14
SCALPING_RSI_PERIOD = 14
SCALPING_BREAKOUT_LOOKBACK = 8
SCALPING_MOMENTUM_LOOKBACK = 3

SCALPING_MIN_ENTRY_SCORE = 72.0
SCALPING_DIRECTION_TIE_MARGIN = 6.0

SCALPING_BUY_RSI_MIN = 48.0
SCALPING_BUY_RSI_MAX = 58.0
SCALPING_SELL_RSI_MIN = 30.0
SCALPING_SELL_RSI_MAX = 45.0

# Legacy entry-quality values remain available to the analytical engine.
# They do not limit repeated paper entries once the previous position closes.
SCALPING_REQUIRE_PRICE_SIDE_CONFIRMATION = True
SCALPING_MIN_DIRECTIONAL_MOMENTUM_USD = 0.10
SCALPING_MAX_BREAKOUT_DISTANCE_ATR_RATIO = 0.50
SCALPING_MAX_PULLBACK_DISTANCE_ATR_RATIO = 0.20
SCALPING_ENABLE_MOMENTUM_IMPULSE = False

# Avoid dead markets and extreme one-minute movement.
SCALPING_MIN_M1_ATR_USD = 0.20
SCALPING_MAX_M1_ATR_USD = 8.00

# Signal keys remain journal metadata only; they do not block re-entry.
SCALPING_SIGNAL_PRICE_BUCKET_USD = 0.25



# ======================================================================
# V3 UNIFIED MARKET INTELLIGENCE
# ======================================================================

SCALPING_UNIFIED_INTELLIGENCE_ENABLED = True
SCALPING_UNIFIED_MIN_ENTRY_SCORE = 74.0

# Borderline-score acceptance preserves fully qualified setups near the threshold. This does not
# lower the global threshold. It only prevents a fully qualified setup from
# being rejected for a tiny sub-point shortfall caused by continuous indicator
# values and score rounding. All hard gates must already pass.
SCALPING_UNIFIED_BORDERLINE_SCORE_ENABLED = True
SCALPING_UNIFIED_BORDERLINE_SCORE_TOLERANCE = 0.25
SCALPING_UNIFIED_BORDERLINE_MIN_CONFIRMING_FAMILIES = 5
SCALPING_UNIFIED_BORDERLINE_MIN_DIRECTION_MARGIN = 20.0
SCALPING_UNIFIED_BORDERLINE_MIN_DATA_COMPLETENESS = 0.95
SCALPING_UNIFIED_BORDERLINE_ALLOWED_REGIMES = ("TREND", "BREAKOUT", "REVERSAL")

# Legacy direct-score candidate policy. The higher unified BUY/SELL score still
# identifies a direction candidate, but V4 playbooks and the V5 microstructure
# meta-controller must independently confirm the timing. Exact ties wait. Hard
# spread, news, risk and position protections remain active. Re-entry can still
# occur immediately after a close when every current gate passes.
SCALPING_DIRECT_SCORE_PAPER_ENABLED = True
# The higher score still chooses direction, but very weak market votes no longer
# create trades. This transparent floor replaces unconditional low-quality entry.
SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE = 1.0

# Trend-context diagnostics retained for V4.0 playbook analysis. The score winner still identifies the
# candidate direction, but entry now requires that direction to match a
# 20-closed-candle M1 trend and a 3-candle confirmation. This reduces noisy
# score flips and contradictory trades without adding a time-based cooldown.
SCALPING_TREND_CONFIRMATION_ENABLED = True
SCALPING_TREND_LOOKBACK_CANDLES = 20
SCALPING_TREND_MIN_NET_MOVE_ATR = 0.35
SCALPING_TREND_MIN_SLOPE_SPAN_ATR = 0.30
SCALPING_TREND_MIN_EFFICIENCY = 0.18
SCALPING_CONFIRMATION_CANDLES = 3
SCALPING_CONFIRMATION_MIN_DIRECTIONAL_CANDLES = 2
SCALPING_CONFIRMATION_MIN_NET_MOVE_ATR = 0.05
SCALPING_CONFIRMATION_MAX_OPPOSING_BODY_ATR = 0.20

# Quality/pacing rules. These are signal-quality gates, not cooldowns. The bot
# may still re-enter immediately after a close when the conditions remain true.
SCALPING_ENTRY_MIN_SCORE_MARGIN = 10.0
SCALPING_ENTRY_MIN_CONTEXT_SUPPORT_VOTES = 2
SCALPING_ENTRY_MAX_CONTEXT_OPPOSITION_VOTES = 2
SCALPING_ENTRY_MAX_ABS_VWAP_DISTANCE_ATR = 2.50
SCALPING_ENTRY_MAX_FAST_EMA_DISTANCE_ATR = 1.25
SCALPING_ENTRY_MIN_RELATIVE_VOLUME = 0.75
SCALPING_ENTRY_BLOCK_LOW_LIQUIDITY = True
SCALPING_ENTRY_BUY_RSI_MIN = 35.0
SCALPING_ENTRY_BUY_RSI_MAX = 72.0
SCALPING_ENTRY_SELL_RSI_MIN = 28.0
SCALPING_ENTRY_SELL_RSI_MAX = 65.0

# Superseded trend/impulse values remain disabled for configuration compatibility.
# V4.0 execution uses only the closed-candle playbooks defined below.
SCALPING_TREND_ENTRY_MIN_WINNER_SCORE = 28.0
SCALPING_TREND_ENTRY_MIN_MARGIN = 8.0
SCALPING_NEUTRAL_TREND_IMPULSE_ENABLED = False
SCALPING_NEUTRAL_TREND_MAX_SPREAD_USD = 0.18
SCALPING_NEUTRAL_TREND_MIN_WINNER_SCORE = 24.0
SCALPING_NEUTRAL_TREND_MIN_MARGIN = 12.0
SCALPING_NEUTRAL_TREND_MIN_CONFIRMATION_STRENGTH = 0.70
SCALPING_NEUTRAL_TREND_MIN_CONFIRMATION_NET_ATR = 0.50
SCALPING_NEUTRAL_TREND_MIN_CONTEXT_SUPPORT_VOTES = 2
SCALPING_NEUTRAL_TREND_MAX_CONTEXT_OPPOSITION_VOTES = 1
SCALPING_NEUTRAL_TREND_MIN_RELATIVE_VOLUME = 0.90
SCALPING_NEUTRAL_TREND_MAX_ABS_VWAP_DISTANCE_ATR = 1.50
SCALPING_NEUTRAL_TREND_MAX_FAST_EMA_DISTANCE_ATR = 1.00

# V4.0 regime-playbook execution. The score winner is only the candidate;
# entry requires a closed-candle pullback, retest, or range rejection. These
# settings intentionally prevent late trend chasing near support/resistance or
# several ATR away from VWAP.
SCALPING_PLAYBOOK_MIN_RELATIVE_VOLUME = 0.80
SCALPING_MAX_SPREAD_ATR_RATIO = 0.18
SCALPING_STRONG_CROSS_MARKET_PRESSURE = 0.55

SCALPING_TREND_MIN_ADX = 18.0
SCALPING_TREND_PULLBACK_MIN_SCORE = 30.0
SCALPING_TREND_PULLBACK_MIN_MARGIN = 8.0
SCALPING_TREND_PULLBACK_MIN_SUPPORT = 3
SCALPING_TREND_PULLBACK_MAX_OPPOSITION = 1
SCALPING_TREND_PULLBACK_MAX_VWAP_ATR = 2.00
SCALPING_TREND_PULLBACK_MAX_EMA_ATR = 0.75
SCALPING_TREND_PULLBACK_BUY_RSI_MIN = 42.0
SCALPING_TREND_PULLBACK_BUY_RSI_MAX = 66.0
SCALPING_TREND_PULLBACK_SELL_RSI_MIN = 34.0
SCALPING_TREND_PULLBACK_SELL_RSI_MAX = 58.0

# V4.0.2 balanced continuation path. This is less rigid than a textbook
# pullback/retest, but it still requires closed-candle pressure, broad context
# agreement, reasonable location and non-extended price. It is designed to
# restore a moderate trade pace without returning to score-only execution.
SCALPING_TREND_CONTINUATION_MIN_SCORE = 38.0
SCALPING_TREND_CONTINUATION_MIN_MARGIN = 12.0
SCALPING_TREND_CONTINUATION_MIN_SUPPORT = 3
SCALPING_TREND_CONTINUATION_MAX_OPPOSITION = 1
SCALPING_TREND_CONTINUATION_MAX_VWAP_ATR = 2.50
SCALPING_TREND_CONTINUATION_MAX_EMA_ATR = 1.00
SCALPING_TREND_CONTINUATION_MIN_ADX = 22.0
SCALPING_TREND_CONTINUATION_MIN_RELATIVE_VOLUME = 0.85
SCALPING_TREND_CONTINUATION_MAX_OPPOSITE_TREND_STRENGTH = 0.45
SCALPING_TREND_CONTINUATION_BUY_RSI_MIN = 44.0
SCALPING_TREND_CONTINUATION_BUY_RSI_MAX = 68.0
SCALPING_TREND_CONTINUATION_SELL_RSI_MIN = 32.0
SCALPING_TREND_CONTINUATION_SELL_RSI_MAX = 56.0

# V4.0.2 adaptive micro-break path. Closed candles establish the local range;
# the live M1 price must break that range before a dominant aligned context may
# enter. This restores moderate activity without blindly trading into support
# or resistance while those levels are still holding.
SCALPING_MICRO_BREAK_LOOKBACK_CANDLES = 5
SCALPING_MICRO_BREAK_BUFFER_ATR = 0.03
SCALPING_MICRO_BREAK_MIN_LIVE_BODY_ATR = 0.04
SCALPING_MICRO_BREAK_MIN_SCORE = 48.0
SCALPING_MICRO_BREAK_MIN_MARGIN = 25.0
SCALPING_MICRO_BREAK_MIN_SUPPORT = 4
SCALPING_MICRO_BREAK_MAX_OPPOSITION = 1
SCALPING_MICRO_BREAK_MAX_VWAP_ATR = 3.25
SCALPING_MICRO_BREAK_MAX_EMA_ATR = 0.55
SCALPING_MICRO_BREAK_MIN_ADX = 25.0
SCALPING_MICRO_BREAK_MIN_RELATIVE_VOLUME = 1.00
SCALPING_MICRO_BREAK_MAX_SPREAD_USD = 0.27
SCALPING_MICRO_BREAK_MAX_OPPOSITE_TREND_STRENGTH = 0.30
SCALPING_MICRO_BREAK_BUY_RSI_MIN = 45.0
SCALPING_MICRO_BREAK_BUY_RSI_MAX = 68.0
SCALPING_MICRO_BREAK_SELL_RSI_MIN = 35.0
SCALPING_MICRO_BREAK_SELL_RSI_MAX = 55.0

SCALPING_BREAKOUT_MIN_ADX = 20.0
SCALPING_BREAKOUT_RETEST_MIN_SCORE = 36.0
SCALPING_BREAKOUT_RETEST_MIN_MARGIN = 12.0
SCALPING_BREAKOUT_RETEST_MIN_SUPPORT = 3
SCALPING_BREAKOUT_RETEST_MAX_OPPOSITION = 1
SCALPING_BREAKOUT_RETEST_MAX_VWAP_ATR = 2.25
SCALPING_BREAKOUT_RETEST_MAX_EMA_ATR = 0.90
SCALPING_BREAKOUT_RETEST_BUY_RSI_MIN = 48.0
SCALPING_BREAKOUT_RETEST_BUY_RSI_MAX = 70.0
SCALPING_BREAKOUT_RETEST_SELL_RSI_MIN = 30.0
SCALPING_BREAKOUT_RETEST_SELL_RSI_MAX = 52.0

SCALPING_RANGE_MAX_ADX = 22.0
SCALPING_RANGE_REJECTION_MIN_SCORE = 34.0
SCALPING_RANGE_REJECTION_MIN_MARGIN = 12.0
SCALPING_RANGE_REJECTION_MIN_SUPPORT = 1
SCALPING_RANGE_REJECTION_MAX_OPPOSITION = 1
SCALPING_RANGE_REJECTION_MAX_VWAP_ATR = 1.00
SCALPING_RANGE_REJECTION_MAX_EMA_ATR = 0.55
SCALPING_RANGE_REJECTION_BUY_RSI_MIN = 28.0
SCALPING_RANGE_REJECTION_BUY_RSI_MAX = 45.0
SCALPING_RANGE_REJECTION_SELL_RSI_MIN = 55.0
SCALPING_RANGE_REJECTION_SELL_RSI_MAX = 72.0

# When spread is close to the $0.30 hard ceiling, require a materially stronger
# setup so transaction cost does not consume the fixed $0.30 target.
SCALPING_ELEVATED_SPREAD_START_USD = 0.20
SCALPING_ELEVATED_SPREAD_MIN_WINNER_SCORE = 40.0
SCALPING_ELEVATED_SPREAD_MIN_MARGIN = 18.0
SCALPING_ELEVATED_SPREAD_MIN_TREND_STRENGTH = 0.55
SCALPING_ELEVATED_SPREAD_REQUIRE_THREE_OF_THREE = True

# Early-loss protection: close an open paper scalp when the 3-candle
# confirmation and raw score winner both flip against it. This can cut losses
# before the volatility stop while preserving the fixed $0.30 target.
SCALPING_FAST_CONFIRMATION_EXIT_ENABLED = True

SCALPING_UNIFIED_MIN_CONFIRMING_FAMILIES = 3
# The total family count alone is not sufficient. A valid trade must contain
# both a concrete entry trigger and directional market context.
SCALPING_UNIFIED_REQUIRE_ENTRY_TRIGGER_FAMILY = True
SCALPING_UNIFIED_REQUIRE_DIRECTIONAL_CONTEXT_FAMILY = True
SCALPING_UNIFIED_DIRECTIONAL_CONTEXT_FAMILIES = (
    "multi_timeframe",
    "market_structure",
    "market_regime",
    "location",
)
SCALPING_UNIFIED_USE_CLOSED_CANDLES_FOR_CONTEXT = True
SCALPING_UNIFIED_USE_LIVE_M1_FOR_TRIGGER = True
SCALPING_UNIFIED_ASIAN_MIN_SCORE = 82.0
SCALPING_UNIFIED_ASIAN_MAX_SPREAD_USD = 0.25
SCALPING_UNIFIED_REQUIRE_RESOLVED_REGIME = True

# Trend-reclaim entry calibration. The mandatory trigger gate remains enabled, but a
# verified trend pullback/reclaim can now qualify as a concrete trigger. This
# addresses the previous situation where strong MTF/structure/regime context
# could never enter unless a fresh breakout or zone rejection appeared.
SCALPING_UNIFIED_TREND_RECLAIM_ENABLED = True
SCALPING_UNIFIED_TREND_RECLAIM_TRIGGER_POINTS = 20.0
SCALPING_UNIFIED_STANDARD_TRIGGER_POINTS = 16.0
SCALPING_UNIFIED_TREND_RECLAIM_MAX_FAST_EMA_DISTANCE_ATR = 0.40
SCALPING_UNIFIED_TREND_RECLAIM_MAX_VWAP_DISTANCE_ATR = 1.75
SCALPING_UNIFIED_TREND_RECLAIM_MIN_BODY_RATIO = 0.30
SCALPING_UNIFIED_TREND_RECLAIM_MIN_RELATIVE_VOLUME = 0.65
SCALPING_UNIFIED_TREND_RECLAIM_MIN_ADX = 18.0
SCALPING_UNIFIED_TREND_RECLAIM_BUY_RSI_MIN = 42.0
SCALPING_UNIFIED_TREND_RECLAIM_BUY_RSI_MAX = 68.0
SCALPING_UNIFIED_TREND_RECLAIM_SELL_RSI_MIN = 32.0
SCALPING_UNIFIED_TREND_RECLAIM_SELL_RSI_MAX = 58.0

# Entry-readiness diagnostic threshold. TREND_RECLAIM uses the tighter 1.75 ATR
# hard limit above; legacy breakout/pullback entries retain their established
# fast-EMA anti-chase rules.
SCALPING_UNIFIED_MAX_ENTRY_VWAP_DISTANCE_ATR = 2.50
SCALPING_UNIFIED_SUPPORT_RESISTANCE_ENABLED = True
SCALPING_UNIFIED_ORDER_BLOCKS_ENABLED = True
SCALPING_UNIFIED_MARKET_STRUCTURE_ENABLED = True
SCALPING_UNIFIED_ATOME_FACTORS_ENABLED = True
SCALPING_UNIFIED_FACTOR_MIN_SCORE = 70.0
SCALPING_UNIFIED_FACTOR_MIN_FACTORS = 2
SCALPING_UNIFIED_FACTOR_ATR_LOOKBACK = 50
SCALPING_UNIFIED_NEWS_CONTEXT_ENABLED = True
SCALPING_UNIFIED_PROVIDER_CACHE_FILE = "data/unified_provider_cache.json"

# V3.4 verified context. These features use only real MT5 candles/quotes.
# There are no synthetic prices, static market defaults, or automatic ML trades.
SCALPING_VERIFIED_MARKET_CONTEXT_ENABLED = True
SCALPING_VERIFIED_MARKET_CONTEXT_REQUIRED = True
SCALPING_VERIFIED_MIN_DATA_QUALITY_SCORE = 0.75
SCALPING_VERIFIED_VOLUME_LOOKBACK = 20
SCALPING_VERIFIED_DELTA_PROXY_LOOKBACK = 10
SCALPING_VERIFIED_VWAP_LOOKBACK = 120

# Cached MT5 cross-market USD-pressure confirmation. It is activated only when
# enough broker forex symbols are available; otherwise its contribution is neutral.
SCALPING_CROSS_MARKET_CONTEXT_ENABLED = True
SCALPING_CROSS_MARKET_REFRESH_SECONDS = 60.0
SCALPING_CROSS_MARKET_M5_LOOKBACK = 3
SCALPING_CROSS_MARKET_MIN_SYMBOLS = 3
SCALPING_CROSS_MARKET_RETURN_SCALE = 0.001
SCALPING_CROSS_MARKET_BIAS_THRESHOLD = 0.25

# Real-paper-trade feature export for later walk-forward ML research. The model
# is not enabled and synthetic training data is prohibited.
SCALPING_FEATURE_DATASET_FILENAME = "scalping_verified_feature_dataset.csv"
SCALPING_MIN_REAL_TRADES_BEFORE_ML_RESEARCH = 200

# Unified diagnostics and data-quality controls.  The factor engine now uses this
# unified flag directly instead of the obsolete shadow-intelligence switch.
SCALPING_UNIFIED_DIAGNOSTICS_ENABLED = True
SCALPING_UNIFIED_REQUIRE_FACTOR_ENGINE = True
SCALPING_UNIFIED_MAX_M1_DATA_AGE_SECONDS = 180
SCALPING_UNIFIED_COMPONENT_MIN_POINTS = 1.0
SCALPING_UNIFIED_SCORE_COMPONENT_VERSION = "V5.0.5"

# Candle-cache policy. Full candle histories refresh at actual timeframe
# boundaries instead of short polling timers. Between M1 refreshes, the live M1
# candle is patched from the current MT5 tick for fast entry timing.
SCALPING_PATCH_LIVE_M1_FROM_TICK = True
SCALPING_CANDLE_BOUNDARY_GRACE_SECONDS = 1.5
SCALPING_CANDLE_MISSING_BAR_RETRY_SECONDS = 5.0
SCALPING_M1_FULL_RESYNC_SECONDS = 120.0
SCALPING_M5_FULL_RESYNC_SECONDS = 600.0
SCALPING_M15_FULL_RESYNC_SECONDS = 1800.0
SCALPING_H1_FULL_RESYNC_SECONDS = 7200.0
SCALPING_H4_FULL_RESYNC_SECONDS = 28800.0
SCALPING_CACHE_HIT_RUNTIME_TARGET_MS = 200.0

# Phase timing diagnostics identify whether an occasional slow cycle came
# from MT5 snapshot retrieval, news processing, signal analysis, risk checks,
# or paper-position management. These values never alter trade decisions.
SCALPING_TIMING_DIAGNOSTICS_ENABLED = True
SCALPING_SLOW_PHASE_WARNING_MS = 200.0

# ======================================================================
# V5.0 TICK MICROSTRUCTURE AND INTERMARKET AUDIT
# ======================================================================

# The MT5 tick recorder backfills all ticks since its previous cursor on every
# cycle. Rows are buffered and written as partitioned Parquet files. The
# paper runner remains operational if a storage write fails, but the error is
# surfaced in cycle diagnostics and the system audit.
SCALPING_TICK_RECORDER_ENABLED = True
SCALPING_TICK_DATA_ROOT = "data/microstructure/ticks"
SCALPING_TICK_CURSOR_ROOT = "data/microstructure/state"
SCALPING_TICK_PARQUET_COMPRESSION = "zstd"
SCALPING_TICK_BUFFER_MAX_ROWS = 1000
SCALPING_TICK_FLUSH_INTERVAL_SECONDS = 5.0
SCALPING_TICK_INITIAL_LOOKBACK_SECONDS = 5.0
# The persisted restart cursor intentionally overlaps recent ticks. This avoids
# permanent data loss if Windows or Python stops before the in-memory Parquet
# buffer flushes. DuckDB exposes a deduplicated view for analysis.
SCALPING_TICK_CURSOR_OVERLAP_SECONDS = 10.0
SCALPING_TICK_MAX_BATCH = 10000
SCALPING_TICK_RECENT_MEMORY_SECONDS = 20.0
# A persisted cursor may be hours behind after a terminal restart. Demo execution
# must never replay that historical backlog as if it were live microstructure.
SCALPING_TICK_MAX_CURSOR_LAG_SECONDS = 30.0
SCALPING_TICK_FUTURE_TOLERANCE_SECONDS = 2.0
SCALPING_MAX_QUOTE_STALE_SECONDS = 3.0

# Rolling features are calculated from broker ticks, never synthetic candles.
# A feature row is stored once per bot cycle for later DuckDB analysis.
SCALPING_MICROSTRUCTURE_ENABLED = True
SCALPING_MICROSTRUCTURE_WINDOWS_SECONDS = (1.0, 3.0, 5.0)
SCALPING_MICROSTRUCTURE_MIN_TICKS = 12
SCALPING_MICROSTRUCTURE_MIN_SPAN_SECONDS = 1.0
SCALPING_MICROSTRUCTURE_MIN_DATA_QUALITY = 0.65
SCALPING_MICROSTRUCTURE_DIRECTIONAL_RATIO_THRESHOLD = 0.20
SCALPING_MICROSTRUCTURE_MIN_VELOCITY_ATR_PER_SECOND = 0.003
SCALPING_MICROSTRUCTURE_MAX_STALL_RATIO = 0.85
SCALPING_MICROSTRUCTURE_FEATURE_ROOT = "data/microstructure/features"
SCALPING_MICROSTRUCTURE_FEATURE_BUFFER_MAX_ROWS = 250
SCALPING_MICROSTRUCTURE_FEATURE_FLUSH_INTERVAL_SECONDS = 10.0

# The meta-controller may either confirm a native V4 playbook or promote a
# pre-existing V4 score winner into the dedicated TICK_CONFIRMED_CONTINUATION
# path. It never invents direction: promotion requires strong technical context,
# valid adaptive economics and directional MT5 tick pressure in the same side.
SCALPING_META_CONTROLLER_ENABLED = True

# V5.0.5 keeps the explicit five-point score-margin candidate, but prevents a
# score difference from becoming an unconditional market-order instruction.
# Normal-location entries remain available without a full V4 playbook. Chasing
# an extended move requires a real same-direction trigger and tick confirmation.
SCALPING_SCORE_MARGIN_ENTRY_ENABLED = True
SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE = 5.0
SCALPING_SCORE_MARGIN_MIN_WINNER_SCORE = 30.0
SCALPING_SCORE_MARGIN_MIN_CONTEXT_ALIGNMENT = 2
SCALPING_SCORE_MARGIN_MAX_CONTEXT_OPPOSITION = 2
SCALPING_SCORE_MARGIN_MIN_RELATIVE_VOLUME = 0.70
SCALPING_SCORE_MARGIN_MAX_ABS_VWAP_ATR = 4.00
SCALPING_SCORE_MARGIN_EXTENDED_VWAP_ATR = 2.50
SCALPING_SCORE_MARGIN_EXTENDED_REQUIRE_TRIGGER = True
SCALPING_SCORE_MARGIN_EXTENDED_REQUIRE_MICRO_CONFIRMATION = True
SCALPING_SCORE_MARGIN_EXTENDED_MIN_MICRO_CONFIDENCE = 0.45

SCALPING_SCORE_MARGIN_EXTENDED_ALLOW_STRONG_MICRO_OVERRIDE = True
SCALPING_SCORE_MARGIN_EXTENDED_OVERRIDE_MIN_WINNER_SCORE = 50.0
SCALPING_SCORE_MARGIN_EXTENDED_OVERRIDE_MIN_MARGIN = 25.0
SCALPING_SCORE_MARGIN_EXTENDED_OVERRIDE_MIN_MICRO_CONFIDENCE = 0.65
SCALPING_SCORE_MARGIN_REQUIRE_MICRO_DATA = False
# Neutral ticks are permitted in normal locations. A clearly opposite tick
# reading remains a veto; the lower threshold reacts sooner than V5.0.4.
SCALPING_SCORE_MARGIN_STRONG_OPPOSITION_CONFIDENCE = 0.55
SCALPING_META_PROMOTE_TICK_CONFIRMED_CANDIDATE = True
SCALPING_MICROSTRUCTURE_ENTRY_GATE_ENABLED = True
SCALPING_MICROSTRUCTURE_ALLOW_NEUTRAL = False
SCALPING_META_PROMOTION_MIN_SCORE = 48.0
SCALPING_META_PROMOTION_MIN_MARGIN = 20.0
SCALPING_META_PROMOTION_MIN_CONTEXT_SUPPORT = 3
SCALPING_META_PROMOTION_MAX_CONTEXT_OPPOSITION = 1
SCALPING_META_PROMOTION_MIN_ADX = 22.0
SCALPING_META_PROMOTION_MIN_RELATIVE_VOLUME = 0.75
SCALPING_META_PROMOTION_MAX_VWAP_ATR = 3.25
SCALPING_META_PROMOTION_MAX_EMA_ATR = 1.25
SCALPING_META_PROMOTION_MIN_MICRO_CONFIDENCE = 0.45
SCALPING_INTERMARKET_STRONG_OPPOSITION_THRESHOLD = 0.55
SCALPING_META_MIN_CONFIDENCE = 0.50

# Broker symbols are discovered and verified at runtime. Missing symbols remain
# neutral and never block the bot by themselves. Returns, not raw levels, drive
# the optional intermarket context.
SCALPING_DIRECT_INTERMARKET_ENABLED = True
SCALPING_INTERMARKET_REFRESH_SECONDS = 300.0
SCALPING_DXY_SYMBOL_CANDIDATES = ("DXY", "USDX", "USDINDEX")
SCALPING_US10Y_SYMBOL_CANDIDATES = ("US10Y", "UST10Y")
SCALPING_TNOTE_SYMBOL_CANDIDATES = ("TNOTE", "ZN")
SCALPING_VIX_SYMBOL_CANDIDATES = ("VIX",)
SCALPING_INTERMARKET_RETURN_WINDOWS_SECONDS = (1.0, 5.0, 15.0)
SCALPING_INTERMARKET_MIN_RETURN_ABS = 0.00001

# Append-only audit events record decision, request, response, requested quote,
# simulated fill, slippage, MFE, MAE, hold time and close reason.
SCALPING_EXECUTION_AUDIT_ENABLED = True
SCALPING_EXECUTION_AUDIT_CSV_FILENAME = "scalp_execution_audit.csv"
SCALPING_EXECUTION_AUDIT_PARQUET_ROOT = "data/execution_audit"
SCALPING_EXECUTION_AUDIT_PARQUET_COMPRESSION = "zstd"
SCALPING_EXECUTION_AUDIT_BUFFER_MAX_ROWS = 100
SCALPING_EXECUTION_AUDIT_FLUSH_INTERVAL_SECONDS = 5.0

# DuckDB is an analysis layer only. It never participates in the entry loop.
SCALPING_DUCKDB_PATH = "data/microstructure/scalping_research.duckdb"


# ======================================================================
# PROFIT, LOSS, AND TRADE MANAGEMENT
# ======================================================================

SCALPING_MIN_PROFIT_TARGET_USD = 0.30
SCALPING_MAX_PROFIT_TARGET_USD = 0.70
SCALPING_TARGET_SPREAD_MULTIPLIER = 2.25
SCALPING_TARGET_ATR_PROFIT_RATIO = 0.25
SCALPING_BREAKOUT_TARGET_ATR_PROFIT_RATIO = 0.32

SCALPING_MIN_STOP_LOSS_USD = 0.45
SCALPING_MAX_STOP_LOSS_USD = 0.65
SCALPING_STOP_ATR_PROFIT_RATIO = 0.25
SCALPING_STOP_SPREAD_MULTIPLIER = 1.50
SCALPING_MIN_REWARD_RISK_RATIO = 0.65
SCALPING_MAX_SPREAD_TARGET_RATIO = 0.32

SCALPING_MAX_HOLD_SECONDS = 75
SCALPING_CLOSE_ON_OPPOSITE_SIGNAL = True
SCALPING_OPPOSITE_SIGNAL_MIN_SCORE = 78.0
# Direct-score paper positions close immediately when the winning direction flips.
# The legacy 78-point threshold remains only for non-direct modes.
SCALPING_DIRECT_SCORE_CLOSE_ON_ANY_FLIP = True

# There is no routine cooldown after a normal win or loss. A temporary pause
# is applied only after each complete group of three consecutive losses.
SCALPING_LOSS_STREAK_COOLDOWN_AFTER_LOSSES = 3
SCALPING_LOSS_STREAK_COOLDOWN_SECONDS = 180

# Tiered profit protection scaled for the fixed $0.30 target. The stages
# protect favorable movement before the target without changing the requested TP.
SCALPING_BREAKEVEN_TRIGGER_USD = 0.12
SCALPING_TRAILING_GIVEBACK_USD = 0.08
SCALPING_MIN_LOCKED_PROFIT_USD = 0.03
SCALPING_PROFIT_STAGE_2_TRIGGER_USD = 0.20
SCALPING_PROFIT_STAGE_2_LOCK_USD = 0.08
SCALPING_PROFIT_STAGE_3_TRIGGER_USD = 0.26
SCALPING_PROFIT_STAGE_3_LOCK_USD = 0.15

# Paper positions persist explicit target/stop prices that emulate broker-side
# protection. A fixed small slippage allowance keeps stop fills conservative
# without turning a short process interruption into an arbitrary oversized loss.
SCALPING_PAPER_PROTECTIVE_ORDERS_ENABLED = True
SCALPING_PAPER_STOP_SLIPPAGE_USD = 0.05
SCALPING_OFFLINE_GAP_THRESHOLD_SECONDS = 3.0

# Intentional runner shutdowns flatten paper positions at the latest quote so
# no simulated scalp remains unmanaged while the process is offline.
SCALPING_CLOSE_OPEN_POSITIONS_ON_RUNNER_STOP = True


# ======================================================================
# DAILY SCALPING RISK
# ======================================================================

SCALPING_MAX_DAILY_TRADES = 30
SCALPING_DAILY_LOSS_LIMIT_USD = 25.00
SCALPING_MAX_DRAWDOWN_USD = 25.00

# The daily limit is deliberately conservative for the first validation.
# It may later move to 60 and then 100+ only after performance review.


# ======================================================================
# NEWS FILTER
# ======================================================================

SCALPING_USE_CORE_NEWS_FILTER = True
SCALPING_NEWS_BLOCK_BEFORE_MINUTES = core_settings.NEWS_BLOCK_BEFORE_MINUTES
SCALPING_NEWS_BLOCK_AFTER_MINUTES = core_settings.NEWS_BLOCK_AFTER_MINUTES


# ======================================================================
# LOGGING
# ======================================================================

SCALPING_LOG_ROOT = "logs/scalping_v6_3_2_conservative_shadow_fills"
SCALPING_USE_DAILY_LOG_FOLDERS = True
SCALPING_DATE_FORMAT = "%Y-%m-%d"
SCALPING_TRADES_FILENAME = "scalp_paper_trades.json"
SCALPING_CYCLE_LOG_FILENAME = "scalp_cycle_log.csv"
SCALPING_TRADE_HISTORY_FILENAME = "scalp_trade_history.csv"
SCALPING_AUDIT_FILENAME = "scalping_audit_report.txt"


# ======================================================================
# DISPLAY
# ======================================================================

SCALPING_PRINT_EVERY_CYCLE = True
SCALPING_PRINT_WAIT_REASONS = True


# ======================================================================
# VALIDATION, REVIEW, AND STAGED SCALING
# ======================================================================

# Reports never change strategy settings automatically. They only produce
# evidence and recommendations for manual review.
SCALPING_MIN_TRADES_FOR_PARAMETER_REVIEW = 50
SCALPING_MAX_CYCLE_ERROR_RATE_PERCENT = 2.0

SCALPING_BASELINE_MIN_CLOSED_TRADES = 50
SCALPING_BASELINE_MIN_ACTIVE_DAYS = 3
SCALPING_BASELINE_MIN_WIN_RATE = 55.0
SCALPING_BASELINE_MIN_PROFIT_FACTOR = 1.10
SCALPING_BASELINE_MAX_DRAWDOWN_USD = 15.00
SCALPING_BASELINE_MAX_LOSING_STREAK = 4

SCALPING_TWO_POSITION_MIN_TRADES = 100
SCALPING_TWO_POSITION_MIN_DAYS = 5
SCALPING_TWO_POSITION_MIN_WIN_RATE = 55.0
SCALPING_TWO_POSITION_MIN_PROFIT_FACTOR = 1.20
SCALPING_TWO_POSITION_MAX_DRAWDOWN_USD = 15.00
SCALPING_TWO_POSITION_MAX_LOSING_STREAK = 4

SCALPING_THREE_POSITION_MIN_TRADES = 200
SCALPING_THREE_POSITION_MIN_DAYS = 10
SCALPING_THREE_POSITION_MIN_WIN_RATE = 57.0
SCALPING_THREE_POSITION_MIN_PROFIT_FACTOR = 1.25
SCALPING_THREE_POSITION_MAX_DRAWDOWN_USD = 20.00
SCALPING_THREE_POSITION_MAX_LOSING_STREAK = 4

SCALPING_DEMO_MIN_PAPER_TRADES = 150
SCALPING_DEMO_MIN_ACTIVE_DAYS = 7
SCALPING_DEMO_MIN_WIN_RATE = 55.0
SCALPING_DEMO_MIN_PROFIT_FACTOR = 1.20
SCALPING_DEMO_MAX_DRAWDOWN_USD = 100.00
SCALPING_DEMO_MAX_LOSING_STREAK = 10
SCALPING_DEMO_MAX_CYCLE_ERROR_RATE_PERCENT = 1.0


# ======================================================================
# CONTROLLED MT5 DEMO EXECUTION — ENABLED ONLY FOR THE SEPARATE DEMO RUNNER
# ======================================================================

# The paper runner never imports the demo executor. The separate demo runner
# requires every independent gate below and refuses non-demo accounts.
SCALPING_DEMO_EXECUTION_ENABLED = True
SCALPING_DEMO_EXECUTION_CONFIRMATION = ""
SCALPING_REQUIRED_DEMO_CONFIRMATION = "I_ACCEPT_DEMO_SCALPING_RISK"
SCALPING_REQUIRE_PAPER_READINESS_FOR_DEMO = False
SCALPING_REQUIRE_DEMO_ACCOUNT = True
SCALPING_DEMO_MAX_OPEN_POSITIONS = 1
SCALPING_DEMO_MAX_DAILY_TRADES = 0  # Legacy field: 0 means DISABLED
SCALPING_DEMO_DAILY_LOSS_LIMIT_USD = 100.00  # Compatibility alias; not reset at midnight
SCALPING_DEMO_MAX_CONSECUTIVE_LOSSES = 3

# V5.1.1 cumulative loss-session controls. There is no daily trade-count limit
# and no midnight reset. The same loss session persists across dates and process
# restarts until an explicit --reset-loss-session launch is performed.
SCALPING_DEMO_TRADE_LIMIT_ENABLED = False
SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD = 100.00
SCALPING_DEMO_PEAK_DRAWDOWN_STOP_ENABLED = False
SCALPING_DEMO_LOSS_SESSION_STATE_PATH = "data/runtime/demo_loss_session.json"
SCALPING_DEMO_REQUIRE_EXPLICIT_LOSS_SESSION_RESET = True
SCALPING_DEMO_ORDER_DEVIATION_POINTS = 10
SCALPING_DEMO_COMMENT = "XAU_V600_APPROVED_DEMO"
SCALPING_DEMO_LOG_FILENAME = "scalp_demo_execution_log.csv"
SCALPING_DEMO_HISTORY_FILENAME = "scalp_demo_history.json"

# Controlled pilot safeguards. The confirmation is never persisted in settings;
# run_scalping_demo_loop.py receives it at launch and arms only the current process.
SCALPING_DEMO_PILOT_MODE = True
SCALPING_DEMO_MAX_LOT_SIZE = 0.01
SCALPING_DEMO_MAX_DRAWDOWN_USD = 100.00
SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES = 3
SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS = 300

# Loss-recovery mode activates before the tenth-loss cooldown. It does not stop
# trading permanently; it temporarily requires a higher-quality confirmation
# after a losing streak so the bot does not repeat the same weak setup. A win
# or break-even trade automatically clears the trailing-loss streak.
SCALPING_DEMO_RECOVERY_MODE_AFTER_LOSSES = 0
SCALPING_DEMO_RECOVERY_REQUIRE_NORMAL_SPREAD = True
SCALPING_DEMO_RECOVERY_MIN_WINNER_SCORE = 50.0
SCALPING_DEMO_RECOVERY_MIN_SCORE_MARGIN = 25.0
SCALPING_DEMO_RECOVERY_MIN_MICRO_CONFIDENCE = 0.60
SCALPING_DEMO_RECOVERY_MIN_REWARD_RISK_RATIO = 1.05

# Demo exit quality. A one-cycle score flip is no longer enough to close a
# position at a loss. Opposite exits require a meaningful score lead and
# same-direction tick confirmation after a short minimum hold.
SCALPING_DEMO_MIN_HOLD_BEFORE_OPPOSITE_EXIT_SECONDS = 5
SCALPING_DEMO_OPPOSITE_EXIT_MIN_SCORE = 45.0
SCALPING_DEMO_OPPOSITE_EXIT_MIN_MARGIN = 15.0
SCALPING_DEMO_OPPOSITE_EXIT_MIN_MICRO_CONFIDENCE = 0.55

# Protect winning demo positions from turning into losses. The broker TP/SL
# stays active; these stages only add an early close after meaningful favorable
# movement has already occurred.
SCALPING_DEMO_PROFIT_PROTECTION_ENABLED = True
SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_USD = 0.20
SCALPING_DEMO_PROFIT_STAGE_1_FLOOR_USD = 0.05
SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_USD = 0.35
SCALPING_DEMO_PROFIT_STAGE_2_FLOOR_USD = 0.15

SCALPING_DEMO_MAX_SESSION_MINUTES = 120
SCALPING_DEMO_CLOSE_POSITIONS_ON_RUNNER_STOP = True
SCALPING_DEMO_REQUIRE_ZERO_EXTERNAL_SYMBOL_POSITIONS = True
SCALPING_DEMO_ACCOUNT_IDENTITY_LOCK = True
SCALPING_DEMO_RUNTIME_CONFIRMATION_REQUIRED = True
SCALPING_DEMO_AUDIT_CSV_FILENAME = "scalp_demo_execution_audit.csv"

# V5.2.0 demo-only economics. Paper compatibility values above remain unchanged,
# while the controlled demo uses wider cost-aware targets and stops. The engine
# measures the market excursion required after crossing the spread, so a small
# nominal stop cannot sit inside ordinary quote noise.
SCALPING_DEMO_MIN_PROFIT_TARGET_USD = 0.85
SCALPING_DEMO_MAX_PROFIT_TARGET_USD = 0.85
SCALPING_DEMO_TARGET_SPREAD_MULTIPLIER = 3.00
SCALPING_DEMO_TARGET_ATR_PROFIT_RATIO = 0.32
SCALPING_DEMO_BREAKOUT_TARGET_ATR_PROFIT_RATIO = 0.45
SCALPING_DEMO_MIN_STOP_LOSS_USD = 1.20
SCALPING_DEMO_MAX_STOP_LOSS_USD = 1.30
SCALPING_DEMO_STOP_MIN_ADVERSE_BUFFER_USD = 0.20
SCALPING_DEMO_STOP_ADVERSE_ATR_RATIO = 0.18
SCALPING_DEMO_MIN_REWARD_RISK_RATIO = 0.65
SCALPING_DEMO_MAX_SPREAD_TARGET_RATIO = 0.32
SCALPING_DEMO_MAX_BARRIER_ASYMMETRY = 2.50
SCALPING_DEMO_MAX_HOLD_SECONDS = 60

# Entry persistence/hysteresis. Ordinary entries must remain valid across
# multiple scans. Only exceptionally strong, tick-confirmed signals may enter
# immediately. This prevents one-cycle score flips from creating churn.
SCALPING_DEMO_SIGNAL_PERSISTENCE_ENABLED = True
SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_CYCLES = 5
SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_SECONDS = 1.25
SCALPING_DEMO_SIGNAL_PERSISTENCE_MAX_GAP_SECONDS = 2.00
SCALPING_DEMO_INSTANT_ENTRY_MIN_SCORE = 65.0
SCALPING_DEMO_INSTANT_ENTRY_MIN_MARGIN = 35.0
SCALPING_DEMO_INSTANT_ENTRY_MIN_MICRO_CONFIDENCE = 0.65

# Central evidence-quality policy. It combines score strength, margin, tape,
# context, execution economics and persistence into a transparent quality index.
SCALPING_DEMO_ENTRY_QUALITY_ENABLED = True
SCALPING_DEMO_ENTRY_MIN_WINNER_SCORE = 38.0
SCALPING_DEMO_ENTRY_MIN_SCORE_MARGIN = 12.0
SCALPING_DEMO_ENTRY_MIN_QUALITY_INDEX = 0.64
SCALPING_DEMO_ELEVATED_SPREAD_MIN_QUALITY_INDEX = 0.72
SCALPING_DEMO_RECOVERY_MIN_QUALITY_INDEX = 0.78
SCALPING_DEMO_STRONG_OPPOSITE_MICRO_CONFIDENCE = 0.55

# A second position is a controlled pyramid, never an automatic duplicate. The
# first position must already be profitable and the new signal must be stronger.
SCALPING_DEMO_PYRAMID_ENABLED = False
SCALPING_DEMO_PYRAMID_MIN_FIRST_POSITION_PROFIT_USD = 0.10
SCALPING_DEMO_PYRAMID_MIN_FIRST_POSITION_AGE_SECONDS = 5
SCALPING_DEMO_PYRAMID_MIN_WINNER_SCORE = 55.0
SCALPING_DEMO_PYRAMID_MIN_SCORE_MARGIN = 30.0
SCALPING_DEMO_PYRAMID_MIN_MICRO_CONFIDENCE = 0.60
SCALPING_DEMO_PYRAMID_MIN_QUALITY_INDEX = 0.80
SCALPING_DEMO_PYRAMID_REQUIRE_NORMAL_SPREAD = True

# Execution-time revalidation. A signal may be valid at decision time but stale
# or adversely repriced by the time the request reaches MT5.
SCALPING_DEMO_MAX_DECISION_AGE_SECONDS = 1.50
SCALPING_DEMO_MAX_ADVERSE_PRICE_MOVE_USD = 0.12
SCALPING_DEMO_MAX_ADVERSE_MOVE_ATR_RATIO = 0.08
SCALPING_DEMO_MAX_ENTRY_SLIPPAGE_USD = 0.08

# Profit protection scales with the actual target instead of fixed dollar
# thresholds. This preserves larger winners while still preventing full giveback.
SCALPING_DEMO_DYNAMIC_PROFIT_PROTECTION_ENABLED = True
SCALPING_DEMO_PROFIT_PROTECTION_MIN_HOLD_SECONDS = 3
SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_RATIO = 0.35
SCALPING_DEMO_PROFIT_STAGE_1_FLOOR_RATIO = 0.10
SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_RATIO = 0.60
SCALPING_DEMO_PROFIT_STAGE_2_FLOOR_RATIO = 0.30
SCALPING_DEMO_PROFIT_STAGE_3_TRIGGER_RATIO = 0.80
SCALPING_DEMO_PROFIT_STAGE_3_FLOOR_RATIO = 0.55
SCALPING_DEMO_MAX_HOLD_EXTENSION_SECONDS = 0

# Empirical edge memory is deliberately conservative. It only vetoes a setup
# bucket after enough comparable closed demo trades show negative expectancy.
SCALPING_DEMO_EDGE_MEMORY_ENABLED = True
SCALPING_DEMO_EDGE_MEMORY_MIN_BUCKET_TRADES = 20
SCALPING_DEMO_EDGE_MEMORY_PRIOR_WINS = 2.0
SCALPING_DEMO_EDGE_MEMORY_PRIOR_LOSSES = 2.0
SCALPING_DEMO_EDGE_MEMORY_MAX_NEGATIVE_EXPECTANCY_USD = -0.03
SCALPING_DEMO_EDGE_MEMORY_MAX_BAD_PROFIT_FACTOR = 0.85
SCALPING_DEMO_EDGE_MEMORY_PROBATION_MIN_TRADES = 5
SCALPING_DEMO_EDGE_MEMORY_PROBATION_EXPECTANCY_SCALE_USD = 0.10
SCALPING_DEMO_EDGE_MEMORY_PROBATION_MAX_QUALITY_PENALTY = 0.10

# Real-account execution is intentionally not implemented. The platform only
# produces a review report after a separate demo history has been collected.
SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED = False

# Automated regression tests can temporarily restore the previous paper-mode
# defaults without changing the distributed demo-pilot configuration. This is
# read only at process startup and is never used by the demo runner.
if os.getenv("SCALPING_TEST_FORCE_PAPER_MODE", "").strip() == "1":
    SCALPING_PAPER_ONLY = True
    SCALPING_DEMO_EXECUTION_ENABLED = False

# ======================================================================
# REAL-ACCOUNT REVIEW EVIDENCE — REVIEW ONLY, NO EXECUTION
# ======================================================================

SCALPING_REAL_REVIEW_MIN_CLOSED_DEMO_TRADES = 100
SCALPING_REAL_REVIEW_MIN_ACTIVE_DAYS = 10
SCALPING_REAL_REVIEW_MIN_WIN_RATE = 55.0
SCALPING_REAL_REVIEW_MIN_PROFIT_FACTOR = 1.20
SCALPING_REAL_REVIEW_MAX_DRAWDOWN_USD = 20.00

# Aggregate exposure limits used when the staged paper position count later
# increases to two or three.
SCALPING_MAX_SAME_DIRECTION_POSITIONS = 1
SCALPING_MAX_TOTAL_OPEN_RISK_USD = 9.00


# ======================================================================
# V6 RESEARCH-CALIBRATED SHADOW / PROMOTION GATE
# ======================================================================

# Default operation is shadow-only on the connected MT5 demo feed. No broker
# order can be sent until an approval artifact has been produced by the
# chronological walk-forward validator for the exact settings hash.
SCALPING_V6_SHADOW_MODE_DEFAULT = True
SCALPING_V6_DEMO_APPROVAL_REQUIRED = True
SCALPING_V6_DEMO_APPROVAL_PATH = "data/runtime/v6_demo_approval.json"
SCALPING_V6_SHADOW_STATE_PATH = "data/runtime/v6_shadow_state.json"
SCALPING_V6_SHADOW_HISTORY_PATH = "data/research/v6_shadow_history.jsonl"
SCALPING_V6_SHADOW_CANDIDATES_PATH = "data/research/v6_shadow_candidates.jsonl"
# V6.2 research-only multi-lane calibration. STRICT remains the only lane
# eligible for controlled-demo approval. BALANCED and EXPLORATORY never send
# broker orders; they exist to collect counterfactual evidence faster.
SCALPING_V6_SHADOW_LANES_ENABLED = True
SCALPING_V6_SHADOW_LANE_STATE_PATH = "data/runtime/v6_shadow_lane_state.json"
SCALPING_V6_SHADOW_LANE_HISTORY_FOLDER = "data/research/v6_shadow_lanes"
SCALPING_V6_SHADOW_LANE_CANDIDATES_FOLDER = "data/research/v6_shadow_lane_candidates"
SCALPING_V6_STRICT_LANE_NAME = "STRICT"
SCALPING_V6_BALANCED_LANE_NAME = "BALANCED"
SCALPING_V6_EXPLORATORY_LANE_NAME = "EXPLORATORY"
SCALPING_V6_FAST_LANE_NAME = "FAST"
SCALPING_V6_FAST_MAX_SPREAD_USD = 0.20
SCALPING_V6_FAST_MAX_SPREAD_ATR_RATIO = 0.15
SCALPING_V6_FAST_MIN_WINNER_SCORE = 42.0
SCALPING_V6_FAST_MIN_SCORE_MARGIN = 18.0
SCALPING_V6_FAST_MIN_MICRO_CONFIDENCE = 0.55
SCALPING_V6_FAST_MIN_MICRO_DATA_QUALITY = 0.75
SCALPING_V6_FAST_MIN_QUOTE_FLOW_IMBALANCE = 0.10
SCALPING_V6_FAST_MAX_HOLD_SECONDS = 15.0

# Research-only candle-colour benchmark. This intentionally simple model is
# isolated from V6.3.3 so its results cannot train or authorize the main bot.
SCALPING_CANDLE_FOLLOW_ENABLED = True
SCALPING_CANDLE_FOLLOW_STRATEGY_ID = "XAUUSD_LIVE_CANDLE_FADE_5S_V3"
SCALPING_CANDLE_FOLLOW_STATE_PATH = "data/runtime/candle_follow_state.json"
SCALPING_CANDLE_FOLLOW_HISTORY_PATH = "data/research/candle_follow_history.jsonl"
SCALPING_CANDLE_FOLLOW_TARGET_USD = 0.40
SCALPING_CANDLE_FOLLOW_STOP_USD = 1.00
SCALPING_CANDLE_FOLLOW_MAX_HOLD_SECONDS = 5.0
SCALPING_CANDLE_FOLLOW_LOOP_SECONDS = 0.25
SCALPING_CANDLE_FOLLOW_MAX_QUOTE_AGE_SECONDS = 3.0
SCALPING_CANDLE_FOLLOW_MAX_CLOSED_CANDLE_AGE_SECONDS = 120.0

# V6.2.1 episode integrity. A closed shadow trade may never reopen in the
# same cycle. Every exit must be followed by a fresh candidate episode. A hard
# stop additionally locks the same structural direction until the higher-level
# consensus resets, preventing repeated entries into one invalidated thesis.
SCALPING_V6_EPISODE_REARM_ENABLED = True
# A failed thesis is not a new opportunity merely because one noisy tick makes
# a gate invalid for a cycle. After a no-progress or adverse tape exit, the
# candidate direction must actually change before that lane may enter again.
# This is a market-state reset, not a time cooldown.
SCALPING_V6_FAILED_THESIS_DIRECTION_RESET_REQUIRED = True
SCALPING_V6_HARD_STOP_STRUCTURE_RESET_REQUIRED = True

# Balanced research lane: still requires matching 2/3 structure and positive
# tape, but uses empirically broader thresholds to create a usable sample.
SCALPING_V6_BALANCED_MIN_WINNER_SCORE = 38.0
SCALPING_V6_BALANCED_MIN_SCORE_MARGIN = 18.0
SCALPING_V6_BALANCED_MAX_SPREAD_USD = 0.27
SCALPING_V6_BALANCED_MAX_SPREAD_ATR_RATIO = 0.18
SCALPING_V6_BALANCED_MAX_ABS_VWAP_ATR = 1.50
SCALPING_V6_BALANCED_MIN_RELATIVE_VOLUME = 0.60
SCALPING_V6_BALANCED_MAX_RELATIVE_VOLUME = 1.80
SCALPING_V6_BALANCED_MIN_MICRO_CONFIDENCE = 0.50
SCALPING_V6_BALANCED_MIN_DIRECTIONAL_WINDOWS = 1
SCALPING_V6_BALANCED_MIN_PERSISTENCE_CYCLES = 3
SCALPING_V6_BALANCED_MIN_PERSISTENCE_SECONDS = 0.75
SCALPING_V6_BALANCED_REQUIRE_LOCATION_ROOM = True

# Exploratory lane: shadow-only. It rejects opposite structural consensus and
# hard execution/news problems, while allowing weaker evidence for research.
SCALPING_V6_EXPLORATORY_MIN_WINNER_SCORE = 30.0
SCALPING_V6_EXPLORATORY_MIN_SCORE_MARGIN = 10.0
SCALPING_V6_EXPLORATORY_MAX_SPREAD_USD = 0.30
SCALPING_V6_EXPLORATORY_MAX_SPREAD_ATR_RATIO = 0.22
SCALPING_V6_EXPLORATORY_MAX_ABS_VWAP_ATR = 2.00
SCALPING_V6_EXPLORATORY_MIN_RELATIVE_VOLUME = 0.50
SCALPING_V6_EXPLORATORY_MAX_RELATIVE_VOLUME = 2.00
SCALPING_V6_EXPLORATORY_MIN_MICRO_CONFIDENCE = 0.45
SCALPING_V6_EXPLORATORY_MIN_DIRECTIONAL_WINDOWS = 0
SCALPING_V6_EXPLORATORY_MIN_PERSISTENCE_CYCLES = 2
SCALPING_V6_EXPLORATORY_MIN_PERSISTENCE_SECONDS = 0.40
SCALPING_V6_EXPLORATORY_MIN_STRUCTURE_VOTES = 1
SCALPING_V6_EXPLORATORY_REQUIRE_LOCATION_ROOM = False

# Feed-stall handling. A stale terminal quote pauses expensive analysis and
# chart rendering until a genuinely new MT5 quote arrives.
SCALPING_V6_FEED_PAUSE_QUOTE_AGE_SECONDS = 3.0
SCALPING_V6_FEED_PAUSE_SLEEP_SECONDS = 2.0
SCALPING_V6_FEED_PAUSE_LOG_INTERVAL_SECONDS = 30.0
SCALPING_V6_MARKET_MAP_FORCE_MIN_SCORE = 38.0
SCALPING_V6_GATE_TELEMETRY_PATH = "data/research/v6_gate_telemetry.jsonl"
SCALPING_V6_GATE_TELEMETRY_INTERVAL_SECONDS = 5.0
SCALPING_V6_SETTINGS_HASH_FIELDS = (
    "SCALPING_V6_MAX_SPREAD_USD",
    "SCALPING_V6_MAX_ABS_VWAP_ATR",
    "SCALPING_V6_MIN_WINNER_SCORE",
    "SCALPING_V6_MIN_SCORE_MARGIN",
    "SCALPING_V6_MIN_ALIGNED_MICRO_CONFIDENCE",
    "SCALPING_V6_MIN_PERSISTENCE_CYCLES",
    "SCALPING_V6_MIN_PERSISTENCE_SECONDS",
    "SCALPING_V6_MAX_QUOTE_AGE_SECONDS",
    "SCALPING_V6_MAX_SPREAD_ATR_RATIO",
    "SCALPING_V6_MIN_RELATIVE_VOLUME",
    "SCALPING_V6_MAX_RELATIVE_VOLUME",
    "SCALPING_V6_REQUIRE_TICK_DIRECTION_CONSISTENCY",
    "SCALPING_V6_MIN_DIRECTIONAL_WINDOWS",
    "SCALPING_V6_CANDIDATE_DEDUP_SECONDS",
    "SCALPING_V6_CANDIDATE_PRICE_BUCKET_USD",
    "SCALPING_V6_EPISODE_REARM_ENABLED",
    "SCALPING_V6_HARD_STOP_STRUCTURE_RESET_REQUIRED",
    "SCALPING_V6_STRUCTURE_CONSENSUS_ENABLED",
    "SCALPING_V6_STRUCTURE_MIN_VOTES",
    "SCALPING_V6_LEVEL_CLUSTER_ATR",
    "SCALPING_V6_REQUIRE_STRUCTURE_LOCATION_ROOM",
    "SCALPING_V6_TARGET_USD",
    "SCALPING_V6_HARD_STOP_USD",
    "SCALPING_V6_MAX_HOLD_SECONDS",
    "SCALPING_V6_NO_PROGRESS_CHECK_SECONDS",
    "SCALPING_V6_NO_PROGRESS_MAX_MFE_USD",
    "SCALPING_V6_NO_PROGRESS_EXIT_PNL_USD",
    "SCALPING_V6_BREAKEVEN_TRIGGER_USD",
    "SCALPING_V6_BREAKEVEN_FLOOR_USD",
    "SCALPING_V6_STRONG_OPPOSITE_EXIT_CONFIDENCE",
    "SCALPING_V6_MIN_HOLD_BEFORE_THESIS_EXIT_SECONDS",
    "SCALPING_V6_MAX_OPEN_POSITIONS",
    "SCALPING_V6_PYRAMID_ENABLED",
    "SCALPING_V6_PROMOTION_MIN_CLOSED_SHADOW_TRADES",
    "SCALPING_V6_PROMOTION_MIN_ACTIVE_DAYS",
    "SCALPING_V6_PROMOTION_MIN_WALK_FORWARD_FOLDS",
    "SCALPING_V6_PROMOTION_MIN_PROFIT_FACTOR",
    "SCALPING_V6_PROMOTION_MIN_EXPECTANCY_USD",
    "SCALPING_V6_PROMOTION_MIN_RECENT_PROFIT_FACTOR",
    "SCALPING_V6_PROMOTION_RECENT_TRADES",
    "SCALPING_V6_PROMOTION_MAX_DRAWDOWN_USD",
    "SCALPING_V6_PROMOTION_MAX_NEGATIVE_FOLDS",
    "SCALPING_V6_PROMOTION_APPROVAL_VALID_DAYS",
    "SCALPING_V6_PROMOTION_MIN_BOOTSTRAP_EXPECTANCY_P05",
    "SCALPING_V6_DEMO_MAX_CONSECUTIVE_LOSSES",
    "SCALPING_V6_DEMO_LOSS_COOLDOWN_SECONDS",
    "SCALPING_V6_DEMO_RETURN_TO_SHADOW_AFTER_LOSSES",
)

# Data-backed first deployment filter. The 59-trade forensic sample showed
# positive performance only in the lowest spread band and near VWAP. These are
# hypotheses to validate in shadow mode, not claims of future profitability.
SCALPING_V6_MAX_SPREAD_USD = 0.27
SCALPING_V6_MAX_ABS_VWAP_ATR = 1.00
SCALPING_V6_MIN_WINNER_SCORE = 45.0
SCALPING_V6_MIN_SCORE_MARGIN = 20.0
SCALPING_V6_MIN_ALIGNED_MICRO_CONFIDENCE = 0.55
SCALPING_V6_MIN_PERSISTENCE_CYCLES = 5
SCALPING_V6_MIN_PERSISTENCE_SECONDS = 1.25
SCALPING_V6_MAX_QUOTE_AGE_SECONDS = 2.0
SCALPING_V6_MAX_SPREAD_ATR_RATIO = 0.15
SCALPING_V6_MIN_RELATIVE_VOLUME = 0.75
SCALPING_V6_MAX_RELATIVE_VOLUME = 1.50
SCALPING_V6_REQUIRE_CLOSED_CANDLE_TRIGGER = False
SCALPING_V6_REQUIRE_TICK_DIRECTION_CONSISTENCY = True
SCALPING_V6_MIN_DIRECTIONAL_WINDOWS = 2
SCALPING_V6_MIN_MICRO_DATA_QUALITY = 0.70
SCALPING_V6_MIN_ALIGNED_QUOTE_FLOW_IMBALANCE = 0.10
SCALPING_V6_MAX_SPREAD_EXPANSION_ATR = 0.04
SCALPING_V6_BLOCKED_MICRO_REGIMES = ("STALLED", "DISLOCATED")
SCALPING_V6_STRICT_BLOCKED_CONTEXT_REGIMES = ("NO_TRADE",)
SCALPING_V6_STRICT_REQUIRE_CONTEXT_DIRECTION_ALIGNMENT = True
SCALPING_V6_CANDIDATE_DEDUP_SECONDS = 20
SCALPING_V6_CANDIDATE_PRICE_BUCKET_USD = 0.20


# Objective chart/market-structure consensus. Three independent families are
# evaluated from closed M15/H1/H4 candles: HTF trend, clustered support/
# resistance with break/sweep logic, and displacement-confirmed order blocks.
# At least two families must agree with the scalp direction.
SCALPING_V6_STRUCTURE_CONSENSUS_ENABLED = True
SCALPING_V6_STRUCTURE_MIN_VOTES = 2
SCALPING_V6_LEVEL_CLUSTER_ATR = 0.22
SCALPING_V6_REQUIRE_STRUCTURE_LOCATION_ROOM = True
SCALPING_V6_CHART_EXPORT_ENABLED = True
SCALPING_V6_CHART_EXPORT_INTERVAL_SECONDS = 300
SCALPING_V6_CHART_EXPORT_FOLDER = "logs/v6_market_maps"

# Triple-barrier shadow labels and approved-demo protective levels. The broker
# stop is a catastrophe barrier; software thesis exits may close earlier.
SCALPING_V6_TARGET_USD = 0.85
SCALPING_V6_HARD_STOP_USD = 1.25
SCALPING_V6_MAX_HOLD_SECONDS = 60
SCALPING_V6_NO_PROGRESS_CHECK_SECONDS = 12
SCALPING_V6_NO_PROGRESS_MAX_MFE_USD = 0.08
SCALPING_V6_NO_PROGRESS_EXIT_PNL_USD = -0.30
SCALPING_V6_BREAKEVEN_TRIGGER_USD = 0.25
SCALPING_V6_BREAKEVEN_FLOOR_USD = 0.00
SCALPING_V6_STRONG_OPPOSITE_EXIT_CONFIDENCE = 0.65
SCALPING_V6_MIN_HOLD_BEFORE_THESIS_EXIT_SECONDS = 4

# One position only until the approved demo phase itself proves an edge.
SCALPING_V6_MAX_OPEN_POSITIONS = 1
SCALPING_V6_PYRAMID_ENABLED = False

# Promotion thresholds. Approval is based on chronological out-of-sample folds
# and automatically expires so stale market regimes cannot remain authorized.
SCALPING_V6_PROMOTION_MIN_CLOSED_SHADOW_TRADES = 200
SCALPING_V6_PROMOTION_MIN_ACTIVE_DAYS = 3
SCALPING_V6_PROMOTION_MIN_WALK_FORWARD_FOLDS = 4
SCALPING_V6_PROMOTION_MIN_PROFIT_FACTOR = 1.15
SCALPING_V6_PROMOTION_MIN_EXPECTANCY_USD = 0.03
SCALPING_V6_PROMOTION_MIN_RECENT_PROFIT_FACTOR = 1.00
SCALPING_V6_PROMOTION_RECENT_TRADES = 50
SCALPING_V6_PROMOTION_MAX_DRAWDOWN_USD = 15.00
SCALPING_V6_PROMOTION_MAX_NEGATIVE_FOLDS = 1
SCALPING_V6_PROMOTION_APPROVAL_VALID_DAYS = 7
SCALPING_V6_PROMOTION_BOOTSTRAP_SAMPLES = 2000
SCALPING_V6_PROMOTION_MIN_BOOTSTRAP_EXPECTANCY_P05 = -0.02

# Approved-demo circuit breaker. A short time pause is not enough after repeated
# losses; the bot returns to shadow-only observation until a fresh high-quality
# candidate appears.
SCALPING_V6_DEMO_MAX_CONSECUTIVE_LOSSES = 3
SCALPING_V6_DEMO_LOSS_COOLDOWN_SECONDS = 300
SCALPING_V6_DEMO_RETURN_TO_SHADOW_AFTER_LOSSES = True

# Optional free macro providers are contextual only. MT5 remains the sole
# authoritative source for executable XAUUSD prices and spreads.
SCALPING_V6_FREE_MACRO_CONTEXT_ENABLED = True
SCALPING_V6_FREE_MACRO_FAIL_OPEN = True


# ======================================================================
# V6.3 CALIBRATED SELF-LEARNING META-LAYER (SHADOW FIRST)
# ======================================================================

# The learner never bypasses hard safety gates. It selects among candidates
# already accepted by the research-only EXPLORATORY lane and remains shadow
# only until chronological out-of-sample checks approve a champion model.
SCALPING_V63_SELF_LEARNING_ENABLED = True
SCALPING_V63_LEARNED_LANE_ENABLED = True
SCALPING_V63_LEARNED_LANE_NAME = "LEARNED"
SCALPING_V63_LEARNED_BASE_LANE = "EXPLORATORY"
SCALPING_V63_MODEL_FOLDER = "data/models/v63"
SCALPING_V63_CHAMPION_MODEL_PATH = "data/models/v63/champion.joblib"
SCALPING_V63_CHALLENGER_MODEL_PATH = "data/models/v63/challenger.joblib"
SCALPING_V63_MODEL_REPORT_PATH = "data/models/v63/model_report.json"
SCALPING_V63_DRIFT_REPORT_PATH = "data/models/v63/drift_report.json"
SCALPING_V63_MODEL_REGISTRY_PATH = "data/models/v63/registry.json"
SCALPING_V63_MIN_CLOSED_TRADES_TO_TRAIN = 80
SCALPING_V63_MIN_TRAIN_TRADES_PER_FOLD = 50
SCALPING_V63_MIN_OOS_SELECTED_TRADES = 20
SCALPING_V63_MIN_WALK_FORWARD_FOLDS = 4
SCALPING_V63_RETRAIN_EVERY_CLOSED_TRADES = 20
SCALPING_V63_TARGET_WIN_RATE = 0.59
SCALPING_V63_MIN_OOS_WIN_RATE = 0.59
SCALPING_V63_MIN_OOS_EXPECTANCY_USD = 0.03
SCALPING_V63_MIN_OOS_PROFIT_FACTOR = 1.15
SCALPING_V63_MIN_OOS_COVERAGE = 0.08
SCALPING_V63_MAX_OOS_BRIER_SCORE = 0.25
SCALPING_V63_MAX_OOS_CALIBRATION_ERROR = 0.12
SCALPING_V63_MIN_PROBABILITY_THRESHOLD = 0.55
SCALPING_V63_MAX_PROBABILITY_THRESHOLD = 0.90
SCALPING_V63_MODEL_MAX_AGE_DAYS = 7
SCALPING_V63_MIN_REGIME_SAMPLES = 15
SCALPING_V63_DRIFT_RECENT_TRADES = 50
SCALPING_V63_DRIFT_PSI_WARNING = 0.20
SCALPING_V63_DRIFT_PSI_BLOCK = 0.30
SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL = True
SCALPING_V63_AUTO_RETRAIN_AFTER_CLOSE = True

# V6.3.2 reliability controls. The 59% target must be supported by a
# confidence-aware lower bound and by performance across multiple chronological
# folds. This prevents one favorable test segment from approving a model.
SCALPING_V632_WIN_RATE_CONFIDENCE_Z = 1.6448536269514722  # one-sided 90%
SCALPING_V632_MIN_OOS_WIN_RATE_LOWER_BOUND = 0.50
SCALPING_V632_MIN_SELECTED_FOLDS = 3
SCALPING_V632_MAX_NEGATIVE_SELECTED_FOLDS = 1
SCALPING_V632_MIN_SELECTED_TRADES_PER_FOLD = 3
SCALPING_V632_PERMUTATION_IMPORTANCE_REPEATS = 3
# The final chronological walk-forward fold is never used to choose the
# probability threshold.  It is an untouched confirmation set that must pass
# the same economic and confidence-aware requirements before promotion.
SCALPING_V632_UNTOUCHED_HOLDOUT_ENABLED = True
SCALPING_V632_MIN_HOLDOUT_SELECTED_TRADES = 5

# Cost-aware adaptive triple barriers. At 0.01 lot on standard XAUUSD, one
# dollar of price movement is approximately one dollar of P/L. The policy
# keeps the target/stop ratio above 0.80 so a 59% win rate has positive room
# before slippage, while still adapting to spread and M1 ATR.
SCALPING_V63_DYNAMIC_BARRIERS_ENABLED = True
SCALPING_V63_TARGET_MIN_USD = 0.90
SCALPING_V63_TARGET_MAX_USD = 1.20
SCALPING_V63_STOP_MIN_USD = 1.00
SCALPING_V63_STOP_MAX_USD = 1.20
SCALPING_V63_TARGET_SPREAD_MULTIPLE = 4.00
SCALPING_V63_STOP_SPREAD_MULTIPLE = 4.50
SCALPING_V63_TARGET_ATR_MULTIPLE = 0.22
SCALPING_V63_STOP_ATR_MULTIPLE = 0.26
SCALPING_V63_MIN_TARGET_STOP_RATIO = 0.80
SCALPING_V63_PROFIT_LOCK_STAGE1_PEAK_RATIO = 0.55
SCALPING_V63_PROFIT_LOCK_STAGE1_FLOOR_RATIO = 0.18
SCALPING_V63_PROFIT_LOCK_STAGE2_PEAK_RATIO = 0.80
SCALPING_V63_PROFIT_LOCK_STAGE2_FLOOR_RATIO = 0.48

# V6.3.2 conservative shadow fill accounting.
# Profitable target crossings are booked at the planned barrier rather than
# the later polling quote. Adverse stop crossings remain booked at the
# observed executable quote so shadow results do not benefit from optimistic
# polling gaps.
SCALPING_V632_SHADOW_TARGET_FILL_MODE = "PLANNED_BARRIER"
SCALPING_V632_SHADOW_STOP_FILL_MODE = "OBSERVED_EXECUTABLE_QUOTE"
SCALPING_V632_RECORD_BARRIER_OVERSHOOT = True
SCALPING_V6_MAX_RESEARCH_MONITORING_GAP_SECONDS = 300.0


# ======================================================================
# MEDIUM-HORIZON MULTI-TIMEFRAME MODEL (ISOLATED SHADOW RESEARCH)
# ======================================================================

# This is deliberately separate from the V6 scalper and has no broker-order
# path.  It evaluates completed M15/H1/H4 bars, deriving 45-minute and 2-hour
# views from those broker bars.  There is no daily entry limit; one distinct
# completed M15 signal can enter once and exposure is capped at two positions.
SCALPING_MEDIUM_STRATEGY_ID = "XAUUSD_MEDIUM_MTF_SHADOW_V1"
SCALPING_MEDIUM_STATE_PATH = "data/runtime/medium_horizon_shadow_state.json"
SCALPING_MEDIUM_HISTORY_PATH = "data/runtime/medium_horizon_shadow_history.jsonl"
SCALPING_MEDIUM_LOT_SIZE = 0.01
SCALPING_MEDIUM_TARGET_USD = 1.50
SCALPING_MEDIUM_HARD_STOP_USD = 1.80
SCALPING_MEDIUM_MAX_HOLD_SECONDS = 14400.0
SCALPING_MEDIUM_MIN_HOLD_BEFORE_THESIS_EXIT_SECONDS = 900.0
SCALPING_MEDIUM_THESIS_EXIT_LOSS_USD = 0.75
SCALPING_MEDIUM_MAX_OPEN_POSITIONS = 2
SCALPING_MEDIUM_MAX_ENTRY_SPREAD_USD = 0.30
SCALPING_MEDIUM_MAX_QUOTE_AGE_SECONDS = 3.0
SCALPING_MEDIUM_MIN_DIRECTIONAL_VOTES = 3
SCALPING_MEDIUM_MIN_BARS = 55
SCALPING_MEDIUM_MIN_EMA_SEPARATION_ATR = 0.04
SCALPING_MEDIUM_MAX_ENTRY_DISTANCE_ATR = 0.90
SCALPING_MEDIUM_LOOP_INTERVAL_SECONDS = 1.0
SCALPING_MEDIUM_MAX_SIGNAL_AGE_SECONDS = 1800.0
SCALPING_MEDIUM_REQUIRE_H4_NOT_OPPOSED = True
SCALPING_MEDIUM_USE_NEWS_VETO = True
SCALPING_MEDIUM_USE_CROSS_MARKET_VETO = True
SCALPING_MEDIUM_DATA_ROOT = "data/research/medium_horizon"
# Disabled after the conservative 2024-07-24..2026-07-24 broker-bar screen:
# 1,581 episode-decorrelated trades, 37.2% WR, -$0.573 expectancy, PF 0.49,
# with every quarterly fold negative. Do not enable by threshold fitting on
# that same dataset; a revised hypothesis needs an untouched holdout.
SCALPING_MEDIUM_ENTRY_ENABLED = False
SCALPING_MEDIUM_APPROVAL_MIN_TRADES = 200
SCALPING_MEDIUM_APPROVAL_MIN_WIN_RATE = 0.59
SCALPING_MEDIUM_APPROVAL_MIN_EXPECTANCY_USD = 0.03
SCALPING_MEDIUM_APPROVAL_MIN_PROFIT_FACTOR = 1.15
SCALPING_MEDIUM_APPROVAL_MAX_NEGATIVE_FOLDS = 1
