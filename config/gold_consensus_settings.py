"""Isolated settings for the three-advisor MT5 demo consensus bot."""

SYMBOL = "XAUUSD"
CONTINUOUS_DIRECTIONAL_ENTRIES = True
VERY_WEAK_EVIDENCE = 15.0
CANDLE_CONFIRM_STRONG_EVIDENCE = 85.0
CANDLE_CONFIRM_WEAKENED_EVIDENCE = 80.0
CANDLE_CONFIRM_DROP_POINTS = 10.0
SCALP_M1_CONFIRMATION_BARS = 1
SCALP_STAGED_M1_ENABLED = True
SCALP_SMC_CONFIG = {'commission_price': None, 'slippage_price': None}
# Verified against fresh terminal ticks on 2026-10-26: broker clock = UTC+2.
# Change explicitly if the broker/server or its DST convention changes.
MT5_SERVER_UTC_OFFSET_SECONDS = 7200
# Small broker/PC clock skew is permitted; larger future offsets remain invalid.
MT5_QUOTE_FUTURE_TOLERANCE_SECONDS = 5.0
MAGIC_NUMBER = 631005
ORDER_COMMENT = "GoldConsensusDemo"
LOT_SIZE = 0.01
FAST_RANGE_COST_FILTER_ENABLED = True
FAST_MICRO_CONFIRMATION_REQUIRED = True
FAST_DEMO_ACTIVITY_MODE = True
THREE_SOURCE_VOTE_ENABLED = True
MARKET_AWARE_SOURCE_ENABLED = True
EXECUTABLE_THESIS_ENABLED = False  # Frozen replay failed; do not promote to demo orders.
EXECUTABLE_THESIS_SHADOW_ENABLED = True
FAST_MICRO_WINDOW_SECONDS = 3
FAST_CONFIRMATION_BARS = 1
FAST_RANGE_COST_MULTIPLE = 1.0
# User constraints: three positions TOTAL across all lanes, fixed 0.01 lot.
STARTING_CAPITAL_USD = 100.0
MAX_POSITION_SLOTS = 3
SCALP_EXTENDED_POSITION_EVIDENCE = 85.0
# No fixed USD ceiling is imposed on the market-structure stop. The stop is
# still mandatory, broker-side, directionally valid and checked against the
# broker grid before every order. Open-position risk is managed by that stop
# plus the adaptive tick/candle exit stack below.
MAX_TRADE_RISK_USD = None
BASKET_TAKE_PROFIT_USD = 5.0
BASKET_STOP_LOSS_USD = 4.0
INDIVIDUAL_EMERGENCY_STOP_USD = 5.0
MINIMUM_EVIDENCE = 85.0
SCALP_ENTRY_EVIDENCE = 85.0
SCALP_INVERSION_EVIDENCE = 50.0
MINIMUM_INDIVIDUAL_EVIDENCE = 75.0
LONE_DIRECTION_EVIDENCE = 90.0
API_REFRESH_SECONDS = 60.0
API_MAX_AGE_SECONDS = 90.0
API_MAX_BAR_AGE_SECONDS = 180.0
MAX_FEED_PRICE_DIFFERENCE_USD = 5.0
MT5_MAX_AGE_SECONDS = 45.0
V3_MAX_AGE_SECONDS = 10.0
V3_REFRESH_SECONDS = 5.0
LOOP_INTERVAL_SECONDS = 0.25  # target cadence; processing latency varies, persistence uses elapsed time
DISPLAY_INTERVAL_SECONDS = 15.0
TRADE_HISTORY_LIMIT = 50
TRADE_HISTORY_REFRESH_SECONDS = 5.0
MINIMUM_ENTRY_SPACING_SECONDS = 2.0
# SCALP retains normal access. Secondary correlated additions wait for profitable
# exposure and fresh M5 follow-through; OBSERVE restores diagnostics-only mode.
# This is demo risk allocation, not a validated prediction of positive returns.
ENTRY_COORDINATION_MODE = 'SCALP_PRIORITY'
ENTRY_CONFIRMATION_CYCLES = 2
MAX_SPREAD_USD = 0.75
MAX_QUOTE_AGE_SECONDS = 2.0
ORDER_DEVIATION_POINTS = 20
MAX_SPREAD_TO_ANALYSIS_TARGET_RATIO = 0.35
MIN_ANALYSIS_REWARD_RISK = 0.70
ENTRY_ZONE_TOLERANCE_SPREADS = 1.0
MAX_SESSION_MINUTES = 120.0
MAX_SESSION_LOSS_USD = None
SESSION_LOSS_STOP_ENABLED = False
POST_EXIT_ANALYSIS_SECONDS = 1.0
LOSS_LOOKBACK_HOURS = 24.0
JOURNAL_PATH = "data/demo/gold_consensus_demo_journal.jsonl"
LOCK_PATH = "data/runtime/scalping_loop.lock"
CLOSE_POSITIONS_ON_STOP = True

HORIZON_HISTORY_LIMIT = 30
HISTORY_RESET_PATH = "data/runtime/gold_horizon_history_resets.json"
LOSS_RESET_PATH = "data/runtime/gold_horizon_loss_reset.json"
HORIZON_CUMULATIVE_TAKE_PROFIT_USD = 5.0
HORIZON_REENTRY_DELAY_SECONDS = 2.0

# --- Exit feed-age policy -------------------------------------------------
# A quote that has not CHANGED for a few seconds is a quiet market, not a
# broken feed: MT5 publishes no tick when nothing trades. Gating protective
# exits on "seconds since the quote last changed" silently disarmed position
# management during exactly the slow adverse drifts it exists to catch (33% of
# recorded position-cycles on 2026-09-10..15). Exits are therefore gated on
# BROKER TICK AGE only, and are allowed a wider ceiling than entries:
# being slow to close is the dangerous failure, being slow to open is not.
ENTRY_MAX_QUOTE_AGE_SECONDS = 2.0
EXIT_MAX_FEED_AGE_SECONDS = 15.0

# --- Risk-anchored adaptive management ------------------------------------
# Selected explicitly with --exit-policy adaptive. Distances are expressed in
# R, where R is the lane's own money stop converted to a price distance
# (R_price = stop_usd / (volume * contract_size)). R is scale-free: it does not
# drift as gold moves from $2,000 to $4,270, and it cannot be set beyond the
# risk actually budgeted for the trade -- the defect that made the previous
# ATR-multiple trail unreachable in every lane.
#
#   trail_arm_r       peak profit needed before the trail arms
#   trail_giveback_r  profit given back from the peak that closes the trade
#   breakeven_arm_r   peak profit after which the trade may no longer return
#                     below entry + round-trip cost (a winner cannot become a
#                     loser once it has paid for itself)
#   conviction_*      bounds on how far the conscience may scale the giveback
#
# These are risk/behaviour defaults, not optimized profitability estimates.
ADAPTIVE_EXIT_CONFIG = {
    # fast_flow_exit_risk: graded micro-flow reversal risk (0..1) that banks an
    # open profit immediately, without waiting for the giveback trail or for a
    # confirmed reversal. None disables it -- a three-second flow turn is not a
    # reason to close a swing.
    'SCALP': {
        'profit_lock_arm_usd': 1.0, 'profit_lock_retained_fraction': 0.80,
        'trail_arm_r': 0.40, 'trail_giveback_r': 0.35, 'breakeven_arm_r': 0.60,
        'exit_confirmation_seconds': 10, 'stagnation_seconds': 1800,
        'fast_flow_exit_risk': 0.70,
    },
    'INTRADAY': {
        'trail_arm_r': 0.50, 'trail_giveback_r': 0.45, 'breakeven_arm_r': 0.80,
        'exit_confirmation_seconds': 30, 'stagnation_seconds': 7200,
        'fast_flow_exit_risk': 0.85,
    },
    'SWING': {
        'trail_arm_r': 0.60, 'trail_giveback_r': 0.55, 'breakeven_arm_r': 1.00,
        'exit_confirmation_seconds': 60, 'stagnation_seconds': 28800,
        'fast_flow_exit_risk': None,
    },
}
# Floors stop a giveback from being set inside dealing noise, and the cap stops
# the conscience from ever widening one without limit.
ADAPTIVE_GIVEBACK_SPREAD_FLOOR = 2.5
ADAPTIVE_GIVEBACK_ATR_FLOOR = 0.05
ADAPTIVE_GIVEBACK_MIN_SCALE = 0.55
ADAPTIVE_GIVEBACK_MAX_SCALE = 1.60
# Round-trip cost assumption used by the breakeven ratchet, in spreads.
ADAPTIVE_ROUND_TRIP_COST_SPREADS = 1.5

# --- Quote-flow protection -------------------------------------------------
# Windows stay in seconds (they describe how long flow must persist), but the
# adverse-move threshold is derived from live ATR and spread instead of the
# former hardcoded dollars, which were written at ~$2,000 gold and had decayed
# to ~0.06 ATR by $4,270 -- inside noise.
FLOW_EXIT_CONFIG = {
    'SCALP': {'window_seconds': 12, 'confirmation_seconds': 6, 'atr_threshold': 0.10},
    'INTRADAY': {'window_seconds': 30, 'confirmation_seconds': 12, 'atr_threshold': 0.12},
    'SWING': {'window_seconds': 90, 'confirmation_seconds': 30, 'atr_threshold': 0.15},
}
FLOW_EXIT_SPREAD_FLOOR = 2.0
FLOW_EXIT_MIN_EFFICIENCY = 0.65

# --- Position conscience ---------------------------------------------------
# A continuous "am I still right?" score for an OPEN position, fusing every
# resource the bot already collects. It is advisory over exits only: it can
# tighten protection freely, may widen it only within
# ADAPTIVE_GIVEBACK_MAX_SCALE and only on good source coverage, and can never
# authorize an entry, resize a position or override a stop.
CONSCIENCE_ENABLED = True
# micro_flow carries real weight because it is the only source that reports
# between candles, which is the timescale a scalp actually lives on.
CONSCIENCE_WEIGHTS = {
    'consensus': 0.20,
    'structure': 0.15,
    'quote_flow': 0.15,
    'micro_flow': 0.20,
    'regime': 0.08,
    'cross_market': 0.09,
    'learned': 0.06,
    'economic': 0.04,
    'news': 0.03,
}
# Below this share of usable weight the score is reported but never widens a
# giveback: thin evidence must not be read as confidence.
CONSCIENCE_MIN_COVERAGE_TO_WIDEN = 0.60
# Collapsed conviction banks an open profit rather than waiting for the trail.
CONSCIENCE_EXIT_CONVICTION = 0.28
CONSCIENCE_EXIT_MIN_PROFIT_R = 0.20
CONSCIENCE_EXIT_CONFIRMATION_SECONDS = {'SCALP': 8.0, 'INTRADAY': 20.0, 'SWING': 45.0}

# --- SCALP continuous-flow profile -----------------------------------------
# Measured on 2,420 recorded SCALP cycles (2026-09-10..15): when directional,
# MT5_CANDLES and API_CANDLES evidence is distributed around a median of 75
# (p90 ~89), while MT5_TICK_FLOW sits at a median of 54 (p90 72, max 91.5).
# The three advisors do not share a scale. A single 82 bar therefore let the
# candle advisors qualify in ~15% of directional cycles and the tick advisor in
# 1.6% -- and because SCALP *requires* MT5_TICK_FLOW to be strong, the lane was
# entry-eligible in 1 cycle out of 2,420 (0.04%). The lane's own weights say
# tick flow is 60% of the decision; the shared threshold inverted that intent.
#
# FLOW_PRIMARY restores it: the tick advisor decides direction and timing
# against its OWN scale, slower structure keeps a veto, and levels come from
# ATR rather than from an agreeing candle advisor -- in 88% of strong-flow
# moments no candle advisor agrees, which is the normal case for fast flow, not
# a reason to stand down.
SCALP_FLOW_ENTRY_EVIDENCE = 60.0        # ~p75 of directional tick-flow evidence
SCALP_OPPOSING_VETO_EVIDENCE = 72.0     # a usable advisor opposing this hard blocks
SCALP_LEVEL_TARGET_ATR = 0.60           # TP distance, in exit-frame ATR
SCALP_LEVEL_STOP_ATR = 0.80             # SL distance, in exit-frame ATR

# Re-entry: a scalper must be able to act on the next flow reading, including
# in the opposite direction. Slower lanes still wait for a fresh completed bar.
SCALP_REENTRY_COOLDOWN_SECONDS = 1.0
SCALP_ALLOW_DIRECTION_FLIP = True

# Churn guards. Trading continuously is only survivable with these: at a $0.24
# median spread, cost is what decides the outcome, not signal frequency.
SCALP_MAX_TRADES_PER_HOUR = 240  # demo activity ceiling, never a trade quota
SCALP_MAX_CONSECUTIVE_LOSSES = 4
SCALP_LOSS_COOLDOWN_SECONDS = 30.0
SCALP_MAX_SPREAD_USD = MAX_SPREAD_USD   # live Oct 8 spread exceeds old .35 ceiling; target-cost checks still apply
SCALP_BLOCK_VOLATILITY_EXPANSION = True

# Cost-aware micro profit-taking. "Bank it when flow turns" is only a profit if
# it clears the round trip; below that floor it is a loss wearing a green
# number, so the exit still fires but is never counted as taking profit.
SCALP_MIN_PROFIT_TAKE_SPREADS = 2.0
SCALP_MIN_PROFIT_TAKE_USD = 0.30
SCALP_REVERSAL_RISK_EXIT = 0.70         # graded micro-flow reversal risk, 0..1

# --- Micro-flow engine -----------------------------------------------------
# Graded, continuously-updated read of the executable quote stream at loop
# cadence. Distinct from gold_flow_exit, which is a confirmed-reversal closer:
# this one produces a 0..1 reversal risk that can act before confirmation, and
# a directional read used for re-entry.
MICRO_FLOW_WINDOWS_SECONDS = (6.0, 12.0, 30.0)  # also usable if processing stretches cadence to two seconds
MICRO_FLOW_MIN_SAMPLES = 4
MICRO_FLOW_MAX_SAMPLE_GAP_SECONDS = 8.0
MICRO_FLOW_MAX_BUFFER = 512

# --- Horizon priority ------------------------------------------------------
# When the global three-slot cap binds, lanes are considered in this order.
# SCALP is considered first. This ordering is not evidence of better returns.
# SCALP uses analysis-derived stops; the legacy dollar cap applies to other modes.
HORIZON_PRIORITY = ("SCALP", "INTRADAY", "SWING")
# Research found no validated basis for deterministically reversing weak
# evidence. Retained only for backward-compatible dashboard configuration.
SCALP_WEAK_BIAS_INVERSION_ENABLED = False
SCALP_INVERSE_BELOW_EVIDENCE = 78.5
HORIZON_LANES = {
    "SCALP": {
        "magic": 631011, "comment": "GoldScalpDemo", "max_positions": 3, "trade_enabled": True,
        # Flow decides direction and timing; M1 is the substrate a scalper can
        # actually react on (M5 re-evaluates only every five minutes).
        "entry_mode": "ADVISOR1_PRIMARY", "exit_frame": "M1",
        "entry_evidence": 82.0, "exit_evidence": 58.0, "confirmation_cycles": 2,
        "stop_mode": "ANALYSIS", "individual_stop_loss_usd": None,
        "advisor_weights": {"MT5_CANDLES": 0.30, "API_CANDLES": 0.10, "MT5_TICK_FLOW": 0.60},
        "required_strong_advisors": ("MT5_CANDLES",), "minimum_signal_seconds": 1.0,
        "add_position_evidence": 75.0, "add_position_spacing_seconds": 5.0,
        "news_policy": "CLOSE_AND_BLOCK", "preferred_target": "tp1",
    },
    "INTRADAY": {
        "entry_mode": "CONSENSUS_2_OF_3", "exit_frame": "M15",
        "magic": 631012, "comment": "GoldIntradayDemo", "max_positions": 2, "trade_enabled": False,
        "entry_evidence": 82.0, "exit_evidence": 60.0, "confirmation_cycles": 2,
        "stop_mode": "INDIVIDUAL", "individual_stop_loss_usd": 5.0,
        "advisor_weights": {"MT5_CANDLES": 0.45, "API_CANDLES": 0.40, "MT5_TICK_FLOW": 0.15},
        "required_strong_advisors": ("MT5_CANDLES", "API_CANDLES"), "minimum_signal_seconds": 15.0,
        "add_position_evidence": 90.0, "add_position_spacing_seconds": 30.0,
        "news_policy": "CLOSE_AND_BLOCK", "preferred_target": "tp2",
    },
    "SWING": {
        "entry_mode": "CONSENSUS_2_OF_3", "exit_frame": "H1",
        "magic": 631013, "comment": "GoldSwingDemo", "max_positions": 2, "trade_enabled": False,
        "entry_evidence": 85.0, "exit_evidence": 62.0, "confirmation_cycles": 1,
        "stop_mode": "INDIVIDUAL", "individual_stop_loss_usd": 5.0,
        "advisor_weights": {"MT5_CANDLES": 0.45, "API_CANDLES": 0.45, "MT5_TICK_FLOW": 0.10},
        "required_strong_advisors": ("MT5_CANDLES", "API_CANDLES"), "minimum_signal_seconds": 30.0,
        "add_position_evidence": 92.0, "add_position_spacing_seconds": 60.0,
        "news_policy": "BLOCK_NEW", "preferred_target": "tp3",
    },
}
