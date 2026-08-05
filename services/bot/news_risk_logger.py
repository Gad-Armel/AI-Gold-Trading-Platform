import csv
import os
from datetime import datetime

from config import settings


NEWS_RISK_FIELDS = [
    "timestamp",
    "symbol",
    "news_allowed",
    "news_action",
    "news_message",
    "active_events",
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


def _join_list(value):
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)

    return str(value)


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


def get_news_risk_log_path():
    return os.path.join(_get_log_folder(), "news_risk_log.csv")


def build_news_risk_row(cycle):
    snapshot = _get_value(cycle, "snapshot", default={})
    news_risk = _get_value(cycle, "news_risk", default={})

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": _get_value(snapshot, "symbol", default=getattr(settings, "SYMBOL", "XAUUSD")),
        "news_allowed": _yes_no(_get_value(news_risk, "allowed", default="")),
        "news_action": _get_value(news_risk, "action", default=""),
        "news_message": _get_value(news_risk, "message", default=""),
        "active_events": _join_list(_get_value(news_risk, "active_events", default=[])),
        "block_reasons": _join_list(_get_value(news_risk, "block_reasons", default=[])),
        "runtime_seconds": _get_value(cycle, "runtime_seconds", default=""),
    }


def log_news_risk(cycle):
    log_path = get_news_risk_log_path()
    file_exists = os.path.exists(log_path)

    row = build_news_risk_row(cycle)

    with open(log_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=NEWS_RISK_FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    return log_path