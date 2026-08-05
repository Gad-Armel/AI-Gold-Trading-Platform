
import json
import os

from collections.abc import Mapping
from typing import Any

from config import settings

from services.execution.paper_trade_report import (
    build_paper_trade_report,
)
from services.risk.advanced_risk_engine import (
    evaluate_advanced_risk,
)


# ======================================================================
# SAFE VALUE HELPERS
# ======================================================================

def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
    minimum: int | None = None,
) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default

    if minimum is not None:
        result = max(
            minimum,
            result,
        )

    return result


def _safe_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "yes",
            "1",
            "enabled",
            "allowed",
            "approved",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "disabled",
            "blocked",
            "rejected",
        }:
            return False

    if value is None:
        return default

    return bool(value)


def _normalize_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    normalized = str(value).strip().upper()

    return normalized or default


def _deduplicate_messages(
    messages: list[Any],
) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for message in messages:
        text = str(message).strip()

        if not text:
            continue

        if text in seen:
            continue

        cleaned.append(text)
        seen.add(text)

    return cleaned


# ======================================================================
# LOG FOLDER HELPERS
# ======================================================================

def _get_base_log_folder() -> str:
    """
    Returns the main logs folder without adding a daily date folder.
    """

    base_log_path = str(
        getattr(
            settings,
            "LOG_FILE_PATH",
            "logs/bot_cycle_log.csv",
        )
    )

    return (
        os.path.dirname(base_log_path)
        or "logs"
    )


def _get_current_log_folder() -> str:
    """
    Returns the log folder currently used by the bot.
    """

    base_folder = _get_base_log_folder()

    if _safe_bool(
        getattr(
            settings,
            "USE_DAILY_LOG_FOLDERS",
            False,
        ),
        default=False,
    ):
        from datetime import datetime

        date_format = str(
            getattr(
                settings,
                "LOG_DATE_FORMAT",
                "%Y-%m-%d",
            )
        )

        date_folder = datetime.now().strftime(
            date_format
        )

        return os.path.join(
            base_folder,
            date_folder,
        )

    return base_folder


def _find_files(
    file_name: str,
) -> list[str]:
    """
    Searches the complete log tree.

    This allows readiness evidence to be found across multiple
    dated paper-trading folders.
    """

    base_folder = _get_base_log_folder()
    matches: list[str] = []

    if not os.path.exists(base_folder):
        return matches

    for root, _, files in os.walk(
        base_folder
    ):
        if file_name in files:
            matches.append(
                os.path.join(
                    root,
                    file_name,
                )
            )

    matches.sort()

    return matches


def _find_file(
    file_name: str,
) -> tuple[bool, str | None]:
    matches = _find_files(
        file_name
    )

    if matches:
        return True, matches[-1]

    expected_path = os.path.join(
        _get_current_log_folder(),
        file_name,
    )

    return False, expected_path


# ======================================================================
# PAPER-TRADE HISTORY AGGREGATION
# ======================================================================

def _load_trade_file(
    file_path: str,
) -> list[dict[str, Any]]:
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, list):
            return []

        return [
            trade
            for trade in data
            if isinstance(trade, dict)
        ]

    except Exception:
        return []


def _trade_identity(
    trade: dict[str, Any],
) -> str:
    """
    Creates a stable identity so the same trade is not counted twice.
    """

    trade_id = str(
        trade.get("id")
        or ""
    ).strip()

    if trade_id:
        return trade_id

    return "|".join(
        [
            str(
                trade.get(
                    "symbol",
                    "",
                )
            ),
            str(
                trade.get(
                    "direction",
                    "",
                )
            ),
            str(
                trade.get(
                    "opened_at",
                    "",
                )
            ),
            str(
                trade.get(
                    "entry_price",
                    "",
                )
            ),
            str(
                trade.get(
                    "magic_number",
                    "",
                )
            ),
        ]
    )


def _collect_paper_trades(
    symbol: str,
) -> dict[str, Any]:
    """
    Collects paper trades from every paper_trades.json file below
    the main logs folder.

    This prevents live-readiness evidence from resetting whenever
    a new daily log folder is created.
    """

    file_paths = _find_files(
        "paper_trades.json"
    )

    expected_magic_number = getattr(
        settings,
        "MAGIC_NUMBER",
        None,
    )

    unique_trades: dict[
        str,
        dict[str, Any],
    ] = {}

    unreadable_files: list[str] = []

    for file_path in file_paths:
        trades = _load_trade_file(
            file_path
        )

        if not trades:
            try:
                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                ) as file:
                    raw_data = json.load(file)

                if raw_data != []:
                    unreadable_files.append(
                        file_path
                    )

            except Exception:
                unreadable_files.append(
                    file_path
                )

        for trade in trades:
            trade_symbol = _normalize_text(
                trade.get(
                    "symbol",
                    "",
                )
            )

            if trade_symbol != symbol:
                continue

            if (
                expected_magic_number is not None
                and trade.get(
                    "magic_number"
                )
                != expected_magic_number
            ):
                continue

            identity = _trade_identity(
                trade
            )

            if identity:
                unique_trades[identity] = trade

    all_trades = list(
        unique_trades.values()
    )

    closed_trades = [
        trade
        for trade in all_trades
        if _normalize_text(
            trade.get(
                "status",
                "",
            )
        )
        == "CLOSED"
    ]

    open_trades = [
        trade
        for trade in all_trades
        if _normalize_text(
            trade.get(
                "status",
                "",
            )
        )
        == "OPEN"
    ]

    realized_profit = sum(
        _safe_float(
            trade.get(
                "final_profit_usd",
                0.0,
            )
        )
        for trade in closed_trades
    )

    unrealized_profit = sum(
        _safe_float(
            trade.get(
                "unrealized_profit_usd",
                0.0,
            )
        )
        for trade in open_trades
    )

    winning_trades = sum(
        1
        for trade in closed_trades
        if _safe_float(
            trade.get(
                "final_profit_usd",
                0.0,
            )
        )
        > 0
    )

    losing_trades = sum(
        1
        for trade in closed_trades
        if _safe_float(
            trade.get(
                "final_profit_usd",
                0.0,
            )
        )
        < 0
    )

    breakeven_trades = (
        len(closed_trades)
        - winning_trades
        - losing_trades
    )

    if closed_trades:
        win_rate = (
            winning_trades
            / len(closed_trades)
        ) * 100.0
    else:
        win_rate = 0.0

    return {
        "files_found": len(
            file_paths
        ),
        "file_paths": file_paths,
        "unreadable_files": unreadable_files,
        "total_paper_trades": len(
            all_trades
        ),
        "closed_paper_trades": len(
            closed_trades
        ),
        "open_paper_trades": len(
            open_trades
        ),
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "breakeven_trades": breakeven_trades,
        "win_rate_percent": round(
            win_rate,
            2,
        ),
        "realized_profit_usd": round(
            realized_profit,
            2,
        ),
        "unrealized_profit_usd": round(
            unrealized_profit,
            2,
        ),
    }


# ======================================================================
# SAFE REPORT AND RISK EXECUTION
# ======================================================================

def _build_report_safely(
    symbol: str,
) -> tuple[dict[str, Any], str | None]:
    try:
        result = build_paper_trade_report(
            symbol
        )

        if isinstance(
            result,
            Mapping,
        ):
            return dict(result), None

        return {}, (
            "Paper-trade report builder returned "
            "an invalid result."
        )

    except Exception as error:
        return {}, (
            "Paper-trade report generation failed: "
            f"{error}"
        )


def _evaluate_risk_safely(
    symbol: str,
) -> tuple[dict[str, Any], str | None]:
    try:
        result = evaluate_advanced_risk(
            symbol
        )

        if isinstance(
            result,
            Mapping,
        ):
            return dict(result), None

        return {}, (
            "Advanced risk engine returned "
            "an invalid result."
        )

    except Exception as error:
        return {}, (
            "Advanced risk evaluation failed: "
            f"{error}"
        )


# ======================================================================
# SETTINGS
# ======================================================================

def _minimum_closed_trades() -> int:
    return _safe_int(
        getattr(
            settings,
            "MIN_CLOSED_PAPER_TRADES_FOR_LIVE",
            20,
        ),
        default=20,
        minimum=1,
    )


def _minimum_win_rate() -> float:
    return max(
        0.0,
        min(
            100.0,
            _safe_float(
                getattr(
                    settings,
                    "MIN_PAPER_WIN_RATE_FOR_LIVE",
                    55.0,
                ),
                default=55.0,
            ),
        ),
    )


def _minimum_realized_profit() -> float:
    return _safe_float(
        getattr(
            settings,
            "MIN_PAPER_REALIZED_PROFIT_FOR_LIVE",
            0.0,
        ),
        default=0.0,
    )


def _required_files() -> list[str]:
    configured = getattr(
        settings,
        "LIVE_READINESS_REQUIRED_FILES",
        None,
    )

    if isinstance(
        configured,
        (list, tuple, set),
    ):
        return [
            str(file_name)
            for file_name in configured
            if str(file_name).strip()
        ]

    return [
        "bot_cycle_log.csv",
        "trade_journal.csv",
        "decision_quality_log.csv",
        "risk_engine_log.csv",
        "paper_trade_report.csv",
        "paper_trade_history.csv",
        "paper_trades.json",
    ]


# ======================================================================
# LIVE-READINESS CHECKER
# ======================================================================

def check_live_readiness(
    symbol: str | None = None,
) -> dict[str, Any]:
    """
    Evaluates whether the system is ready for live-trading review.

    This function:
    - does not enable live trading;
    - does not change settings;
    - does not place an order;
    - aggregates paper trades across all dated log folders;
    - fails closed when required evidence cannot be verified.

    The execution gate may call this function after live trading has
    been enabled. Therefore ENABLE_LIVE_TRADING=True is not itself a
    readiness blocker.
    """

    clean_symbol = _normalize_text(
        symbol
        or getattr(
            settings,
            "SYMBOL",
            "XAUUSD",
        ),
        default="XAUUSD",
    )

    checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []

    # ==================================================================
    # PAPER-TRADE EVIDENCE
    # ==================================================================

    paper_report, report_error = (
        _build_report_safely(
            clean_symbol
        )
    )

    aggregate_report = (
        _collect_paper_trades(
            clean_symbol
        )
    )

    if report_error:
        warnings.append(
            report_error
        )

    if aggregate_report[
        "files_found"
    ] > 0:
        closed_trades = _safe_int(
            aggregate_report.get(
                "closed_paper_trades",
                0,
            )
        )

        win_rate = _safe_float(
            aggregate_report.get(
                "win_rate_percent",
                0.0,
            )
        )

        realized_profit = _safe_float(
            aggregate_report.get(
                "realized_profit_usd",
                0.0,
            )
        )

        paper_statistics_source = (
            "AGGREGATED_PAPER_TRADES"
        )

        checks.append(
            "Paper-trade statistics were aggregated "
            f"from {aggregate_report['files_found']} "
            "paper-trade file(s)."
        )

    else:
        closed_trades = _safe_int(
            paper_report.get(
                "closed_paper_trades",
                0,
            )
        )

        win_rate = _safe_float(
            paper_report.get(
                "win_rate_percent",
                0.0,
            )
        )

        realized_profit = _safe_float(
            paper_report.get(
                "realized_profit_usd",
                0.0,
            )
        )

        paper_statistics_source = (
            "CURRENT_PAPER_REPORT"
        )

        warnings.append(
            "No paper_trades.json files were found "
            "for historical aggregation."
        )

    if aggregate_report[
        "unreadable_files"
    ]:
        blockers.append(
            "One or more paper-trade history files "
            "could not be read."
        )

    # ==================================================================
    # ADVANCED RISK
    # ==================================================================

    advanced_risk, risk_error = (
        _evaluate_risk_safely(
            clean_symbol
        )
    )

    if risk_error:
        blockers.append(
            risk_error
        )

    advanced_risk_allowed = _safe_bool(
        advanced_risk.get(
            "allowed",
            False,
        ),
        default=False,
    )

    # ==================================================================
    # CORE SAFETY SETTINGS
    # ==================================================================

    live_trading_enabled = _safe_bool(
        getattr(
            settings,
            "ENABLE_LIVE_TRADING",
            False,
        ),
        default=False,
    )

    emergency_stop = _safe_bool(
        getattr(
            settings,
            "EMERGENCY_STOP",
            False,
        ),
        default=False,
    )

    live_confirmation = str(
        getattr(
            settings,
            "LIVE_TRADING_CONFIRMATION",
            "",
        )
        or ""
    )

    required_confirmation = str(
        getattr(
            settings,
            "REQUIRED_LIVE_TRADING_CONFIRMATION",
            "I_ACCEPT_LIVE_TRADING_RISK",
        )
        or ""
    )

    if live_trading_enabled:
        checks.append(
            "Live trading is enabled. Readiness is being "
            "evaluated for active execution."
        )

        if (
            not required_confirmation
            or live_confirmation
            != required_confirmation
        ):
            blockers.append(
                "Live trading is enabled, but the exact "
                "live-risk confirmation is missing or invalid."
            )
        else:
            checks.append(
                "Exact live-trading confirmation is present."
            )

    else:
        checks.append(
            "Live trading remains disabled during readiness review."
        )

        if live_confirmation:
            warnings.append(
                "LIVE_TRADING_CONFIRMATION is filled while "
                "live trading is disabled. It should remain empty "
                "until final approval."
            )
        else:
            checks.append(
                "Live-trading confirmation is empty."
            )

    if emergency_stop:
        blockers.append(
            "EMERGENCY_STOP is active."
        )
    else:
        checks.append(
            "Emergency stop is clear."
        )

    # ==================================================================
    # PAPER-TRADE REQUIREMENTS
    # ==================================================================

    minimum_closed_trades = (
        _minimum_closed_trades()
    )

    minimum_win_rate = (
        _minimum_win_rate()
    )

    minimum_realized_profit = (
        _minimum_realized_profit()
    )

    if (
        closed_trades
        >= minimum_closed_trades
    ):
        checks.append(
            "Closed paper-trade requirement passed: "
            f"{closed_trades}/{minimum_closed_trades}."
        )
    else:
        blockers.append(
            "Not enough closed paper trades: "
            f"{closed_trades}/{minimum_closed_trades}."
        )

    if win_rate >= minimum_win_rate:
        checks.append(
            "Paper win-rate requirement passed: "
            f"{win_rate:.2f}% >= "
            f"{minimum_win_rate:.2f}%."
        )
    else:
        blockers.append(
            "Paper win rate is below the requirement: "
            f"{win_rate:.2f}% < "
            f"{minimum_win_rate:.2f}%."
        )

    require_positive_profit = _safe_bool(
        getattr(
            settings,
            "REQUIRE_POSITIVE_PAPER_PROFIT_FOR_LIVE",
            True,
        ),
        default=True,
    )

    if require_positive_profit:
        required_profit = max(
            0.0,
            minimum_realized_profit,
        )

        if realized_profit > required_profit:
            checks.append(
                "Paper realized profit requirement passed: "
                f"${realized_profit:.2f} > "
                f"${required_profit:.2f}."
            )
        else:
            blockers.append(
                "Paper realized profit is not high enough: "
                f"${realized_profit:.2f}. It must be greater "
                f"than ${required_profit:.2f}."
            )

    elif (
        realized_profit
        >= minimum_realized_profit
    ):
        checks.append(
            "Paper realized profit requirement passed: "
            f"${realized_profit:.2f} >= "
            f"${minimum_realized_profit:.2f}."
        )

    else:
        blockers.append(
            "Paper realized profit is below the configured "
            f"minimum: ${realized_profit:.2f} < "
            f"${minimum_realized_profit:.2f}."
        )

    # ==================================================================
    # RISK ENGINE REQUIREMENTS
    # ==================================================================

    risk_engine_required = _safe_bool(
        getattr(
            settings,
            "REQUIRE_RISK_ENGINE_FOR_LIVE",
            True,
        ),
        default=True,
    )

    risk_engine_enabled = _safe_bool(
        getattr(
            settings,
            "ENABLE_ADVANCED_RISK_ENGINE",
            False,
        ),
        default=False,
    )

    if risk_engine_required:
        if risk_engine_enabled:
            checks.append(
                "Advanced risk engine is enabled."
            )
        else:
            blockers.append(
                "Advanced risk engine is required but disabled."
            )

        if advanced_risk_allowed:
            checks.append(
                "Advanced risk engine currently allows trading."
            )
        else:
            blockers.append(
                "Advanced risk engine currently blocks trading."
            )

    else:
        if risk_engine_enabled:
            checks.append(
                "Advanced risk engine is enabled, although "
                "it is not mandatory for readiness."
            )

        if not advanced_risk_allowed:
            warnings.append(
                "Advanced risk engine currently blocks trading."
            )

    # ==================================================================
    # REQUIRED AUDIT FILES
    # ==================================================================

    block_on_missing_files = _safe_bool(
        getattr(
            settings,
            "BLOCK_LIVE_READINESS_ON_MISSING_FILES",
            True,
        ),
        default=True,
    )

    required_file_results: list[
        dict[str, Any]
    ] = []

    for file_name in _required_files():
        exists, path = _find_file(
            file_name
        )

        required_file_results.append(
            {
                "file_name": file_name,
                "exists": exists,
                "path": path,
            }
        )

        if exists:
            checks.append(
                f"Found readiness file: {file_name}."
            )

        elif block_on_missing_files:
            blockers.append(
                "Missing required readiness file: "
                f"{file_name}. Expected near: {path}"
            )

        else:
            warnings.append(
                "Missing readiness file: "
                f"{file_name}. Expected near: {path}"
            )

    # ==================================================================
    # FINAL RESULT
    # ==================================================================

    checks = _deduplicate_messages(
        checks
    )

    warnings = _deduplicate_messages(
        warnings
    )

    blockers = _deduplicate_messages(
        blockers
    )

    ready_for_review = (
        len(blockers) == 0
    )

    return {
        "symbol": clean_symbol,
        "ready_for_review": ready_for_review,
        "status": (
            "READY_FOR_REVIEW"
            if ready_for_review
            else "NOT_READY"
        ),
        "live_trading_enabled": (
            live_trading_enabled
        ),
        "emergency_stop_active": (
            emergency_stop
        ),
        "closed_paper_trades": (
            closed_trades
        ),
        "minimum_closed_paper_trades": (
            minimum_closed_trades
        ),
        "paper_win_rate": round(
            win_rate,
            2,
        ),
        "minimum_paper_win_rate": (
            minimum_win_rate
        ),
        "paper_realized_profit": round(
            realized_profit,
            2,
        ),
        "minimum_paper_realized_profit": (
            minimum_realized_profit
        ),
        "paper_statistics_source": (
            paper_statistics_source
        ),
        "aggregate_paper_report": (
            aggregate_report
        ),
        "current_paper_report": (
            paper_report
        ),
        "advanced_risk_allowed": (
            advanced_risk_allowed
        ),
        "advanced_risk_result": (
            advanced_risk
        ),
        "required_file_results": (
            required_file_results
        ),
        "checks": checks,
        "warnings": warnings,
        "blockers": blockers,
    }

