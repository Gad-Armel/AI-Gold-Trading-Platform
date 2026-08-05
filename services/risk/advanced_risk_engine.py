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


def get_paper_trades_path():
    return os.path.join(_get_log_folder(), "paper_trades.json")


def _load_paper_trades():
    path = get_paper_trades_path()

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        return []

    except Exception:
        return []


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _get_today_trades(symbol):
    today = datetime.now().strftime("%Y-%m-%d")
    magic_number = getattr(settings, "MAGIC_NUMBER", None)

    trades = _load_paper_trades()

    today_trades = []

    for trade in trades:
        if trade.get("symbol") != symbol:
            continue

        if trade.get("magic_number") != magic_number:
            continue

        opened_at = str(trade.get("opened_at", ""))

        if opened_at.startswith(today):
            today_trades.append(trade)

    return today_trades


def _calculate_consecutive_losses(closed_trades):
    consecutive_losses = 0

    sorted_trades = sorted(
        closed_trades,
        key=lambda trade: trade.get("closed_at", ""),
        reverse=True,
    )

    for trade in sorted_trades:
        profit = _safe_float(trade.get("final_profit_usd", 0.0))

        if profit < 0:
            consecutive_losses += 1
        else:
            break

    return consecutive_losses


def _calculate_drawdown(closed_trades):
    balance_curve = []
    running_profit = 0.0

    sorted_trades = sorted(
        closed_trades,
        key=lambda trade: trade.get("closed_at", ""),
    )

    for trade in sorted_trades:
        running_profit += _safe_float(trade.get("final_profit_usd", 0.0))
        balance_curve.append(running_profit)

    if not balance_curve:
        return 0.0

    peak = balance_curve[0]
    max_drawdown = 0.0

    for value in balance_curve:
        if value > peak:
            peak = value

        drawdown = peak - value

        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return round(max_drawdown, 2)


def evaluate_advanced_risk(symbol=None):
    """
    Advanced risk engine.

    Uses paper-trade history for now.
    Later this same logic can protect live trading.
    """

    symbol = symbol or getattr(settings, "SYMBOL", "XAUUSD")

    if not getattr(settings, "ENABLE_ADVANCED_RISK_ENGINE", True):
        return {
            "allowed": True,
            "action": "RISK_ENGINE_DISABLED",
            "message": "Advanced risk engine is disabled.",
            "block_reasons": [],
        }

    today_trades = _get_today_trades(symbol)

    closed_trades = [
        trade for trade in today_trades
        if trade.get("status") == "CLOSED"
    ]

    daily_realized_profit = sum(
        _safe_float(trade.get("final_profit_usd", 0.0))
        for trade in closed_trades
    )

    daily_trade_count = len(today_trades)
    consecutive_losses = _calculate_consecutive_losses(closed_trades)
    max_drawdown = _calculate_drawdown(closed_trades)

    block_reasons = []
    warnings = []

    daily_loss_limit = float(getattr(settings, "DAILY_LOSS_LIMIT_USD", 10.00))
    max_daily_trades = int(getattr(settings, "MAX_DAILY_TRADES", 5))
    max_consecutive_losses = int(getattr(settings, "MAX_CONSECUTIVE_LOSSES", 3))
    max_drawdown_usd = float(getattr(settings, "MAX_DRAWDOWN_USD", 15.00))

    if daily_realized_profit <= -daily_loss_limit:
        block_reasons.append(
            f"Daily loss limit reached: {daily_realized_profit} <= -{daily_loss_limit}"
        )

    if daily_trade_count >= max_daily_trades:
        block_reasons.append(
            f"Max daily trades reached: {daily_trade_count} >= {max_daily_trades}"
        )

    if consecutive_losses >= max_consecutive_losses:
        block_reasons.append(
            f"Max consecutive losses reached: {consecutive_losses} >= {max_consecutive_losses}"
        )

    if max_drawdown >= max_drawdown_usd:
        block_reasons.append(
            f"Max drawdown reached: {max_drawdown} >= {max_drawdown_usd}"
        )

    if daily_realized_profit < 0:
        warnings.append(f"Daily realized P/L is negative: {daily_realized_profit}")

    allowed = len(block_reasons) == 0

    return {
        "allowed": allowed,
        "action": "RISK_ALLOWED" if allowed else "RISK_BLOCKED",
        "message": "Advanced risk check passed." if allowed else "Advanced risk check blocked trading.",
        "symbol": symbol,
        "daily_realized_profit": round(daily_realized_profit, 2),
        "daily_trade_count": daily_trade_count,
        "consecutive_losses": consecutive_losses,
        "max_drawdown": max_drawdown,
        "daily_loss_limit": daily_loss_limit,
        "max_daily_trades": max_daily_trades,
        "max_consecutive_losses": max_consecutive_losses,
        "max_drawdown_usd": max_drawdown_usd,
        "warnings": warnings,
        "block_reasons": block_reasons,
    }


def apply_advanced_risk_to_ai(ai_result, advanced_risk_result):
    """
    If risk blocks trading, force AI result to NO_TRADE.
    """

    if advanced_risk_result.get("allowed", False):
        return ai_result

    return {
        "action": "NO_TRADE",
        "can_trade": False,
        "confidence": 0.0,
        "reason": "Advanced risk engine blocked trading.",
        "original_ai_result": ai_result,
        "risk_block_reasons": advanced_risk_result.get("block_reasons", []),
    }