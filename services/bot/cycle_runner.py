import time
import traceback
from typing import Any

from config.settings import SYMBOL, SAVE_SIGNAL_TEXT_LOGS

from models.market_state import BotCycleState

from services.market_data.market_snapshot import get_market_snapshot
from services.market_data.price_service import get_current_price

from services.risk.market_condition_checker import check_market_conditions
from services.risk.advanced_risk_engine import (
    evaluate_advanced_risk,
    apply_advanced_risk_to_ai,
)
from services.risk.slippage_guard import (
    evaluate_slippage_guard,
    apply_slippage_guard_to_ai,
)
from services.risk.news_event_filter import (
    assess_news_event_risk,
    apply_news_filter_to_ai,
)
from services.risk.automatic_economic_calendar import (
    sync_auto_economic_calendar_if_needed,
)
from services.risk.fmp_market_context import (
    build_fmp_market_context,
    apply_fmp_context_to_ai,
    compare_fmp_gold_to_snapshot,
)

from services.analysis.trend_detector import detect_trend
from services.analysis.volatility_detector import detect_volatility
from services.analysis.structure_detector import detect_structure
from services.analysis.trend_confirmation import (
    confirm_trend,
    attach_trend_confirmation,
)
from services.analysis.structure_confirmation import (
    confirm_structure,
    attach_structure_confirmation,
)

from services.decision.decision_engine import make_trade_decision
from services.decision.signal_package_builder import build_signal_package
from services.decision.signal_formatter import format_signal_package_for_ai
from services.decision.decision_quality_filter import (
    apply_decision_quality_filter,
)

from services.ai.ai_brain import run_ai_brain
from services.ai.ai_confirmation_filter import (
    apply_ai_confirmation_filter,
)

from services.execution.execution_gate import evaluate_execution_gate
from services.execution.trade_executor import execute_trade_from_gate
from services.execution.profit_manager import manage_profit_targets
from services.execution.dry_run_trade_plan import (
    create_dry_run_trade_plan,
)
from services.execution.paper_trade_manager import manage_paper_trade
from services.execution.paper_trade_report import (
    build_paper_trade_report,
)

from services.bot.cycle_logger import log_bot_cycle
from services.bot.signal_text_logger import save_signal_text_log
from services.bot.cycle_summary_printer import print_cycle_summary
from services.bot.trade_journal import log_trade_journal_entry
from services.bot.paper_trade_report_logger import (
    log_paper_trade_report,
)
from services.bot.paper_trade_history_exporter import (
    export_paper_trade_history,
)
from services.bot.decision_quality_logger import log_decision_quality
from services.bot.risk_engine_logger import log_risk_engine
from services.bot.news_risk_logger import log_news_risk


# ======================================================================
# GENERAL SAFETY HELPERS
# ======================================================================

def _safe_attach(
    cycle: BotCycleState,
    name: str,
    value: Any,
) -> BotCycleState:
    """
    Attaches an optional runtime field to the cycle.

    Some BotCycleState implementations may not accept additional fields.
    Failure to attach optional metadata must never crash the bot cycle.
    """

    try:
        setattr(cycle, name, value)
    except Exception:
        pass

    return cycle


def _try_log_cycle(cycle: BotCycleState) -> None:
    try:
        log_bot_cycle(cycle)
    except Exception as error:
        print(f"Cycle logging failed: {error}")

    try:
        journal_path = log_trade_journal_entry(cycle)
        print(f"Trade journal saved: {journal_path}")
    except Exception as error:
        print(f"Trade journal logging failed: {error}")


def _try_save_signal_text(
    symbol: str,
    formatted_signal: str,
) -> None:
    if not SAVE_SIGNAL_TEXT_LOGS:
        return

    try:
        save_signal_text_log(
            symbol,
            formatted_signal,
        )
    except Exception as error:
        print(f"Signal text logging failed: {error}")


def _try_print_cycle_summary(
    cycle: BotCycleState,
) -> None:
    try:
        print_cycle_summary(cycle)
    except Exception as error:
        print(f"Cycle summary printing failed: {error}")


def _attach_runtime(
    cycle: BotCycleState,
    start_time: float,
) -> BotCycleState:
    runtime_seconds = round(
        time.perf_counter() - start_time,
        4,
    )

    runtime_ms = round(
        runtime_seconds * 1000,
        2,
    )

    _safe_attach(
        cycle,
        "runtime_seconds",
        runtime_seconds,
    )

    _safe_attach(
        cycle,
        "runtime_ms",
        runtime_ms,
    )

    return cycle


# ======================================================================
# AUTOMATIC CALENDAR SAFETY
# ======================================================================

def _sync_calendar_safely() -> dict[str, Any]:
    try:
        result = sync_auto_economic_calendar_if_needed()

        if isinstance(result, dict):
            return result

        return {
            "success": False,
            "skipped": False,
            "message": (
                "Automatic calendar sync returned an "
                "unexpected result."
            ),
            "added_events": 0,
        }

    except Exception as error:
        return {
            "success": False,
            "skipped": False,
            "message": (
                f"Auto calendar sync failed: {error}"
            ),
            "added_events": 0,
        }


# ======================================================================
# FMP PHASE 37 INTEGRATION
# ======================================================================

def _build_fmp_context_safely(
    snapshot: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Builds the cached FMP context and compares GCUSD with MT5.

    FMP is supporting context only. An FMP service failure must not crash
    the bot or independently approve a trade.
    """

    try:
        fmp_context = build_fmp_market_context(
            force=False
        )

        if not isinstance(fmp_context, dict):
            fmp_context = {
                "success": False,
                "skipped": False,
                "cache_hit": False,
                "calls_used": 0,
                "message": (
                    "FMP market context returned an "
                    "unexpected result."
                ),
            }

    except Exception as error:
        fmp_context = {
            "success": False,
            "skipped": False,
            "cache_hit": False,
            "calls_used": 0,
            "message": (
                f"FMP market context failed: {error}"
            ),
            "gold_quote_success": False,
        }

    try:
        fmp_price_check = compare_fmp_gold_to_snapshot(
            fmp_context,
            snapshot,
        )

        if not isinstance(fmp_price_check, dict):
            fmp_price_check = {
                "success": False,
                "price_confirmed": False,
                "message": (
                    "FMP price comparison returned an "
                    "unexpected result."
                ),
            }

    except Exception as error:
        fmp_price_check = {
            "success": False,
            "price_confirmed": False,
            "message": (
                f"FMP price check failed: {error}"
            ),
        }

    return fmp_context, fmp_price_check


def _apply_fmp_context_safely(
    ai_result: Any,
    fmp_context: dict[str, Any],
    fmp_price_check: dict[str, Any],
) -> Any:
    """
    Adds FMP information to the AI result safely.

    The FMP gold-quote confidence bonus is allowed only when:
    - the FMP quote was successfully loaded; and
    - the FMP price agrees with the MT5 midpoint.

    A price mismatch removes the quote bonus, but it does not directly
    convert, approve, reject, or execute a trade.
    """

    if not isinstance(ai_result, dict):
        return ai_result

    result = dict(ai_result)

    gold_quote_success = bool(
        fmp_context.get(
            "gold_quote_success",
            False,
        )
    )

    price_check_success = bool(
        fmp_price_check.get(
            "success",
            False,
        )
    )

    price_confirmed = bool(
        fmp_price_check.get(
            "price_confirmed",
            False,
        )
    )

    high_risk_news_detected = bool(
        fmp_context.get(
            "high_risk_news_detected",
            False,
        )
    )

    # Preserve the news-risk penalty if Forex News is enabled later,
    # but only grant the gold-quote bonus after price confirmation.
    context_for_ai = dict(fmp_context)

    if not price_confirmed:
        context_for_ai["gold_quote_success"] = False

    usable_context = (
        bool(context_for_ai.get("gold_quote_success"))
        or high_risk_news_detected
    )

    if usable_context:
        try:
            adjusted_result = apply_fmp_context_to_ai(
                result,
                context_for_ai,
            )

            if isinstance(adjusted_result, dict):
                result = adjusted_result

        except Exception as error:
            result["fmp_context_applied"] = False
            result["fmp_context_adjustment"] = 0.0
            result["fmp_context_reason"] = (
                f"FMP context adjustment failed: {error}"
            )

    else:
        result["fmp_context_applied"] = False
        result["fmp_context_adjustment"] = 0.0

        if gold_quote_success and not price_confirmed:
            result["fmp_context_reason"] = (
                "FMP quote loaded, but external price "
                "confirmation was not granted."
            )
        elif fmp_context.get("cache_hit"):
            result["fmp_context_reason"] = (
                "Cached FMP context contained no usable "
                "price confirmation."
            )
        else:
            result["fmp_context_reason"] = (
                "No usable FMP context."
            )

    # Attach explicit Phase 37 fields for summaries and logs.
    result["fmp_context_success"] = bool(
        fmp_context.get("success", False)
    )

    result["fmp_context_skipped"] = bool(
        fmp_context.get("skipped", False)
    )

    result["fmp_cache_hit"] = bool(
        fmp_context.get("cache_hit", False)
    )

    result["fmp_calls_used"] = fmp_context.get(
        "calls_used",
        0,
    )

    result["fmp_estimated_calls_per_day"] = (
        fmp_context.get(
            "estimated_calls_per_day",
            0,
        )
    )

    result["fmp_gold_quote_success"] = (
        gold_quote_success
    )

    result["fmp_price_check_success"] = (
        price_check_success
    )

    result["fmp_price_confirmed"] = (
        price_confirmed
    )

    result["fmp_price_difference_usd"] = (
        fmp_price_check.get(
            "difference_usd"
        )
    )

    result["fmp_price_check_message"] = (
        fmp_price_check.get(
            "message",
            "No FMP price-check message.",
        )
    )

    return result


# ======================================================================
# OPTIONAL LOGGING HELPERS
# ======================================================================

def _log_paper_trade_outputs(
    cycle: BotCycleState,
    symbol: str,
) -> None:
    try:
        paper_trade_report = build_paper_trade_report(
            symbol
        )

        _safe_attach(
            cycle,
            "paper_trade_report",
            paper_trade_report,
        )

        paper_report_path = log_paper_trade_report(
            paper_trade_report
        )

        _safe_attach(
            cycle,
            "paper_trade_report_log_path",
            paper_report_path,
        )

    except Exception as error:
        print(
            "Paper trade report logging failed: "
            f"{error}"
        )

    try:
        paper_history_result = (
            export_paper_trade_history(symbol)
        )

        if isinstance(paper_history_result, dict):
            history_path = paper_history_result.get(
                "file_path"
            )
        else:
            history_path = None

        _safe_attach(
            cycle,
            "paper_trade_history_path",
            history_path,
        )

        print(
            "Paper trade history exported: "
            f"{history_path}"
        )

    except Exception as error:
        print(
            "Paper trade history export failed: "
            f"{error}"
        )


def _log_validation_outputs(
    cycle: BotCycleState,
) -> None:
    try:
        path = log_decision_quality(cycle)

        _safe_attach(
            cycle,
            "decision_quality_log_path",
            path,
        )

        print(f"Decision quality logged: {path}")

    except Exception as error:
        print(
            "Decision quality logging failed: "
            f"{error}"
        )

    try:
        path = log_risk_engine(cycle)

        _safe_attach(
            cycle,
            "risk_engine_log_path",
            path,
        )

        print(f"Risk engine logged: {path}")

    except Exception as error:
        print(
            f"Risk engine logging failed: {error}"
        )

    try:
        path = log_news_risk(cycle)

        _safe_attach(
            cycle,
            "news_risk_log_path",
            path,
        )

        print(f"News risk logged: {path}")

    except Exception as error:
        print(
            f"News risk logging failed: {error}"
        )


# ======================================================================
# COMPLETE BOT CYCLE
# ======================================================================

def run_bot_cycle(
    symbol: str = SYMBOL,
) -> BotCycleState:
    """
    Runs one complete bot cycle.

    Live-trading safety remains controlled by config/settings.py.
    This function does not enable live trading.
    """

    start_time = time.perf_counter()

    try:
        # --------------------------------------------------------------
        # MARKET DATA
        # --------------------------------------------------------------

        snapshot = get_market_snapshot(symbol)
        conditions = check_market_conditions(snapshot)

        # --------------------------------------------------------------
        # MARKET ANALYSIS
        # --------------------------------------------------------------

        trend = detect_trend(snapshot)

        trend_confirmation = confirm_trend(
            trend
        )

        trend = attach_trend_confirmation(
            trend,
            trend_confirmation,
        )

        volatility = detect_volatility(snapshot)

        structure = detect_structure(snapshot)

        structure_confirmation = confirm_structure(
            structure
        )

        structure = attach_structure_confirmation(
            structure,
            structure_confirmation,
        )

        # --------------------------------------------------------------
        # DECISION ENGINE
        # --------------------------------------------------------------

        raw_decision = make_trade_decision(
            snapshot,
            conditions,
            trend,
            volatility,
            structure,
        )

        decision, trade_score = (
            apply_decision_quality_filter(
                conditions=conditions,
                trend=trend,
                volatility=volatility,
                structure=structure,
                decision=raw_decision,
                snapshot=snapshot,
            )
        )

        signal_package = build_signal_package(
            snapshot,
            conditions,
            trend,
            volatility,
            structure,
            decision,
        )

        formatted_signal = (
            format_signal_package_for_ai(
                signal_package
            )
        )

        # --------------------------------------------------------------
        # AI CONFIRMATION
        # --------------------------------------------------------------

        raw_ai_result = run_ai_brain(
            signal_package
        )

        ai_result, ai_quality = (
            apply_ai_confirmation_filter(
                decision=decision,
                ai_result=raw_ai_result,
            )
        )

        # --------------------------------------------------------------
        # ADVANCED RISK ENGINE
        # --------------------------------------------------------------

        advanced_risk = evaluate_advanced_risk(
            symbol
        )

        ai_result = apply_advanced_risk_to_ai(
            ai_result,
            advanced_risk,
        )

        # --------------------------------------------------------------
        # SLIPPAGE CHECK
        # --------------------------------------------------------------

        latest_price = get_current_price(
            symbol
        )

        slippage_guard = evaluate_slippage_guard(
            snapshot=snapshot,
            latest_price_data=latest_price,
        )

        ai_result = apply_slippage_guard_to_ai(
            ai_result=ai_result,
            slippage_result=slippage_guard,
        )

        # --------------------------------------------------------------
        # ECONOMIC CALENDAR AND NEWS RISK
        # --------------------------------------------------------------

        calendar_sync = _sync_calendar_safely()

        news_risk = assess_news_event_risk(
            symbol
        )

        ai_result = apply_news_filter_to_ai(
            ai_result,
            news_risk,
        )

        # --------------------------------------------------------------
        # FMP FREE MARKET CONTEXT — PHASE 37
        # --------------------------------------------------------------

        (
            fmp_context,
            fmp_price_check,
        ) = _build_fmp_context_safely(
            snapshot
        )

        ai_result = _apply_fmp_context_safely(
            ai_result=ai_result,
            fmp_context=fmp_context,
            fmp_price_check=fmp_price_check,
        )

        # --------------------------------------------------------------
        # EXECUTION SAFETY GATE
        # --------------------------------------------------------------

        execution_gate = evaluate_execution_gate(
            signal_package,
            ai_result,
        )

        trade_execution = execute_trade_from_gate(
            signal_package,
            execution_gate,
            ai_result,
        )

        dry_run_plan = create_dry_run_trade_plan(
            signal_package=signal_package,
            ai_result=ai_result,
            execution_gate=execution_gate,
            trade_execution=trade_execution,
        )

        profit_manager = manage_profit_targets(
            symbol
        )

        # --------------------------------------------------------------
        # BUILD SUCCESSFUL CYCLE
        # --------------------------------------------------------------

        cycle = BotCycleState(
            success=True,
            snapshot=snapshot,
            conditions=conditions,
            trend=trend,
            volatility=volatility,
            structure=structure,
            decision=decision,
            signal_package=signal_package,
            formatted_signal=formatted_signal,
            ai_result=ai_result,
            execution_gate=execution_gate,
            trade_execution=trade_execution,
            profit_manager=profit_manager,
            error_message=None,
        )

        cycle = _attach_runtime(
            cycle,
            start_time,
        )

        # --------------------------------------------------------------
        # ATTACH EXTENDED CYCLE DATA
        # --------------------------------------------------------------

        _safe_attach(
            cycle,
            "raw_decision",
            raw_decision,
        )

        _safe_attach(
            cycle,
            "trade_score",
            trade_score,
        )

        _safe_attach(
            cycle,
            "trend_confirmation",
            trend_confirmation,
        )

        _safe_attach(
            cycle,
            "structure_confirmation",
            structure_confirmation,
        )

        _safe_attach(
            cycle,
            "raw_ai_result",
            raw_ai_result,
        )

        _safe_attach(
            cycle,
            "ai_quality",
            ai_quality,
        )

        _safe_attach(
            cycle,
            "advanced_risk",
            advanced_risk,
        )

        _safe_attach(
            cycle,
            "slippage_guard",
            slippage_guard,
        )

        _safe_attach(
            cycle,
            "latest_price",
            latest_price,
        )

        _safe_attach(
            cycle,
            "calendar_sync",
            calendar_sync,
        )

        _safe_attach(
            cycle,
            "news_risk",
            news_risk,
        )

        _safe_attach(
            cycle,
            "fmp_context",
            fmp_context,
        )

        _safe_attach(
            cycle,
            "fmp_price_check",
            fmp_price_check,
        )

        _safe_attach(
            cycle,
            "dry_run_plan",
            dry_run_plan,
        )

        # --------------------------------------------------------------
        # PAPER TRADING
        # --------------------------------------------------------------

        paper_trade_result = manage_paper_trade(
            cycle
        )

        _safe_attach(
            cycle,
            "paper_trade_result",
            paper_trade_result,
        )

        _log_paper_trade_outputs(
            cycle,
            symbol,
        )

        # --------------------------------------------------------------
        # QUALITY, RISK, AND NEWS LOGGING
        # --------------------------------------------------------------

        _log_validation_outputs(cycle)

        # --------------------------------------------------------------
        # FINAL CYCLE OUTPUTS
        # --------------------------------------------------------------

        _try_log_cycle(cycle)

        _try_save_signal_text(
            symbol,
            formatted_signal,
        )

        _try_print_cycle_summary(cycle)

        return cycle

    except Exception as error:
        traceback.print_exc()

        failed_cycle = BotCycleState(
            success=False,
            error_message=str(error),
        )

        failed_cycle = _attach_runtime(
            failed_cycle,
            start_time,
        )

        _safe_attach(
            failed_cycle,
            "symbol",
            symbol,
        )

        _safe_attach(
            failed_cycle,
            "exception_type",
            type(error).__name__,
        )

        _try_log_cycle(failed_cycle)
        _try_print_cycle_summary(failed_cycle)

        return failed_cycle