# ======================================================================
# CORE TRADING SETTINGS
# ======================================================================

SYMBOL = "XAUUSD"
LOT_SIZE = 0.01
MAGIC_NUMBER = 20260709

MAX_SPREAD = 1.00
PROFIT_TARGET_USD = 2.00

MIN_AI_CONFIDENCE = 0.60
MAX_OPEN_POSITIONS = 1


# ======================================================================
# LIVE-TRADING SAFETY
# ======================================================================

# Keep live trading disabled during paper validation.
ENABLE_LIVE_TRADING = False
EMERGENCY_STOP = False

LIVE_TRADING_CONFIRMATION = ""
REQUIRED_LIVE_TRADING_CONFIRMATION = "I_ACCEPT_LIVE_TRADING_RISK"

REQUIRE_LIVE_READINESS_BEFORE_TRADING = True


# ======================================================================
# BOT EXECUTION
# ======================================================================

RUN_INTERVAL_SECONDS = 60
MAX_BOT_CYCLES = 480


# ======================================================================
# LOGGING
# ======================================================================

LOG_FILE_PATH = "logs/bot_cycle_log.csv"

SIGNAL_LOG_FOLDER = "logs/signals"
SAVE_SIGNAL_TEXT_LOGS = True

USE_DAILY_LOG_FOLDERS = True
LOG_DATE_FORMAT = "%Y-%m-%d"


# ======================================================================
# PAPER TRADING
# ======================================================================

PAPER_STOP_LOSS_USD = 2.00
PAPER_MAX_HOLD_SECONDS = 300
PAPER_CLOSE_ON_OPPOSITE_SIGNAL = True


# ======================================================================
# TRADE QUALITY FILTERS
# ======================================================================

MIN_TRADE_SCORE = 70
MIN_TREND_CONFIDENCE = 0.60
MIN_STRUCTURE_CONFIDENCE = 0.50

BLOCK_HIGH_VOLATILITY_TRADES = False
BLOCK_NEUTRAL_STRUCTURE_TRADES = True

BLOCK_UNSAFE_SPREAD_TRADES = True
BLOCK_INVALID_PRICE_TRADES = True
BLOCK_MISSING_CANDLE_TRADES = True
BLOCK_INACTIVE_SESSION_TRADES = True
BLOCK_UNKNOWN_VOLATILITY_TRADES = True
BLOCK_EXTREME_VOLATILITY_TRADES = True


# ======================================================================
# ADVANCED RISK ENGINE
# ======================================================================

ENABLE_ADVANCED_RISK_ENGINE = True

DAILY_LOSS_LIMIT_USD = 10.00
MAX_DAILY_TRADES = 20
MAX_CONSECUTIVE_LOSSES = 3
MAX_DRAWDOWN_USD = 15.00


# ======================================================================
# SLIPPAGE PROTECTION
# ======================================================================

MAX_SLIPPAGE_USD = 0.50
BLOCK_ON_SLIPPAGE_CHECK_ERROR = True


# ======================================================================
# LIVE READINESS REQUIREMENTS
# ======================================================================

MIN_CLOSED_PAPER_TRADES_FOR_LIVE = 20
MIN_PAPER_WIN_RATE_FOR_LIVE = 55.0
MAX_ALLOWED_PAPER_DRAWDOWN_FOR_LIVE = 10.00

REQUIRE_RISK_ENGINE_FOR_LIVE = True
REQUIRE_SLIPPAGE_GUARD_FOR_LIVE = True


# ======================================================================
# FORWARD VALIDATION
# ======================================================================

FORWARD_VALIDATION_CYCLES = 20
FORWARD_VALIDATION_INTERVAL_SECONDS = 5


# ======================================================================
# NEWS RISK FILTER
# ======================================================================

ENABLE_NEWS_RISK_FILTER = True
NEWS_EVENTS_FILE = "data/economic_events.json"

NEWS_BLOCK_BEFORE_MINUTES = 30
NEWS_BLOCK_AFTER_MINUTES = 15

BLOCK_HIGH_IMPACT_NEWS = True
BLOCK_MEDIUM_IMPACT_NEWS = False
BLOCK_UNVERIFIED_CONSERVATIVE_EVENTS = False


# ======================================================================
# TEST SUITE
# ======================================================================

RUN_MAIN_IN_TEST_SUITE = False
RUN_TEST_TIMEOUT_SECONDS = 120


# ======================================================================
# FMP API KEY
# ======================================================================

# Keep this blank.
# The real key should be loaded from the FMP_API_KEY environment variable.
FMP_API_KEY = ""


# ======================================================================
# AUTOMATIC ECONOMIC CALENDAR
# ======================================================================

ENABLE_AUTO_ECONOMIC_CALENDAR = True

# The FMP calendar endpoint may return 403 on the free plan.
# The free calendar fallback must remain enabled below.
AUTO_ECONOMIC_CALENDAR_PROVIDER = "FMP"

AUTO_ECONOMIC_CALENDAR_COUNTRY = "US"
AUTO_ECONOMIC_CALENDAR_CURRENCY = "USD"
AUTO_ECONOMIC_CALENDAR_DAYS_AHEAD = 14

AUTO_ECONOMIC_CALENDAR_REFRESH_HOURS = 3
AUTO_ECONOMIC_CALENDAR_TIMEOUT_SECONDS = 20

AUTO_ECONOMIC_CALENDAR_SYNC_FILE = (
    "data/economic_calendar_sync.json"
)

AUTO_ECONOMIC_CALENDAR_KEYWORDS = [
    "CPI",
    "Consumer Price Index",
    "NFP",
    "Non Farm Payrolls",
    "Non-Farm Payrolls",
    "Nonfarm Payrolls",
    "Payrolls",
    "FOMC",
    "Federal Reserve",
    "Fed Interest Rate Decision",
    "Interest Rate Decision",
    "Core PCE",
    "PCE Price Index",
    "Personal Consumption Expenditures",
    "Unemployment Rate",
    "Retail Sales",
]


# ======================================================================
# FREE ECONOMIC CALENDAR FALLBACK
# ======================================================================

ENABLE_FREE_CALENDAR_FALLBACK = True
FREE_CALENDAR_FALLBACK_DAYS_AHEAD = 14
FREE_CALENDAR_TIMEOUT_SECONDS = 20
FREE_CALENDAR_TIMEZONE = "America/New_York"
FREE_CALENDAR_USE_CONSERVATIVE_ESTIMATES = True


# ======================================================================
# FMP FREE MARKET CONTEXT
# ======================================================================

ENABLE_FMP_MARKET_CONTEXT = True

FMP_MARKET_CONTEXT_TIMEOUT_SECONDS = 20
FMP_MARKET_CONTEXT_FILE = "data/fmp_market_context.json"

# Use one free gold quote request every three hours.
# This produces approximately eight FMP quote calls per day.
FMP_MARKET_CONTEXT_REFRESH_HOURS = 3

FMP_GOLD_SYMBOL = "GCUSD"

# Forex news requires paid FMP access.
# Keep this disabled to prevent HTTP 402 errors and unnecessary calls.
ENABLE_FMP_FOREX_NEWS = False

# Retained for compatibility with existing modules.
# It is ignored while ENABLE_FMP_FOREX_NEWS is False.
FMP_FOREX_NEWS_LIMIT = 10

# Maximum acceptable difference between the FMP GCUSD quote
# and the MT5 XAUUSD market price.
FMP_PRICE_CONFIRMATION_MAX_DIFF_USD = 25.00

FMP_CONTEXT_CONFIDENCE_BONUS = 0.03
FMP_CONTEXT_CONFIDENCE_PENALTY = 0.05

FMP_HIGH_RISK_NEWS_KEYWORDS = [
    "fed",
    "fomc",
    "powell",
    "rate decision",
    "interest rate",
    "inflation",
    "cpi",
    "pce",
    "nfp",
    "payroll",
    "unemployment",
    "jobs report",
    "retail sales",
    "dollar",
    "treasury yields",
    "war",
    "geopolitical",
]
# ======================================================================
# RUNTIME EMERGENCY-STOP CONTROL
# ======================================================================

# Creating this file stops both normal and scalping loops on the next cycle.
# Delete the file only after the reason for stopping has been reviewed.
EMERGENCY_STOP_FILE = "data/EMERGENCY_STOP.flag"
