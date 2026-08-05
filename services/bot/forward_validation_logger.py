import csv
import os
from datetime import datetime

from config import settings


FORWARD_VALIDATION_FIELDS = [
    "timestamp",
    "cycle_number",
    "success",
    "symbol",
    "decision_action",
    "ai_action",
    "dry_run_action",
    "paper_trade_action",
    "paper_trade_open_count",
    "trade_score",
    "trade_quality",
    "advanced_risk_allowed",
    "slippage_allowed",
    "runtime_seconds",
    "error_message",
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


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_forward_validation_log_path():
    return os.path.join(_get_log_folder(), "forward_validation_log.csv")


def build_forward_validation_row(cycle, cycle_number):
    snapshot = _get_value(cycle, "snapshot", default={})
    decision = _get_value(cycle, "decision", default={})
    ai_result = _get_value(cycle, "ai_result", default={})
    dry_run_plan = _get_value(cycle, "dry_run_plan", default={})
    paper_trade_result = _get_value(cycle, "paper_trade_result", default={})
    trade_score = _get_value(cycle, "trade_score", default={})
    advanced_risk = _get_value(cycle, "advanced_risk", default={})
    slippage_guard = _get_value(cycle, "slippage_guard", default={})

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cycle_number": cycle_number,
        "success": _get_value(cycle, "success", default=""),
        "symbol": _get_value(snapshot, "symbol", default=getattr(settings, "SYMBOL", "XAUUSD")),
        "decision_action": _get_value(decision, "action", "decision", default=""),
        "ai_action": _get_value(ai_result, "action", "ai_action", default=""),
        "dry_run_action": _get_value(dry_run_plan, "action", default=""),
        "paper_trade_action": _get_value(paper_trade_result, "action", default=""),
        "paper_trade_open_count": _get_value(paper_trade_result, "open_paper_trades", default=""),
        "trade_score": _get_value(trade_score, "score", default=""),
        "trade_quality": _get_value(trade_score, "quality", default=""),
        "advanced_risk_allowed": _get_value(advanced_risk, "allowed", default=""),
        "slippage_allowed": _get_value(slippage_guard, "allowed", default=""),
        "runtime_seconds": _get_value(cycle, "runtime_seconds", default=""),
        "error_message": _get_value(cycle, "error_message", default=""),
    }


def log_forward_validation_cycle(cycle, cycle_number):
    log_path = get_forward_validation_log_path()
    file_exists = os.path.exists(log_path)

    row = build_forward_validation_row(cycle, cycle_number)

    with open(log_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FORWARD_VALIDATION_FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    return log_path