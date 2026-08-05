import csv
import os
from datetime import datetime

from config import settings


RISK_ENGINE_FIELDS = [
    "timestamp",
    "symbol",
    "advanced_risk_allowed",
    "advanced_risk_action",
    "daily_realized_profit",
    "daily_trade_count",
    "consecutive_losses",
    "max_drawdown",
    "daily_loss_limit",
    "max_daily_trades",
    "max_consecutive_losses",
    "max_drawdown_usd",
    "advanced_risk_warnings",
    "advanced_risk_block_reasons",
    "slippage_allowed",
    "slippage_action",
    "snapshot_price",
    "latest_price",
    "slippage",
    "max_slippage",
    "slippage_block_reasons",
    "runtime_seconds",
]


def _get_value(source, *keys, default=""):
    if source is None:
        return default

    for key in keys:
        if isinstance(source, dict):
            value = source.get(key)
        else:
            value = getattr(source, key, None)

        if value is not None:
            return value

    return default


def _yes_no(value):
    if value is True:
        return "YES"

    if value is False:
        return "NO"

    return str(value)


def _join_list(value):
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)

    return str(value)


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_risk_engine_log_path():
    return os.path.join(_get_log_folder(), "risk_engine_log.csv")


def build_risk_engine_row(cycle):
    snapshot = _get_value(cycle, "snapshot", default={})
    advanced_risk = _get_value(cycle, "advanced_risk", default={})
    slippage_guard = _get_value(cycle, "slippage_guard", default={})

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": _get_value(snapshot, "symbol", default=getattr(settings, "SYMBOL", "XAUUSD")),

        "advanced_risk_allowed": _yes_no(
            _get_value(advanced_risk, "allowed", default="")
        ),
        "advanced_risk_action": _get_value(
            advanced_risk,
            "action",
            default="",
        ),
        "daily_realized_profit": _get_value(
            advanced_risk,
            "daily_realized_profit",
            default="",
        ),
        "daily_trade_count": _get_value(
            advanced_risk,
            "daily_trade_count",
            default="",
        ),
        "consecutive_losses": _get_value(
            advanced_risk,
            "consecutive_losses",
            default="",
        ),
        "max_drawdown": _get_value(
            advanced_risk,
            "max_drawdown",
            default="",
        ),
        "daily_loss_limit": _get_value(
            advanced_risk,
            "daily_loss_limit",
            default="",
        ),
        "max_daily_trades": _get_value(
            advanced_risk,
            "max_daily_trades",
            default="",
        ),
        "max_consecutive_losses": _get_value(
            advanced_risk,
            "max_consecutive_losses",
            default="",
        ),
        "max_drawdown_usd": _get_value(
            advanced_risk,
            "max_drawdown_usd",
            default="",
        ),
        "advanced_risk_warnings": _join_list(
            _get_value(advanced_risk, "warnings", default=[])
        ),
        "advanced_risk_block_reasons": _join_list(
            _get_value(advanced_risk, "block_reasons", default=[])
        ),

        "slippage_allowed": _yes_no(
            _get_value(slippage_guard, "allowed", default="")
        ),
        "slippage_action": _get_value(
            slippage_guard,
            "action",
            default="",
        ),
        "snapshot_price": _get_value(
            slippage_guard,
            "snapshot_price",
            default="",
        ),
        "latest_price": _get_value(
            slippage_guard,
            "latest_price",
            default="",
        ),
        "slippage": _get_value(
            slippage_guard,
            "slippage",
            default="",
        ),
        "max_slippage": _get_value(
            slippage_guard,
            "max_slippage",
            default="",
        ),
        "slippage_block_reasons": _join_list(
            _get_value(slippage_guard, "block_reasons", default=[])
        ),

        "runtime_seconds": _get_value(
            cycle,
            "runtime_seconds",
            default="",
        ),
    }


def log_risk_engine(cycle):
    log_path = get_risk_engine_log_path()
    file_exists = os.path.exists(log_path)

    row = build_risk_engine_row(cycle)

    with open(log_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=RISK_ENGINE_FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    return log_path