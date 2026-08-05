import csv
import os
from datetime import datetime

from config import settings


PAPER_TRADE_REPORT_FIELDS = [
    "timestamp",
    "symbol",
    "total_paper_trades",
    "open_paper_trades",
    "closed_paper_trades",
    "winning_trades",
    "losing_trades",
    "realized_profit_usd",
    "unrealized_profit_usd",
    "win_rate_percent",
    "paper_trade_file_path",
]


def _get_value(source, key, default=""):
    if source is None:
        return default

    if isinstance(source, dict):
        return source.get(key, default)

    return getattr(source, key, default)


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_paper_trade_report_log_path():
    return os.path.join(_get_log_folder(), "paper_trade_report.csv")


def build_paper_trade_report_row(report):
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": _get_value(report, "symbol", getattr(settings, "SYMBOL", "XAUUSD")),
        "total_paper_trades": _get_value(report, "total_paper_trades", 0),
        "open_paper_trades": _get_value(report, "open_paper_trades", 0),
        "closed_paper_trades": _get_value(report, "closed_paper_trades", 0),
        "winning_trades": _get_value(report, "winning_trades", 0),
        "losing_trades": _get_value(report, "losing_trades", 0),
        "realized_profit_usd": _get_value(report, "realized_profit_usd", 0.0),
        "unrealized_profit_usd": _get_value(report, "unrealized_profit_usd", 0.0),
        "win_rate_percent": _get_value(report, "win_rate_percent", 0.0),
        "paper_trade_file_path": _get_value(report, "file_path", ""),
    }


def log_paper_trade_report(report):
    report_log_path = get_paper_trade_report_log_path()
    file_exists = os.path.exists(report_log_path)

    row = build_paper_trade_report_row(report)

    with open(report_log_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=PAPER_TRADE_REPORT_FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    return report_log_path