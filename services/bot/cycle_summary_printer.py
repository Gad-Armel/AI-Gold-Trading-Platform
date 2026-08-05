from collections.abc import Mapping
from typing import Any


SUMMARY_WIDTH = 70
NOT_AVAILABLE = "N/A"


# ======================================================================
# SAFE VALUE HELPERS
# ======================================================================

def _get(
    source: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Safely reads a field from either:
    - a dictionary/mapping;
    - a dataclass or regular object.
    """

    if source is None:
        return default

    if isinstance(source, Mapping):
        return source.get(key, default)

    return getattr(source, key, default)


def _first(
    source: Any,
    keys: list[str] | tuple[str, ...],
    default: Any = NOT_AVAILABLE,
) -> Any:
    """
    Returns the first usable value found among several possible field names.
    """

    for key in keys:
        value = _get(source, key, None)

        if value is not None and value != "":
            return value

    return default


def _display(
    value: Any,
    default: str = NOT_AVAILABLE,
) -> Any:
    if value is None or value == "":
        return default

    return value


def _yes_no(value: Any) -> str:
    if value is True:
        return "YES"

    if value is False:
        return "NO"

    if value is None or value == "":
        return NOT_AVAILABLE

    return str(value)


def _format_price(price: Any) -> str:
    """
    Formats a price object containing bid, ask, and spread.

    Supports dictionaries and object-based price states.
    """

    if price is None:
        return NOT_AVAILABLE

    bid = _first(
        price,
        ["bid"],
        default=None,
    )

    ask = _first(
        price,
        ["ask"],
        default=None,
    )

    spread = _first(
        price,
        ["spread"],
        default=None,
    )

    if bid is not None or ask is not None or spread is not None:
        return (
            f"Bid: {_display(bid)} | "
            f"Ask: {_display(ask)} | "
            f"Spread: {_display(spread)}"
        )

    return str(price)


def _section() -> None:
    print("-" * SUMMARY_WIDTH)


def _header(title: str) -> None:
    print("")
    print("=" * SUMMARY_WIDTH)
    print(title)
    print("=" * SUMMARY_WIDTH)


def _footer() -> None:
    print("=" * SUMMARY_WIDTH)
    print("")


# ======================================================================
# CYCLE SUMMARY
# ======================================================================

def print_cycle_summary(bot_cycle: Any) -> None:
    """
    Prints one readable summary for a successful or failed bot cycle.

    The function supports both dictionary-based and object-based cycle data.
    Missing optional fields are displayed as N/A instead of raising errors.
    """

    error_message = _get(
        bot_cycle,
        "error_message",
        "",
    )

    runtime_seconds = _get(
        bot_cycle,
        "runtime_seconds",
        NOT_AVAILABLE,
    )

    runtime_ms = _get(
        bot_cycle,
        "runtime_ms",
        NOT_AVAILABLE,
    )

    snapshot = _get(bot_cycle, "snapshot")
    conditions = _get(bot_cycle, "conditions")
    trend = _get(bot_cycle, "trend")
    volatility = _get(bot_cycle, "volatility")
    structure = _get(bot_cycle, "structure")
    decision = _get(bot_cycle, "decision")
    ai_result = _get(bot_cycle, "ai_result")

    trend_confirmation = _get(
        bot_cycle,
        "trend_confirmation",
        {},
    )

    structure_confirmation = _get(
        bot_cycle,
        "structure_confirmation",
        {},
    )

    trade_score = _get(
        bot_cycle,
        "trade_score",
        {},
    )

    ai_quality = _get(
        bot_cycle,
        "ai_quality",
        {},
    )

    advanced_risk = _get(
        bot_cycle,
        "advanced_risk",
        {},
    )

    slippage_guard = _get(
        bot_cycle,
        "slippage_guard",
        {},
    )

    calendar_sync = _get(
        bot_cycle,
        "calendar_sync",
        {},
    )

    news_risk = _get(
        bot_cycle,
        "news_risk",
        {},
    )

    fmp_context = _get(
        bot_cycle,
        "fmp_context",
        {},
    )

    fmp_price_check = _get(
        bot_cycle,
        "fmp_price_check",
        {},
    )

    execution_gate = _get(
        bot_cycle,
        "execution_gate",
    )

    trade_execution = _get(
        bot_cycle,
        "trade_execution",
    )

    dry_run_plan = _get(
        bot_cycle,
        "dry_run_plan",
    )

    profit_manager = _get(
        bot_cycle,
        "profit_manager",
    )

    paper_trade_result = _get(
        bot_cycle,
        "paper_trade_result",
        {},
    )

    paper_trade_report = _get(
        bot_cycle,
        "paper_trade_report",
        {},
    )

    # A failed cycle may not contain a snapshot, so use the cycle symbol
    # attached by cycle_runner.py as a fallback.
    symbol = _first(
        snapshot,
        ["symbol"],
        default=_first(
            bot_cycle,
            ["symbol"],
            default="UNKNOWN",
        ),
    )

    price = _first(
        snapshot,
        ["price"],
        default=NOT_AVAILABLE,
    )

    session_data = _get(
        snapshot,
        "session",
    )

    session = _first(
        session_data,
        [
            "name",
            "primary_session",
            "primary",
        ],
        default=NOT_AVAILABLE,
    )

    if session == NOT_AVAILABLE:
        session = _first(
            snapshot,
            [
                "primary_session",
                "session_name",
            ],
            default=NOT_AVAILABLE,
        )

    # ==================================================================
    # HEADER AND FAILURE HANDLING
    # ==================================================================

    _header(f"BOT CYCLE SUMMARY | {symbol}")

    if error_message:
        print("Cycle Status: FAILED")

        exception_type = _first(
            bot_cycle,
            ["exception_type"],
            default="",
        )

        if exception_type:
            print(f"Exception Type: {exception_type}")

        print(f"Error: {error_message}")
        print(
            f"Cycle Runtime: {runtime_seconds} sec | "
            f"{runtime_ms} ms"
        )

        _footer()
        return

    print("Cycle Status: SUCCESS")
    print(f"Price: {_format_price(price)}")
    print(f"Session: {session}")
    print(
        f"Cycle Runtime: {runtime_seconds} sec | "
        f"{runtime_ms} ms"
    )

    # ==================================================================
    # MARKET CONDITIONS
    # ==================================================================

    market_allowed = _first(
        conditions,
        [
            "trade_allowed",
            "is_safe",
            "spread_safe",
        ],
        default=NOT_AVAILABLE,
    )

    _section()
    print("MARKET CONDITIONS")
    _section()

    print(
        "Market Trade Allowed: "
        f"{_yes_no(market_allowed)}"
    )

    print(
        "Price Valid: "
        f"{_yes_no(_first(conditions, ['price_valid']))}"
    )

    print(
        "Candles Loaded: "
        f"{_yes_no(_first(conditions, ['candles_loaded']))}"
    )

    print(
        "Spread Safe: "
        f"{_yes_no(_first(conditions, ['spread_safe']))}"
    )

    print(
        "Session Active: "
        f"{_yes_no(_first(conditions, ['session_active']))}"
    )

    # ==================================================================
    # TECHNICAL ANALYSIS
    # ==================================================================

    trend_direction = _first(
        trend,
        [
            "overall_trend",
            "direction",
            "trend",
        ],
    )

    trend_confidence = _first(
        trend,
        [
            "trend_confidence",
            "confidence",
            "strength",
        ],
    )

    volatility_level = _first(
        volatility,
        [
            "overall_volatility",
            "level",
            "risk_level",
        ],
    )

    volatility_risk = _first(
        volatility,
        [
            "trade_risk_level",
            "risk_level",
            "risk",
        ],
    )

    structure_bias = _first(
        structure,
        [
            "structure_bias",
            "bias",
        ],
    )

    structure_confidence = _first(
        structure,
        [
            "structure_confidence",
            "confidence",
        ],
    )

    _section()
    print("TECHNICAL ANALYSIS")
    _section()

    print(f"Trend: {trend_direction}")
    print(f"Trend Confidence: {trend_confidence}")

    print(
        "Trend Confirmed: "
        f"{_yes_no(_first(trend_confirmation, ['confirmed']))}"
    )

    print(
        "Trend Confirmation Message: "
        f"{_first(trend_confirmation, ['message'], default='')}"
    )

    print(
        "Trade Score: "
        f"{_first(trade_score, ['score'])}"
    )

    print(
        "Trade Quality: "
        f"{_first(trade_score, ['quality'])}"
    )

    print(f"Volatility: {volatility_level}")
    print(f"Volatility Risk: {volatility_risk}")
    print(f"Structure Bias: {structure_bias}")
    print(
        f"Structure Confidence: {structure_confidence}"
    )

    print(
        "Structure Confirmed: "
        f"{_yes_no(_first(structure_confirmation, ['confirmed']))}"
    )

    print(
        "Structure Confirmation Message: "
        f"{_first(structure_confirmation, ['message'], default='')}"
    )

    # ==================================================================
    # TRADE DECISION
    # ==================================================================

    decision_action = _first(
        decision,
        [
            "action",
            "decision",
        ],
    )

    decision_trade_allowed = _first(
        decision,
        [
            "trade_allowed",
            "can_trade",
        ],
    )

    decision_confidence = _first(
        decision,
        [
            "confidence",
            "decision_confidence",
        ],
    )

    _section()
    print("TRADE DECISION")
    _section()

    print(f"Decision Action: {decision_action}")

    print(
        "Decision Trade Allowed: "
        f"{_yes_no(decision_trade_allowed)}"
    )

    print(
        f"Decision Confidence: {decision_confidence}"
    )

    print(
        "Decision Reasons: "
        f"{_first(decision, ['reasons', 'reason'], default=[])}"
    )

    # ==================================================================
    # AI CONFIRMATION
    # ==================================================================

    ai_action = _first(
        ai_result,
        [
            "ai_action",
            "action",
        ],
    )

    ai_confidence = _first(
        ai_result,
        [
            "confidence",
            "ai_confidence",
        ],
    )

    ai_can_trade = _first(
        ai_result,
        [
            "can_trade",
            "trade_allowed",
        ],
    )

    _section()
    print("AI CONFIRMATION")
    _section()

    print(f"AI Action: {ai_action}")
    print(f"AI Confidence: {ai_confidence}")

    print(
        f"AI Can Trade: {_yes_no(ai_can_trade)}"
    )

    print(
        "AI Quality Passed: "
        f"{_yes_no(_first(ai_quality, ['passed']))}"
    )

    print(
        "AI Quality Block Reasons: "
        f"{_first(ai_quality, ['block_reasons'], default=[])}"
    )

    # ==================================================================
    # ADVANCED RISK ENGINE
    # ==================================================================

    _section()
    print("ADVANCED RISK ENGINE")
    _section()

    print(
        "Advanced Risk Allowed: "
        f"{_yes_no(_first(advanced_risk, ['allowed']))}"
    )

    print(
        "Advanced Risk Action: "
        f"{_first(advanced_risk, ['action'])}"
    )

    print(
        "Daily Realized P/L: "
        f"{_first(advanced_risk, ['daily_realized_profit'])}"
    )

    print(
        "Daily Trade Count: "
        f"{_first(advanced_risk, ['daily_trade_count'])}"
    )

    print(
        "Consecutive Losses: "
        f"{_first(advanced_risk, ['consecutive_losses'])}"
    )

    print(
        "Maximum Drawdown: "
        f"{_first(advanced_risk, ['max_drawdown'])}"
    )

    print(
        "Risk Block Reasons: "
        f"{_first(advanced_risk, ['block_reasons'], default=[])}"
    )

    # ==================================================================
    # SLIPPAGE GUARD
    # ==================================================================

    _section()
    print("SLIPPAGE GUARD")
    _section()

    print(
        "Slippage Guard Allowed: "
        f"{_yes_no(_first(slippage_guard, ['allowed']))}"
    )

    print(
        "Slippage Action: "
        f"{_first(slippage_guard, ['action'])}"
    )

    print(
        "Snapshot Price: "
        f"{_first(slippage_guard, ['snapshot_price'])}"
    )

    print(
        "Latest Price: "
        f"{_first(slippage_guard, ['latest_price'])}"
    )

    print(
        "Slippage: "
        f"{_first(slippage_guard, ['slippage'])}"
    )

    print(
        "Maximum Slippage: "
        f"{_first(slippage_guard, ['max_slippage'])}"
    )

    print(
        "Slippage Block Reasons: "
        f"{_first(slippage_guard, ['block_reasons'], default=[])}"
    )

    # ==================================================================
    # ECONOMIC CALENDAR
    # ==================================================================

    _section()
    print("ECONOMIC CALENDAR")
    _section()

    print(
        "Calendar Sync Success: "
        f"{_yes_no(_first(calendar_sync, ['success']))}"
    )

    print(
        "Calendar Sync Skipped: "
        f"{_yes_no(_first(calendar_sync, ['skipped']))}"
    )

    print(
        "Calendar Sync Message: "
        f"{_first(calendar_sync, ['message'], default='')}"
    )

    print(
        "Calendar Events Added: "
        f"{_first(calendar_sync, ['added_events'], default=0)}"
    )

    # ==================================================================
    # NEWS RISK
    # ==================================================================

    _section()
    print("NEWS RISK FILTER")
    _section()

    print(
        "News Risk Allowed: "
        f"{_yes_no(_first(news_risk, ['allowed']))}"
    )

    print(
        "News Risk Action: "
        f"{_first(news_risk, ['action'])}"
    )

    print(
        "News Risk Message: "
        f"{_first(news_risk, ['message'], default='')}"
    )

    print(
        "Active News Events: "
        f"{_first(news_risk, ['active_events'], default=[])}"
    )

    print(
        "News Block Reasons: "
        f"{_first(news_risk, ['block_reasons'], default=[])}"
    )

    # ==================================================================
    # FMP PHASE 37
    # ==================================================================

    fmp_success = _first(
        fmp_context,
        ["success"],
    )

    fmp_skipped = _first(
        fmp_context,
        ["skipped"],
    )

    fmp_cache_hit = _first(
        fmp_context,
        ["cache_hit"],
        default=False,
    )

    fmp_calls_used = _first(
        fmp_context,
        ["calls_used"],
        default=0,
    )

    fmp_cached_calls = _first(
        fmp_context,
        ["cached_calls_used"],
        default=0,
    )

    fmp_estimated_calls = _first(
        fmp_context,
        ["estimated_calls_per_day"],
        default=0,
    )

    forex_news_enabled = _first(
        fmp_context,
        ["forex_news_enabled"],
        default=False,
    )

    _section()
    print("FMP FREE MARKET CONTEXT — PHASE 37")
    _section()

    print(
        f"FMP Context Success: {_yes_no(fmp_success)}"
    )

    print(
        f"FMP Context Skipped: {_yes_no(fmp_skipped)}"
    )

    print(
        f"FMP Cache Hit: {_yes_no(fmp_cache_hit)}"
    )

    print(
        "FMP Context Message: "
        f"{_first(fmp_context, ['message'], default='')}"
    )

    print(
        "FMP Gold Quote Success: "
        f"{_yes_no(_first(fmp_context, ['gold_quote_success']))}"
    )

    print(
        "FMP Gold Quote Message: "
        f"{_first(fmp_context, ['gold_quote_message'], default='')}"
    )

    print(
        "FMP Gold Quote: "
        f"{_first(fmp_context, ['gold_quote'], default={})}"
    )

    print(
        "FMP Forex News Enabled: "
        f"{_yes_no(forex_news_enabled)}"
    )

    print(
        "FMP Forex News Success: "
        f"{_yes_no(_first(fmp_context, ['forex_news_success']))}"
    )

    print(
        "FMP Forex News Message: "
        f"{_first(fmp_context, ['forex_news_message'], default='')}"
    )

    print(
        "FMP High-Risk News: "
        f"{_yes_no(_first(fmp_context, ['high_risk_news_detected']))}"
    )

    print(
        "FMP Matched Keywords: "
        f"{_first(fmp_context, ['matched_news_keywords'], default=[])}"
    )

    print(f"FMP Calls Used This Cycle: {fmp_calls_used}")

    if fmp_cache_hit:
        print(
            "FMP Calls Used When Cache Was Created: "
            f"{fmp_cached_calls}"
        )

    print(
        "FMP Estimated Calls Per Day: "
        f"{fmp_estimated_calls}"
    )

    print(
        "FMP Price Check Success: "
        f"{_yes_no(_first(fmp_price_check, ['success']))}"
    )

    print(
        "FMP Price Confirmed: "
        f"{_yes_no(_first(fmp_price_check, ['price_confirmed']))}"
    )

    print(
        "FMP Price: "
        f"{_first(fmp_price_check, ['fmp_price'])}"
    )

    print(
        "MT5 Mid Price: "
        f"{_first(fmp_price_check, ['mt5_mid_price'])}"
    )

    print(
        "FMP Price Difference USD: "
        f"{_first(fmp_price_check, ['difference_usd'])}"
    )

    print(
        "Maximum Allowed Difference USD: "
        f"{_first(fmp_price_check, ['max_allowed_difference_usd'])}"
    )

    print(
        "FMP Price Check Message: "
        f"{_first(fmp_price_check, ['message'], default='')}"
    )

    print(
        "FMP Context Applied to AI: "
        f"{_yes_no(_first(ai_result, ['fmp_context_applied']))}"
    )

    print(
        "FMP AI Confidence Adjustment: "
        f"{_first(ai_result, ['fmp_context_adjustment'], default=0.0)}"
    )

    print(
        "FMP AI Context Reason: "
        f"{_first(ai_result, ['fmp_context_reason'], default='')}"
    )

    # ==================================================================
    # EXECUTION GATE
    # ==================================================================

    gate_allowed = _first(
        execution_gate,
        [
            "allowed",
            "allowed_to_execute",
            "can_execute",
        ],
    )

    gate_reason = _first(
        execution_gate,
        [
            "reason",
            "message",
        ],
        default="",
    )

    _section()
    print("EXECUTION GATE")
    _section()

    print(
        "Execution Gate Allowed: "
        f"{_yes_no(gate_allowed)}"
    )

    print(f"Gate Reason: {gate_reason}")

    # ==================================================================
    # TRADE EXECUTION
    # ==================================================================

    trade_attempted = _first(
        trade_execution,
        [
            "attempted",
            "trade_attempted",
        ],
    )

    trade_success = _first(
        trade_execution,
        [
            "success",
            "trade_success",
        ],
    )

    trade_message = _first(
        trade_execution,
        [
            "message",
            "reason",
        ],
        default="",
    )

    _section()
    print("TRADE EXECUTION")
    _section()

    print(
        f"Trade Attempted: {_yes_no(trade_attempted)}"
    )

    print(
        f"Trade Success: {_yes_no(trade_success)}"
    )

    print(f"Trade Message: {trade_message}")

    # ==================================================================
    # DRY-RUN PLAN
    # ==================================================================

    dry_run_action = _first(
        dry_run_plan,
        [
            "action",
            "dry_run_action",
        ],
        default=_first(
            trade_execution,
            ["dry_run_action"],
        ),
    )

    dry_run_direction = _first(
        dry_run_plan,
        [
            "direction",
            "dry_run_direction",
        ],
        default=_first(
            trade_execution,
            ["dry_run_direction"],
        ),
    )

    dry_run_reason = _first(
        dry_run_plan,
        [
            "reason",
            "message",
            "dry_run_reason",
        ],
        default=_first(
            trade_execution,
            ["dry_run_reason"],
            default="",
        ),
    )

    _section()
    print("DRY-RUN PLAN")
    _section()

    print(f"Dry Run Action: {dry_run_action}")
    print(f"Dry Run Direction: {dry_run_direction}")
    print(f"Dry Run Reason: {dry_run_reason}")

    # ==================================================================
    # PAPER TRADING
    # ==================================================================

    _section()
    print("PAPER TRADING")
    _section()

    print(
        "Paper Trade Action: "
        f"{_first(paper_trade_result, ['action'])}"
    )

    print(
        "Paper Trade Message: "
        f"{_first(paper_trade_result, ['message'], default='')}"
    )

    print(
        "Open Paper Trades: "
        f"{_first(paper_trade_result, ['open_paper_trades'])}"
    )

    print(
        "Paper Trade Profit: "
        f"{_first(paper_trade_result, ['paper_profit'])}"
    )

    print(
        "Total Paper Trades: "
        f"{_first(paper_trade_report, ['total_paper_trades'])}"
    )

    print(
        "Closed Paper Trades: "
        f"{_first(paper_trade_report, ['closed_paper_trades'])}"
    )

    print(
        "Realized Paper Profit: "
        f"{_first(paper_trade_report, ['realized_profit_usd'])}"
    )

    print(
        "Unrealized Paper Profit: "
        f"{_first(paper_trade_report, ['unrealized_profit_usd'])}"
    )

    win_rate = _first(
        paper_trade_report,
        ["win_rate_percent"],
    )

    if win_rate == NOT_AVAILABLE:
        print("Paper Win Rate: N/A")
    else:
        print(f"Paper Win Rate: {win_rate}%")

    # ==================================================================
    # PROFIT MANAGER
    # ==================================================================

    profit_action = _first(
        profit_manager,
        [
            "action",
            "status",
        ],
    )

    profit_message = _first(
        profit_manager,
        [
            "message",
            "reason",
        ],
        default="",
    )

    _section()
    print("PROFIT MANAGER")
    _section()

    print(f"Profit Manager Action: {profit_action}")
    print(f"Profit Message: {profit_message}")

    _footer()