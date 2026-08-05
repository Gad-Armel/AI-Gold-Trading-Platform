import csv
import os
from datetime import datetime

from config import settings


DECISION_QUALITY_FIELDS = [
    "timestamp",
    "symbol",
    "raw_decision_action",
    "final_decision_action",
    "trade_score",
    "trade_quality",
    "trade_score_passed",
    "trend_confirmed",
    "trend_message",
    "structure_confirmed",
    "structure_message",
    "ai_quality_passed",
    "ai_original_action",
    "ai_filtered_action",
    "market_filter_passed",
    "volatility_filter_passed",
    "volatility_level",
    "block_reasons",
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


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_decision_quality_log_path():
    return os.path.join(_get_log_folder(), "decision_quality_log.csv")


def build_decision_quality_row(cycle):
    snapshot = _get_value(cycle, "snapshot", default={})
    raw_decision = _get_value(cycle, "raw_decision", default={})
    decision = _get_value(cycle, "decision", default={})
    trade_score = _get_value(cycle, "trade_score", default={})
    trend_confirmation = _get_value(cycle, "trend_confirmation", default={})
    structure_confirmation = _get_value(cycle, "structure_confirmation", default={})
    ai_quality = _get_value(cycle, "ai_quality", default={})

    market_filter = _get_value(trade_score, "market_filter", default={})
    volatility_filter = _get_value(trade_score, "volatility_filter", default={})

    block_reasons = _get_value(trade_score, "block_reasons", default=[])

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": _get_value(snapshot, "symbol", default=getattr(settings, "SYMBOL", "XAUUSD")),

        "raw_decision_action": _get_value(
            raw_decision,
            "action",
            "decision",
            "trade_action",
            default="",
        ),

        "final_decision_action": _get_value(
            decision,
            "action",
            "decision",
            "trade_action",
            default="",
        ),

        "trade_score": _get_value(trade_score, "score", default=""),
        "trade_quality": _get_value(trade_score, "quality", default=""),
        "trade_score_passed": _yes_no(_get_value(trade_score, "passed", default="")),

        "trend_confirmed": _yes_no(_get_value(trend_confirmation, "confirmed", default="")),
        "trend_message": _get_value(trend_confirmation, "message", default=""),

        "structure_confirmed": _yes_no(_get_value(structure_confirmation, "confirmed", default="")),
        "structure_message": _get_value(structure_confirmation, "message", default=""),

        "ai_quality_passed": _yes_no(_get_value(ai_quality, "passed", default="")),
        "ai_original_action": _get_value(ai_quality, "original_ai_action", default=""),
        "ai_filtered_action": _get_value(ai_quality, "filtered_ai_action", default=""),

        "market_filter_passed": _yes_no(_get_value(market_filter, "passed", default="")),
        "volatility_filter_passed": _yes_no(_get_value(volatility_filter, "passed", default="")),
        "volatility_level": _get_value(volatility_filter, "volatility_level", default=""),

        "block_reasons": " | ".join(str(reason) for reason in block_reasons),

        "runtime_seconds": _get_value(cycle, "runtime_seconds", default=""),
    }


def log_decision_quality(cycle):
    log_path = get_decision_quality_log_path()
    file_exists = os.path.exists(log_path)

    row = build_decision_quality_row(cycle)

    with open(log_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=DECISION_QUALITY_FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    return log_path