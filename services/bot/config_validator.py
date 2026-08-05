import os
from typing import Any

from config import settings


REPORT_WIDTH = 70


def _has_setting(name: str) -> bool:
    return hasattr(settings, name)


def _get_setting(name: str, default: Any = None) -> Any:
    return getattr(settings, name, default)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_keyword_list(
    errors: list[str],
    warnings: list[str],
    name: str,
) -> None:
    value = _get_setting(name)

    if not isinstance(value, list):
        errors.append(f"{name} must be a list.")
    elif not value:
        warnings.append(f"{name} is empty.")
    elif any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{name} must contain only non-empty strings.")


def _validate_numeric_group(
    errors: list[str],
    names: tuple[str, ...],
    *,
    integer: bool = False,
    allow_zero: bool = False,
) -> None:
    for name in names:
        value = _get_setting(name)

        if value is None:
            continue

        valid_type = _is_integer(value) if integer else _is_number(value)

        if not valid_type:
            kind = "an integer" if integer else "numeric"
            errors.append(f"{name} must be {kind}.")
            continue

        if allow_zero:
            if value < 0:
                errors.append(f"{name} must not be negative.")
        elif value <= 0:
            errors.append(f"{name} must be greater than 0.")


def validate_config() -> dict[str, Any]:
    """
    Validates the complete bot configuration, including Phase 37.
    """

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    required_settings = list(dict.fromkeys([
        # Core
        "SYMBOL", "LOT_SIZE", "MAGIC_NUMBER", "MAX_SPREAD",
        "PROFIT_TARGET_USD", "MIN_AI_CONFIDENCE",
        "MAX_OPEN_POSITIONS", "RUN_INTERVAL_SECONDS",
        "MAX_BOT_CYCLES", "LOG_FILE_PATH", "SIGNAL_LOG_FOLDER",
        "SAVE_SIGNAL_TEXT_LOGS", "USE_DAILY_LOG_FOLDERS",
        "LOG_DATE_FORMAT",

        # Live safety
        "ENABLE_LIVE_TRADING", "EMERGENCY_STOP",
        "LIVE_TRADING_CONFIRMATION",
        "REQUIRED_LIVE_TRADING_CONFIRMATION",
        "REQUIRE_LIVE_READINESS_BEFORE_TRADING",

        # Trade quality
        "MIN_TRADE_SCORE", "MIN_TREND_CONFIDENCE",
        "MIN_STRUCTURE_CONFIDENCE",
        "BLOCK_HIGH_VOLATILITY_TRADES",
        "BLOCK_NEUTRAL_STRUCTURE_TRADES",
        "BLOCK_UNSAFE_SPREAD_TRADES",
        "BLOCK_INVALID_PRICE_TRADES",
        "BLOCK_MISSING_CANDLE_TRADES",
        "BLOCK_INACTIVE_SESSION_TRADES",
        "BLOCK_UNKNOWN_VOLATILITY_TRADES",
        "BLOCK_EXTREME_VOLATILITY_TRADES",

        # Paper trading
        "PAPER_STOP_LOSS_USD", "PAPER_MAX_HOLD_SECONDS",
        "PAPER_CLOSE_ON_OPPOSITE_SIGNAL",

        # Advanced risk and slippage
        "DAILY_LOSS_LIMIT_USD", "MAX_DAILY_TRADES",
        "MAX_CONSECUTIVE_LOSSES", "MAX_DRAWDOWN_USD",
        "ENABLE_ADVANCED_RISK_ENGINE", "MAX_SLIPPAGE_USD",
        "BLOCK_ON_SLIPPAGE_CHECK_ERROR",

        # Live readiness
        "MIN_CLOSED_PAPER_TRADES_FOR_LIVE",
        "MIN_PAPER_WIN_RATE_FOR_LIVE",
        "MAX_ALLOWED_PAPER_DRAWDOWN_FOR_LIVE",
        "REQUIRE_RISK_ENGINE_FOR_LIVE",
        "REQUIRE_SLIPPAGE_GUARD_FOR_LIVE",

        # Forward validation and tests
        "FORWARD_VALIDATION_CYCLES",
        "FORWARD_VALIDATION_INTERVAL_SECONDS",
        "RUN_MAIN_IN_TEST_SUITE", "RUN_TEST_TIMEOUT_SECONDS",

        # News filter
        "ENABLE_NEWS_RISK_FILTER", "NEWS_EVENTS_FILE",
        "NEWS_BLOCK_BEFORE_MINUTES", "NEWS_BLOCK_AFTER_MINUTES",
        "BLOCK_HIGH_IMPACT_NEWS", "BLOCK_MEDIUM_IMPACT_NEWS",

        # Automatic calendar
        "ENABLE_AUTO_ECONOMIC_CALENDAR",
        "AUTO_ECONOMIC_CALENDAR_PROVIDER", "FMP_API_KEY",
        "AUTO_ECONOMIC_CALENDAR_COUNTRY",
        "AUTO_ECONOMIC_CALENDAR_CURRENCY",
        "AUTO_ECONOMIC_CALENDAR_DAYS_AHEAD",
        "AUTO_ECONOMIC_CALENDAR_REFRESH_HOURS",
        "AUTO_ECONOMIC_CALENDAR_TIMEOUT_SECONDS",
        "AUTO_ECONOMIC_CALENDAR_SYNC_FILE",
        "AUTO_ECONOMIC_CALENDAR_KEYWORDS",

        # Free calendar fallback
        "ENABLE_FREE_CALENDAR_FALLBACK",
        "FREE_CALENDAR_FALLBACK_DAYS_AHEAD",
        "FREE_CALENDAR_TIMEOUT_SECONDS",
        "FREE_CALENDAR_TIMEZONE",
        "FREE_CALENDAR_USE_CONSERVATIVE_ESTIMATES",

        # FMP Phase 37
        "ENABLE_FMP_MARKET_CONTEXT",
        "FMP_MARKET_CONTEXT_REFRESH_HOURS",
        "FMP_MARKET_CONTEXT_TIMEOUT_SECONDS",
        "FMP_MARKET_CONTEXT_FILE", "FMP_GOLD_SYMBOL",
        "ENABLE_FMP_FOREX_NEWS", "FMP_FOREX_NEWS_LIMIT",
        "FMP_PRICE_CONFIRMATION_MAX_DIFF_USD",
        "FMP_CONTEXT_CONFIDENCE_BONUS",
        "FMP_CONTEXT_CONFIDENCE_PENALTY",
        "FMP_HIGH_RISK_NEWS_KEYWORDS",
    ]))

    for name in required_settings:
        if _has_setting(name):
            checks.append(f"Found setting: {name}")
        else:
            errors.append(f"Missing required setting: {name}")

    bool_settings = (
        "ENABLE_LIVE_TRADING", "EMERGENCY_STOP",
        "SAVE_SIGNAL_TEXT_LOGS", "USE_DAILY_LOG_FOLDERS",
        "BLOCK_HIGH_VOLATILITY_TRADES",
        "BLOCK_NEUTRAL_STRUCTURE_TRADES",
        "BLOCK_UNSAFE_SPREAD_TRADES",
        "BLOCK_INVALID_PRICE_TRADES",
        "BLOCK_MISSING_CANDLE_TRADES",
        "BLOCK_INACTIVE_SESSION_TRADES",
        "BLOCK_UNKNOWN_VOLATILITY_TRADES",
        "BLOCK_EXTREME_VOLATILITY_TRADES",
        "PAPER_CLOSE_ON_OPPOSITE_SIGNAL",
        "ENABLE_ADVANCED_RISK_ENGINE",
        "BLOCK_ON_SLIPPAGE_CHECK_ERROR",
        "REQUIRE_RISK_ENGINE_FOR_LIVE",
        "REQUIRE_SLIPPAGE_GUARD_FOR_LIVE",
        "REQUIRE_LIVE_READINESS_BEFORE_TRADING",
        "RUN_MAIN_IN_TEST_SUITE", "ENABLE_NEWS_RISK_FILTER",
        "BLOCK_HIGH_IMPACT_NEWS", "BLOCK_MEDIUM_IMPACT_NEWS",
        "ENABLE_AUTO_ECONOMIC_CALENDAR",
        "ENABLE_FREE_CALENDAR_FALLBACK",
        "FREE_CALENDAR_USE_CONSERVATIVE_ESTIMATES",
        "ENABLE_FMP_MARKET_CONTEXT", "ENABLE_FMP_FOREX_NEWS",
    )

    for name in bool_settings:
        value = _get_setting(name)
        if value is not None and not isinstance(value, bool):
            errors.append(f"{name} must be True or False.")

    string_settings = (
        "SYMBOL", "LOG_FILE_PATH", "SIGNAL_LOG_FOLDER",
        "LOG_DATE_FORMAT", "LIVE_TRADING_CONFIRMATION",
        "REQUIRED_LIVE_TRADING_CONFIRMATION", "NEWS_EVENTS_FILE",
        "AUTO_ECONOMIC_CALENDAR_PROVIDER", "FMP_API_KEY",
        "AUTO_ECONOMIC_CALENDAR_COUNTRY",
        "AUTO_ECONOMIC_CALENDAR_CURRENCY",
        "AUTO_ECONOMIC_CALENDAR_SYNC_FILE",
        "FREE_CALENDAR_TIMEZONE", "FMP_MARKET_CONTEXT_FILE",
        "FMP_GOLD_SYMBOL",
    )
    empty_allowed = {"FMP_API_KEY", "LIVE_TRADING_CONFIRMATION"}

    for name in string_settings:
        value = _get_setting(name)

        if value is not None and not isinstance(value, str):
            errors.append(f"{name} must be a string.")
        elif (
            isinstance(value, str)
            and name not in empty_allowed
            and not value.strip()
        ):
            errors.append(f"{name} must not be empty.")

    _validate_numeric_group(
        errors,
        (
            "LOT_SIZE", "MAX_SPREAD", "PROFIT_TARGET_USD",
            "RUN_INTERVAL_SECONDS", "PAPER_STOP_LOSS_USD",
            "DAILY_LOSS_LIMIT_USD", "MAX_DRAWDOWN_USD",
            "MAX_SLIPPAGE_USD",
            "FMP_PRICE_CONFIRMATION_MAX_DIFF_USD",
        ),
    )
    _validate_numeric_group(
        errors,
        (
            "MAX_ALLOWED_PAPER_DRAWDOWN_FOR_LIVE",
            "FMP_CONTEXT_CONFIDENCE_BONUS",
            "FMP_CONTEXT_CONFIDENCE_PENALTY",
        ),
        allow_zero=True,
    )
    _validate_numeric_group(
        errors,
        (
            "MAGIC_NUMBER", "MAX_OPEN_POSITIONS", "MAX_BOT_CYCLES",
            "PAPER_MAX_HOLD_SECONDS", "MAX_DAILY_TRADES",
            "MAX_CONSECUTIVE_LOSSES",
            "MIN_CLOSED_PAPER_TRADES_FOR_LIVE",
            "FORWARD_VALIDATION_CYCLES",
            "FORWARD_VALIDATION_INTERVAL_SECONDS",
            "RUN_TEST_TIMEOUT_SECONDS",
            "AUTO_ECONOMIC_CALENDAR_DAYS_AHEAD",
            "AUTO_ECONOMIC_CALENDAR_REFRESH_HOURS",
            "AUTO_ECONOMIC_CALENDAR_TIMEOUT_SECONDS",
            "FREE_CALENDAR_FALLBACK_DAYS_AHEAD",
            "FREE_CALENDAR_TIMEOUT_SECONDS",
            "FMP_MARKET_CONTEXT_REFRESH_HOURS",
            "FMP_MARKET_CONTEXT_TIMEOUT_SECONDS",
            "FMP_FOREX_NEWS_LIMIT",
        ),
        integer=True,
    )
    _validate_numeric_group(
        errors,
        ("NEWS_BLOCK_BEFORE_MINUTES", "NEWS_BLOCK_AFTER_MINUTES"),
        integer=True,
        allow_zero=True,
    )

    for name in (
        "MIN_AI_CONFIDENCE", "MIN_TREND_CONFIDENCE",
        "MIN_STRUCTURE_CONFIDENCE",
        "FMP_CONTEXT_CONFIDENCE_BONUS",
        "FMP_CONTEXT_CONFIDENCE_PENALTY",
    ):
        value = _get_setting(name)
        if value is not None:
            if not _is_number(value):
                errors.append(f"{name} must be numeric.")
            elif not 0 <= value <= 1:
                errors.append(f"{name} must be between 0 and 1.")

    score = _get_setting("MIN_TRADE_SCORE")
    if score is not None:
        if not _is_number(score):
            errors.append("MIN_TRADE_SCORE must be numeric.")
        elif not 0 <= score <= 100:
            errors.append("MIN_TRADE_SCORE must be between 0 and 100.")

    win_rate = _get_setting("MIN_PAPER_WIN_RATE_FOR_LIVE")
    if win_rate is not None:
        if not _is_number(win_rate):
            errors.append(
                "MIN_PAPER_WIN_RATE_FOR_LIVE must be numeric."
            )
        elif not 0 <= win_rate <= 100:
            errors.append(
                "MIN_PAPER_WIN_RATE_FOR_LIVE must be between 0 and 100."
            )

    _validate_keyword_list(
        errors, warnings, "AUTO_ECONOMIC_CALENDAR_KEYWORDS"
    )
    _validate_keyword_list(
        errors, warnings, "FMP_HIGH_RISK_NEWS_KEYWORDS"
    )

    # ------------------------------------------------------------------
    # Live-trading safety
    # ------------------------------------------------------------------

    enable_live = _get_setting("ENABLE_LIVE_TRADING", False)
    emergency_stop = _get_setting("EMERGENCY_STOP", False)
    confirmation = _get_setting("LIVE_TRADING_CONFIRMATION", "")
    required_confirmation = _get_setting(
        "REQUIRED_LIVE_TRADING_CONFIRMATION",
        "I_ACCEPT_LIVE_TRADING_RISK",
    )

    if enable_live is True:
        warnings.append(
            "ENABLE_LIVE_TRADING is True. Live orders may be possible."
        )

        if confirmation != required_confirmation:
            errors.append(
                "Live trading is enabled, but "
                "LIVE_TRADING_CONFIRMATION is invalid."
            )
        if emergency_stop is True:
            errors.append(
                "Live trading is enabled while EMERGENCY_STOP is True."
            )
        if _get_setting(
            "REQUIRE_LIVE_READINESS_BEFORE_TRADING", True
        ) is not True:
            errors.append(
                "Live trading requires "
                "REQUIRE_LIVE_READINESS_BEFORE_TRADING=True."
            )
        if _get_setting("ENABLE_ADVANCED_RISK_ENGINE", True) is not True:
            errors.append(
                "Live trading requires ENABLE_ADVANCED_RISK_ENGINE=True."
            )
        if _get_setting("REQUIRE_RISK_ENGINE_FOR_LIVE", True) is not True:
            errors.append(
                "Live trading requires REQUIRE_RISK_ENGINE_FOR_LIVE=True."
            )
        if _get_setting(
            "REQUIRE_SLIPPAGE_GUARD_FOR_LIVE", True
        ) is not True:
            errors.append(
                "Live trading requires "
                "REQUIRE_SLIPPAGE_GUARD_FOR_LIVE=True."
            )
    else:
        checks.append("Live trading is disabled. Safe mode active.")

    if confirmation and enable_live is not True:
        warnings.append(
            "LIVE_TRADING_CONFIRMATION is filled, but live trading "
            "is disabled."
        )

    # ------------------------------------------------------------------
    # API key and calendar fallback
    # ------------------------------------------------------------------

    settings_key = str(_get_setting("FMP_API_KEY", "") or "").strip()
    environment_key = str(os.getenv("FMP_API_KEY", "") or "").strip()
    effective_key = settings_key or environment_key

    if settings_key:
        warnings.append(
            "FMP_API_KEY is stored in settings.py. The environment "
            "variable is safer."
        )
    elif environment_key:
        checks.append("FMP API key found in the environment variable.")
    else:
        checks.append("No FMP API key was found.")

    provider = str(
        _get_setting("AUTO_ECONOMIC_CALENDAR_PROVIDER", "FMP") or ""
    ).strip()
    if provider.upper() != "FMP":
        warnings.append(
            f"AUTO_ECONOMIC_CALENDAR_PROVIDER is {provider!r}; "
            "current code expects FMP."
        )

    auto_calendar = (
        _get_setting("ENABLE_AUTO_ECONOMIC_CALENDAR", True) is True
    )
    free_fallback = (
        _get_setting("ENABLE_FREE_CALENDAR_FALLBACK", True) is True
    )

    if auto_calendar and not effective_key:
        if free_fallback:
            checks.append(
                "No FMP key is available, but free calendar fallback "
                "is enabled."
            )
        else:
            errors.append(
                "Automatic calendar is enabled without an FMP key "
                "and without free fallback."
            )

    if auto_calendar and not free_fallback:
        warnings.append("Free calendar fallback is disabled.")

    # ------------------------------------------------------------------
    # Phase 37 FMP validation
    # ------------------------------------------------------------------

    fmp_context_enabled = (
        _get_setting("ENABLE_FMP_MARKET_CONTEXT", True) is True
    )
    forex_news_enabled = (
        _get_setting("ENABLE_FMP_FOREX_NEWS", False) is True
    )
    refresh_hours = _get_setting("FMP_MARKET_CONTEXT_REFRESH_HOURS")

    if fmp_context_enabled:
        if effective_key:
            checks.append("FMP market context has an API key.")
        else:
            warnings.append(
                "FMP market context is enabled, but no API key was "
                "found. The bot will continue without GCUSD context."
            )

        if forex_news_enabled:
            warnings.append(
                "FMP Forex News is enabled. It may require paid access "
                "and increases API usage."
            )
        else:
            checks.append(
                "FMP Forex News is disabled. Phase 37 uses only GCUSD."
            )

        if _is_integer(refresh_hours) and refresh_hours > 0:
            calls_per_refresh = 2 if forex_news_enabled else 1
            calls_per_day = (24 / refresh_hours) * calls_per_refresh

            checks.append(
                f"Estimated FMP market-context calls/day: "
                f"{calls_per_day:.1f}"
            )

            if calls_per_day > 250:
                errors.append(
                    "FMP market-context settings may exceed "
                    "250 API calls per day."
                )
            elif calls_per_day > 50:
                warnings.append(
                    "FMP market-context refresh frequency is high."
                )

    gold_symbol = str(
        _get_setting("FMP_GOLD_SYMBOL", "") or ""
    ).strip().upper()
    if gold_symbol and gold_symbol != "GCUSD":
        warnings.append(
            f"FMP_GOLD_SYMBOL is {gold_symbol}; Phase 37 was tested "
            "with GCUSD."
        )

    if _get_setting("ENABLE_ADVANCED_RISK_ENGINE", True) is not True:
        warnings.append("Advanced risk engine is disabled.")
    if _get_setting("ENABLE_NEWS_RISK_FILTER", True) is not True:
        warnings.append("News risk filter is disabled.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "settings_checked": len(required_settings),
        "safe_mode": enable_live is not True,
        "emergency_stop": emergency_stop is True,
        "fmp_api_key_available": bool(effective_key),
        "fmp_forex_news_enabled": forex_news_enabled,
    }


def print_config_validation_report(
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if result is None:
        result = validate_config()

    print("")
    print("=" * REPORT_WIDTH)
    print("CONFIG VALIDATION REPORT")
    print("=" * REPORT_WIDTH)
    print(
        f"Config Status: "
        f"{'VALID' if result.get('valid') else 'INVALID'}"
    )
    print(f"Settings Checked: {result.get('settings_checked')}")
    print(
        f"Safe Mode: "
        f"{'YES' if result.get('safe_mode') else 'NO'}"
    )

    print("-" * REPORT_WIDTH)
    print("ERRORS")
    if result.get("errors"):
        for error in result["errors"]:
            print(f"[ERROR] {error}")
    else:
        print("No errors found.")

    print("-" * REPORT_WIDTH)
    print("WARNINGS")
    if result.get("warnings"):
        for warning in result["warnings"]:
            print(f"[WARNING] {warning}")
    else:
        print("No warnings found.")

    print("=" * REPORT_WIDTH)
    print("")
    return result


def validate_or_raise() -> dict[str, Any]:
    result = validate_config()

    if not result["valid"]:
        print_config_validation_report(result)
        raise RuntimeError("Config validation failed.")

    return result


# Backward-compatible aliases
def validate_settings() -> dict[str, Any]:
    return validate_config()


def run_config_validation() -> dict[str, Any]:
    return validate_config()


def check_config() -> dict[str, Any]:
    return validate_config()
