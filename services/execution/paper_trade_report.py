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


def load_paper_trades():
    path = get_paper_trade_file_path()

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def build_paper_trade_report(symbol=None):
    symbol = symbol or getattr(settings, "SYMBOL", "XAUUSD")
    magic_number = getattr(settings, "MAGIC_NUMBER", None)

    trades = load_paper_trades()

    bot_trades = [
        trade for trade in trades
        if trade.get("symbol") == symbol
        and trade.get("magic_number") == magic_number
    ]

    open_trades = [
        trade for trade in bot_trades
        if trade.get("status") == "OPEN"
    ]

    closed_trades = [
        trade for trade in bot_trades
        if trade.get("status") == "CLOSED"
    ]

    realized_profit = 0.0
    winning_trades = 0
    losing_trades = 0

    for trade in closed_trades:
        profit = float(trade.get("final_profit_usd", 0.0))
        realized_profit += profit

        if profit > 0:
            winning_trades += 1
        elif profit < 0:
            losing_trades += 1

    total_closed = len(closed_trades)
    win_rate = 0.0

    if total_closed > 0:
        win_rate = round((winning_trades / total_closed) * 100, 2)

    unrealized_profit = 0.0

    for trade in open_trades:
        unrealized_profit += float(trade.get("unrealized_profit_usd", 0.0))

    return {
        "symbol": symbol,
        "total_paper_trades": len(bot_trades),
        "open_paper_trades": len(open_trades),
        "closed_paper_trades": len(closed_trades),
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "realized_profit_usd": round(realized_profit, 2),
        "unrealized_profit_usd": round(unrealized_profit, 2),
        "win_rate_percent": win_rate,
        "file_path": get_paper_trade_file_path(),
    }