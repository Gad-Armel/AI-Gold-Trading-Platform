import json
import os
from datetime import datetime

from config import settings


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_paper_trade_file_path():
    return os.path.join(_get_log_folder(), "paper_trades.json")


def reset_paper_trades(symbol=None):
    """
    Clears paper trades only.

    This does NOT touch MT5.
    This does NOT close real positions.
    This is only for safe-mode simulated trades.
    """

    symbol = symbol or getattr(settings, "SYMBOL", "XAUUSD")
    path = get_paper_trade_file_path()

    reset_payload = {
        "reset_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "message": "Paper trades reset. No live MT5 trades were touched.",
    }

    with open(path, "w", encoding="utf-8") as file:
        json.dump([], file, indent=4)

    return {
        "success": True,
        "symbol": symbol,
        "file_path": path,
        "message": reset_payload["message"],
        "reset_at": reset_payload["reset_at"],
    }