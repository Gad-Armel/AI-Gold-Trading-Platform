import csv
import json
import os
from datetime import datetime

from config import settings


PAPER_TRADE_HISTORY_FIELDS = [
    "trade_id",
    "symbol",
    "direction",
    "entry_price",
    "close_price",
    "lot_size",
    "opened_at",
    "closed_at",
    "status",
    "final_profit_usd",
    "unrealized_profit_usd",
    "close_reason",
    "hold_seconds",
    "magic_number",
]


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_paper_trades_json_path():
    return os.path.join(_get_log_folder(), "paper_trades.json")


def get_paper_trade_history_path():
    return os.path.join(_get_log_folder(), "paper_trade_history.csv")


def _load_paper_trades():
    path = get_paper_trades_json_path()

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def _build_history_row(trade):
    return {
        "trade_id": trade.get("id", ""),
        "symbol": trade.get("symbol", ""),
        "direction": trade.get("direction", ""),
        "entry_price": trade.get("entry_price", ""),
        "close_price": trade.get("close_price", ""),
        "lot_size": trade.get("lot_size", ""),
        "opened_at": trade.get("opened_at", ""),
        "closed_at": trade.get("closed_at", ""),
        "status": trade.get("status", ""),
        "final_profit_usd": trade.get("final_profit_usd", ""),
        "unrealized_profit_usd": trade.get("unrealized_profit_usd", ""),
        "close_reason": trade.get("close_reason", ""),
        "hold_seconds": trade.get("hold_seconds", ""),
        "magic_number": trade.get("magic_number", ""),
    }


def export_paper_trade_history(symbol=None):
    """
    Exports all current paper trades from paper_trades.json into a clean CSV.

    This overwrites the CSV each time so there are no duplicate rows.
    """

    symbol = symbol or getattr(settings, "SYMBOL", "XAUUSD")
    magic_number = getattr(settings, "MAGIC_NUMBER", None)

    trades = _load_paper_trades()

    bot_trades = [
        trade for trade in trades
        if trade.get("symbol") == symbol
        and trade.get("magic_number") == magic_number
    ]

    history_path = get_paper_trade_history_path()

    with open(history_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=PAPER_TRADE_HISTORY_FIELDS)
        writer.writeheader()

        for trade in bot_trades:
            writer.writerow(_build_history_row(trade))

    return {
        "success": True,
        "symbol": symbol,
        "trade_count": len(bot_trades),
        "file_path": history_path,
    }