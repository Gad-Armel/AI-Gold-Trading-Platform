import importlib
import json
import os
from datetime import datetime
from typing import Any

from config import settings
from services.bot.config_validator import validate_config
from services.bot.live_readiness_checker import check_live_readiness
from services.execution.paper_trade_report import build_paper_trade_report
from services.risk.advanced_risk_engine import evaluate_advanced_risk


REPORT_WIDTH = 70


REQUIRED_MODULES = [
    "config.settings",

    "services.execution.mt5_connector",
    "services.execution.order_manager",
    "services.execution.execution_gate",
    "services.execution.trade_executor",
    "services.execution.profit_manager",
    "services.execution.position_limit_checker",
    "services.execution.trade_direction_validator",
    "services.execution.dry_run_trade_plan",
    "services.execution.paper_trade_manager",
    "services.execution.paper_trade_report",
    "services.execution.paper_trade_reset",

    "services.market_data.price_service",
    "services.market_data.market_watcher",
    "services.market_data.candle_service",
    "services.market_data.timeframe_service",
    "services.market_data.market_snapshot",
    "services.market_data.session_service",

    "services.risk.spread_checker",
    "services.risk.market_condition_checker",
    "services.risk.bad_market_filter",
    "services.risk.volatility_risk_filter",
    "services.risk.advanced_risk_engine",
    "services.risk.slippage_guard",
    "services.risk.news_event_filter",
    "services.risk.economic_event_manager",
    "services.risk.automatic_economic_calendar",
    "services.risk.fmp_market_context",

    "services.analysis.trend_detector",
    "services.analysis.volatility_detector",
    "services.analysis.structure_detector",
    "services.analysis.trend_confirmation",
    "services.analysis.structure_confirmation",

    "services.decision.decision_engine",
    "services.decision.signal_package_builder",
    "services.decision.signal_formatter",
    "services.decision.trade_score_calculator",
    "services.decision.decision_quality_filter",

    "services.ai.ai_brain",
    "services.ai.ai_confirmation_filter",

    "services.bot.cycle_runner",
    "services.bot.loop_runner",
    "services.bot.cycle_logger",
    "services.bot.signal_text_logger",
    "services.bot.cycle_summary_printer",
    "services.bot.log_path_manager",
    "services.bot.startup_report",
    "services.bot.emergency_stop",
    "services.bot.config_validator",
    "services.bot.health_checker",
    "services.bot.safe_mode_checker",
    "services.bot.trade_journal",
    "services.bot.paper_trade_report_logger",
    "services.bot.paper_trade_history_exporter",
    "services.bot.decision_quality_logger",
    "services.bot.risk_engine_logger",
    "services.bot.live_readiness_checker",
    "services.bot.forward_validation_logger",
    "services.bot.decision_tuning_analyzer",
    "services.bot.news_risk_logger",
    "services.bot.validation_command_center",
    "services.bot.test_suite_runner",
    "services.bot.daily_review_report",
    "services.bot.system_auditor",

    "dashboard.paper_trade_dashboard",
]


REQUIRED_FUNCTIONS = {
    "services.execution.mt5_connector": [
        "connect_mt5",
        "disconnect_mt5",
        "get_account_info",
        "get_open_positions",
    ],
    "services.market_data.price_service": [
        "get_current_price",
    ],
    "services.execution.order_manager": [
        "open_buy",
        "open_sell",
        "close_position",
    ],
    "services.market_data.market_watcher": [
        "watch_market",
    ],
    "services.market_data.candle_service": [
        "get_candles",
    ],
    "services.market_data.timeframe_service": [
        "TIMEFRAMES",
        "get_timeframe",
    ],
    "services.market_data.session_service": [
        "detect_market_session",
    ],
    "services.risk.spread_checker": [
        "is_spread_safe",
    ],
    "services.risk.market_condition_checker": [
        "check_market_conditions",
    ],
    "services.analysis.trend_detector": [
        "detect_trend",
    ],
    "services.analysis.volatility_detector": [
        "detect_volatility",
    ],
    "services.analysis.structure_detector": [
        "detect_structure",
    ],
    "services.decision.decision_engine": [
        "make_trade_decision",
    ],
    "services.decision.signal_package_builder": [
        "build_signal_package",
    ],
    "services.decision.signal_formatter": [
        "format_signal_package_for_ai",
    ],
    "services.ai.ai_brain": [
        "run_ai_brain",
    ],
    "services.execution.execution_gate": [
        "evaluate_execution_gate",
    ],
    "services.execution.trade_executor": [
        "execute_trade_from_gate",
    ],
    "services.execution.profit_manager": [
        "manage_profit_targets",
    ],
    "services.bot.cycle_runner": [
        "run_bot_cycle",
    ],
    "services.bot.loop_runner": [
        "run_bot_loop",
    ],
    "services.risk.news_event_filter": [
        "assess_news_event_risk",
        "apply_news_filter_to_ai",
    ],
    "services.risk.fmp_market_context": [
        "fetch_gold_quote",
        "fetch_forex_news",
        "build_fmp_market_context",
        "apply_fmp_context_to_ai",
        "compare_fmp_gold_to_snapshot",
    ],
    "services.risk.automatic_economic_calendar": [
        "sync_auto_economic_calendar",
        "sync_auto_economic_calendar_if_needed",
    ],
    "services.risk.economic_event_manager": [
        "load_events",
        "save_events",
        "add_event",
        "clear_events",
        "list_events",
    ],
    "services.bot.news_risk_logger": [
        "log_news_risk",
    ],
    "services.bot.system_auditor": [
        "run_system_audit",
        "print_system_audit_report",
    ],
}


REQUIRED_ROOT_FILES = [
    "main.py",
    "run_loop.py",
    "requirements.txt",
    "run_system_audit.py",
    "run_paper_dashboard.py",
    "run_live_readiness_check.py",
    "run_platform_status_report.py",
    "test_paper_trade_system.py",
    "test_advanced_risk_engine.py",
    "manage_news_events.py",
    "test_news_event_filter.py",
    "run_decision_tuning_report.py",
    "run_forward_validation.py",
    "run_validation_command_center.py",
    "run_all_tests.py",
    "test_live_gate_protection.py",
    "run_daily_review.py",
    "OPERATING_GUIDE.md",
    "run_auto_calendar_update.py",
    "test_auto_calendar_sync.py",
    "test_fmp_free_access.py",
]


REQUIRED_FOLDERS = [
    "config",
    "models",
    "services",
    "services/ai",
    "services/analysis",
    "services/bot",
    "services/decision",
    "services/execution",
    "services/market_data",
    "services/risk",
    "dashboard",
    "logs",
    "tests",
    "docs",
]


REQUIRED_LOG_FILES = [
    "bot_cycle_log.csv",
    "trade_journal.csv",
    "decision_quality_log.csv",
    "risk_engine_log.csv",
    "paper_trades.json",
    "paper_trade_report.csv",
    "paper_trade_history.csv",
    "paper_trade_dashboard.html",
    "news_risk_log.csv",
    "forward_validation_log.csv",
    "decision_tuning_report.txt",
    "test_suite_report.txt",
    "daily_review_report.txt",
]


PHASE_37_SETTINGS = [
    "ENABLE_FMP_MARKET_CONTEXT",
    "ENABLE_FMP_FOREX_NEWS",
    "FMP_MARKET_CONTEXT_REFRESH_HOURS",
    "FMP_MARKET_CONTEXT_TIMEOUT_SECONDS",
    "FMP_MARKET_CONTEXT_FILE",
    "FMP_GOLD_SYMBOL",
    "FMP_PRICE_CONFIRMATION_MAX_DIFF_USD",
    "FMP_CONTEXT_CONFIDENCE_BONUS",
    "FMP_CONTEXT_CONFIDENCE_PENALTY",
    "FMP_HIGH_RISK_NEWS_KEYWORDS",
]


def _get_log_folder() -> str:
    base_log_path = getattr(
        settings,
        "LOG_FILE_PATH",
        "logs/bot_cycle_log.csv",
    )
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(
            settings,
            "LOG_DATE_FORMAT",
            "%Y-%m-%d",
        )
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(
            base_log_folder,
            today_folder,
        )

    return base_log_folder


def _check_imports() -> tuple[list[str], list[dict[str, str]]]:
    passed: list[str] = []
    failed: list[dict[str, str]] = []

    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
            passed.append(module_name)
        except Exception as error:
            failed.append(
                {
                    "module": module_name,
                    "error": str(error),
                }
            )

    return passed, failed


def _check_functions() -> tuple[list[str], list[dict[str, str]]]:
    passed: list[str] = []
    failed: list[dict[str, str]] = []

    for module_name, function_names in REQUIRED_FUNCTIONS.items():
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            failed.append(
                {
                    "module": module_name,
                    "function": "*",
                    "error": f"Module import failed: {error}",
                }
            )
            continue

        for function_name in function_names:
            if hasattr(module, function_name):
                passed.append(
                    f"{module_name}.{function_name}"
                )
            else:
                failed.append(
                    {
                        "module": module_name,
                        "function": function_name,
                        "error": "Missing function or variable.",
                    }
                )

    return passed, failed


def _check_root_files() -> tuple[list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []

    for file_path in REQUIRED_ROOT_FILES:
        if os.path.isfile(file_path):
            passed.append(file_path)
        else:
            failed.append(file_path)

    return passed, failed


def _check_folders() -> tuple[list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []

    for folder_path in REQUIRED_FOLDERS:
        if os.path.isdir(folder_path):
            passed.append(folder_path)
        else:
            failed.append(folder_path)

    return passed, failed


def _check_log_files() -> tuple[str, list[str], list[str]]:
    log_folder = _get_log_folder()
    passed: list[str] = []
    failed: list[str] = []

    for file_name in REQUIRED_LOG_FILES:
        path = os.path.join(log_folder, file_name)

        if os.path.isfile(path):
            passed.append(path)
        else:
            failed.append(path)

    return log_folder, passed, failed


def _read_json_file(file_path: str) -> tuple[dict[str, Any], str | None]:
    if not os.path.isfile(file_path):
        return {}, "File does not exist."

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as error:
        return {}, str(error)

    if not isinstance(data, dict):
        return {}, "JSON root must be an object."

    return data, None


def _check_phase_37() -> dict[str, Any]:
    """
    Audits Phase 37 without making a network request.

    The audit reads settings and the existing cache only, preserving
    the configured FMP API-call budget.
    """

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    missing_settings = [
        name
        for name in PHASE_37_SETTINGS
        if not hasattr(settings, name)
    ]

    if missing_settings:
        for name in missing_settings:
            errors.append(
                f"Missing Phase 37 setting: {name}"
            )
    else:
        checks.append("All Phase 37 settings are present.")

    enabled = bool(
        getattr(settings, "ENABLE_FMP_MARKET_CONTEXT", False)
    )
    forex_news_enabled = bool(
        getattr(settings, "ENABLE_FMP_FOREX_NEWS", False)
    )
    refresh_hours = getattr(
        settings,
        "FMP_MARKET_CONTEXT_REFRESH_HOURS",
        None,
    )
    gold_symbol = str(
        getattr(settings, "FMP_GOLD_SYMBOL", "") or ""
    ).strip().upper()
    cache_file = str(
        getattr(
            settings,
            "FMP_MARKET_CONTEXT_FILE",
            "data/fmp_market_context.json",
        )
    )

    settings_key = str(
        getattr(settings, "FMP_API_KEY", "") or ""
    ).strip()
    environment_key = str(
        os.getenv("FMP_API_KEY", "") or ""
    ).strip()
    api_key_available = bool(settings_key or environment_key)

    if enabled:
        checks.append("FMP market context is enabled.")
    else:
        warnings.append("FMP market context is disabled.")

    if forex_news_enabled:
        warnings.append(
            "FMP Forex News is enabled. Phase 37 expects it to remain "
            "disabled because the endpoint may require paid access."
        )
    else:
        checks.append(
            "FMP Forex News is disabled. Only the GCUSD quote is used."
        )

    if isinstance(refresh_hours, int) and not isinstance(
        refresh_hours,
        bool,
    ) and refresh_hours > 0:
        calls_per_refresh = 2 if forex_news_enabled else 1
        estimated_calls_per_day = (
            24 / refresh_hours
        ) * calls_per_refresh
        checks.append(
            "Configured FMP market-context calls/day: "
            f"{estimated_calls_per_day:.1f}"
        )
    else:
        estimated_calls_per_day = None
        errors.append(
            "FMP_MARKET_CONTEXT_REFRESH_HOURS must be a positive integer."
        )

    if gold_symbol == "GCUSD":
        checks.append("FMP gold symbol is GCUSD.")
    elif gold_symbol:
        warnings.append(
            f"FMP gold symbol is {gold_symbol}; Phase 37 was tested "
            "with GCUSD."
        )
    else:
        errors.append("FMP_GOLD_SYMBOL is empty.")

    if api_key_available:
        checks.append("FMP API key is available.")
    elif enabled:
        warnings.append(
            "FMP market context is enabled, but no FMP API key was found."
        )

    cache_data, cache_error = _read_json_file(cache_file)

    cache_exists = cache_error is None
    cache_summary: dict[str, Any] = {
        "file_path": cache_file,
        "exists": cache_exists,
        "error": cache_error,
        "success": None,
        "last_refresh": None,
        "gold_quote_success": None,
        "calls_used_when_created": None,
        "estimated_calls_per_day": None,
        "forex_news_enabled": None,
    }

    if cache_exists:
        cache_summary.update(
            {
                "success": cache_data.get("success"),
                "last_refresh": cache_data.get("last_refresh"),
                "gold_quote_success": cache_data.get(
                    "gold_quote_success"
                ),
                "calls_used_when_created": cache_data.get(
                    "calls_used"
                ),
                "estimated_calls_per_day": cache_data.get(
                    "estimated_calls_per_day"
                ),
                "forex_news_enabled": cache_data.get(
                    "forex_news_enabled"
                ),
            }
        )
        checks.append("FMP market-context cache is readable.")

        if cache_data.get("forex_news_enabled") is True:
            warnings.append(
                "The existing FMP cache was created while Forex News "
                "was enabled. A future refresh will replace it."
            )
    else:
        warnings.append(
            "FMP market-context cache is missing or unreadable. "
            "It will be created on the next successful refresh."
        )

    return {
        "passed": not errors,
        "enabled": enabled,
        "forex_news_enabled": forex_news_enabled,
        "refresh_hours": refresh_hours,
        "configured_estimated_calls_per_day": estimated_calls_per_day,
        "gold_symbol": gold_symbol,
        "api_key_available": api_key_available,
        "cache": cache_summary,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def run_system_audit() -> dict[str, Any]:
    config_result = validate_config()

    imported_modules, import_failures = _check_imports()
    passed_functions, failed_functions = _check_functions()
    passed_files, failed_files = _check_root_files()
    passed_folders, failed_folders = _check_folders()
    log_folder, passed_logs, failed_logs = _check_log_files()
    phase_37 = _check_phase_37()

    symbol = getattr(settings, "SYMBOL", "XAUUSD")

    try:
        paper_report = build_paper_trade_report(symbol)
    except Exception as error:
        paper_report = {
            "error": str(error),
        }

    try:
        advanced_risk = evaluate_advanced_risk(symbol)
    except Exception as error:
        advanced_risk = {
            "error": str(error),
            "allowed": False,
        }

    try:
        live_readiness = check_live_readiness(symbol)
    except Exception as error:
        live_readiness = {
            "error": str(error),
            "ready_for_review": False,
        }

    critical_failures: list[str] = []

    if not config_result.get("valid", False):
        critical_failures.append("Config validation failed.")

    if import_failures:
        critical_failures.append(
            "One or more required modules failed to import."
        )

    if failed_functions:
        critical_failures.append(
            "One or more required functions are missing."
        )

    if failed_folders:
        critical_failures.append(
            "One or more required folders are missing."
        )

    if failed_files:
        critical_failures.append(
            "One or more root scripts/files are missing."
        )

    if not phase_37.get("passed", False):
        critical_failures.append(
            "Phase 37 configuration audit failed."
        )

    audit_passed = not critical_failures

    return {
        "audit_passed": audit_passed,
        "generated_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "symbol": symbol,
        "safe_mode": not getattr(
            settings,
            "ENABLE_LIVE_TRADING",
            False,
        ),
        "config": config_result,

        "imported_modules_count": len(imported_modules),
        "import_failures": import_failures,

        "passed_functions_count": len(passed_functions),
        "failed_functions": failed_functions,

        "passed_root_files": passed_files,
        "failed_root_files": failed_files,

        "passed_folders": passed_folders,
        "failed_folders": failed_folders,

        "log_folder": log_folder,
        "passed_logs": passed_logs,
        "failed_logs": failed_logs,

        "phase_37": phase_37,

        "paper_report": paper_report,
        "advanced_risk": advanced_risk,
        "live_readiness": live_readiness,
        "critical_failures": critical_failures,
    }


def print_system_audit_report(
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if result is None:
        result = run_system_audit()

    print("")
    print("=" * REPORT_WIDTH)
    print("FULL SYSTEM AUDIT REPORT")
    print("=" * REPORT_WIDTH)

    print(f"Generated At: {result['generated_at']}")
    print(f"Symbol: {result['symbol']}")
    print(f"Audit Passed: {result['audit_passed']}")
    print(
        f"Safe Mode: "
        f"{'YES' if result['safe_mode'] else 'NO'}"
    )

    print("-" * REPORT_WIDTH)
    print("CONFIG")

    config = result["config"]
    print(f"Config Valid: {config.get('valid')}")
    print(
        f"Settings Checked: "
        f"{config.get('settings_checked')}"
    )

    if config.get("errors"):
        for error in config["errors"]:
            print(f"[CONFIG ERROR] {error}")
    else:
        print("No config errors.")

    if config.get("warnings"):
        for warning in config["warnings"]:
            print(f"[CONFIG WARNING] {warning}")
    else:
        print("No config warnings.")

    print("-" * REPORT_WIDTH)
    print("IMPORT CHECK")
    print(
        f"Imported Modules: "
        f"{result['imported_modules_count']}"
    )

    if result["import_failures"]:
        for failure in result["import_failures"]:
            print(
                f"[IMPORT ERROR] {failure['module']} | "
                f"{failure['error']}"
            )
    else:
        print("All required modules imported.")

    print("-" * REPORT_WIDTH)
    print("FUNCTION CHECK")
    print(
        f"Passed Functions: "
        f"{result['passed_functions_count']}"
    )

    if result["failed_functions"]:
        for failure in result["failed_functions"]:
            print(
                f"[FUNCTION ERROR] "
                f"{failure['module']}."
                f"{failure['function']} | "
                f"{failure['error']}"
            )
    else:
        print("All required functions found.")

    print("-" * REPORT_WIDTH)
    print("ROOT FILE CHECK")

    if result["failed_root_files"]:
        for file_path in result["failed_root_files"]:
            print(f"[MISSING FILE] {file_path}")
    else:
        print("All required root files found.")

    print("-" * REPORT_WIDTH)
    print("FOLDER CHECK")

    if result["failed_folders"]:
        for folder_path in result["failed_folders"]:
            print(f"[MISSING FOLDER] {folder_path}")
    else:
        print("All required folders found.")

    print("-" * REPORT_WIDTH)
    print("LOG FILE CHECK")
    print(f"Log Folder: {result['log_folder']}")

    if result["failed_logs"]:
        for log_path in result["failed_logs"]:
            print(f"[MISSING LOG] {log_path}")
    else:
        print("All expected log files found.")

    print("-" * REPORT_WIDTH)
    print("FMP FREE MARKET CONTEXT — PHASE 37")

    phase_37 = result["phase_37"]
    print(f"Phase 37 Passed: {phase_37.get('passed')}")
    print(
        f"FMP Context Enabled: "
        f"{phase_37.get('enabled')}"
    )
    print(
        f"FMP Forex News Enabled: "
        f"{phase_37.get('forex_news_enabled')}"
    )
    print(
        f"FMP Gold Symbol: "
        f"{phase_37.get('gold_symbol')}"
    )
    print(
        f"FMP Refresh Hours: "
        f"{phase_37.get('refresh_hours')}"
    )
    print(
        "Configured Estimated Calls/Day: "
        f"{phase_37.get('configured_estimated_calls_per_day')}"
    )
    print(
        f"FMP API Key Available: "
        f"{phase_37.get('api_key_available')}"
    )

    cache = phase_37.get("cache", {})
    print(f"FMP Cache File: {cache.get('file_path')}")
    print(f"FMP Cache Exists: {cache.get('exists')}")
    print(
        f"FMP Cache Last Refresh: "
        f"{cache.get('last_refresh')}"
    )
    print(
        f"Cached Gold Quote Success: "
        f"{cache.get('gold_quote_success')}"
    )
    print(
        "Cached Calls Used When Created: "
        f"{cache.get('calls_used_when_created')}"
    )
    print(
        "Cached Estimated Calls/Day: "
        f"{cache.get('estimated_calls_per_day')}"
    )

    for error in phase_37.get("errors", []):
        print(f"[PHASE 37 ERROR] {error}")

    for warning in phase_37.get("warnings", []):
        print(f"[PHASE 37 WARNING] {warning}")

    if not phase_37.get("errors"):
        print("No Phase 37 errors.")

    print("-" * REPORT_WIDTH)
    print("PAPER TRADE REPORT")

    paper_report = result["paper_report"]

    if "error" in paper_report:
        print(f"[ERROR] {paper_report['error']}")
    else:
        print(
            "Total Paper Trades: "
            f"{paper_report.get('total_paper_trades')}"
        )
        print(
            "Open Paper Trades: "
            f"{paper_report.get('open_paper_trades')}"
        )
        print(
            "Closed Paper Trades: "
            f"{paper_report.get('closed_paper_trades')}"
        )
        print(
            "Win Rate: "
            f"{paper_report.get('win_rate_percent')}%"
        )
        print(
            "Realized Profit: "
            f"{paper_report.get('realized_profit_usd')}"
        )

    print("-" * REPORT_WIDTH)
    print("ADVANCED RISK")

    advanced_risk = result["advanced_risk"]

    if "error" in advanced_risk:
        print(f"[ERROR] {advanced_risk['error']}")
    else:
        print(
            f"Risk Allowed: "
            f"{advanced_risk.get('allowed')}"
        )
        print(
            f"Risk Action: "
            f"{advanced_risk.get('action')}"
        )
        print(
            "Daily P/L: "
            f"{advanced_risk.get('daily_realized_profit')}"
        )
        print(
            "Daily Trade Count: "
            f"{advanced_risk.get('daily_trade_count')}"
        )
        print(
            "Risk Block Reasons: "
            f"{advanced_risk.get('block_reasons')}"
        )

    print("-" * REPORT_WIDTH)
    print("LIVE READINESS")

    live_readiness = result["live_readiness"]

    if "error" in live_readiness:
        print(f"[ERROR] {live_readiness['error']}")
    else:
        print(
            "Ready For Review: "
            f"{live_readiness.get('ready_for_review')}"
        )
        print(
            "Closed Paper Trades: "
            f"{live_readiness.get('closed_paper_trades')}"
        )
        print(
            "Paper Win Rate: "
            f"{live_readiness.get('paper_win_rate')}%"
        )
        print(
            f"Blockers: "
            f"{live_readiness.get('blockers')}"
        )
        print(
            f"Warnings: "
            f"{live_readiness.get('warnings')}"
        )

    print("-" * REPORT_WIDTH)
    print("CRITICAL FAILURES")

    if result["critical_failures"]:
        for failure in result["critical_failures"]:
            print(f"[CRITICAL] {failure}")
    else:
        print("None")

    print("=" * REPORT_WIDTH)

    if result["audit_passed"]:
        print("SYSTEM AUDIT STATUS: PASSED")
    else:
        print("SYSTEM AUDIT STATUS: FAILED")

    print("=" * REPORT_WIDTH)
    print("")

    return result
