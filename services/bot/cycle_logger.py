import csv
from datetime import datetime

from services.bot.log_path_manager import get_daily_cycle_log_path


def _get(obj, key, default=""):
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def _first(obj, keys, default=""):
    for key in keys:
        value = _get(obj, key, None)

        if value is not None and value != "":
            return value

    return default


def _format_price_value(price):
    if isinstance(price, dict):
        bid = price.get("bid", "")
        ask = price.get("ask", "")
        spread = price.get("spread", "")
        return f"bid={bid}; ask={ask}; spread={spread}"

    return price


def _build_cycle_row(cycle):
    snapshot = _get(cycle, "snapshot")
    conditions = _get(cycle, "conditions")
    trend = _get(cycle, "trend")
    volatility = _get(cycle, "volatility")
    structure = _get(cycle, "structure")
    decision = _get(cycle, "decision")
    ai_result = _get(cycle, "ai_result")
    execution_gate = _get(cycle, "execution_gate")
    trade_execution = _get(cycle, "trade_execution")
    profit_manager = _get(cycle, "profit_manager")

    price = _first(snapshot, ["price"], default="")

    session_obj = _get(snapshot, "session")
    session = _first(
        session_obj,
        ["name", "primary_session", "primary"],
        default="",
    )

    if not session:
        session = _first(snapshot, ["primary_session", "session_name"], default="")

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "runtime_seconds": _get(cycle, "runtime_seconds", ""),
        "runtime_ms": _get(cycle, "runtime_ms", ""),

        "cycle_success": _get(cycle, "success", ""),
        "error_message": _get(cycle, "error_message", ""),

        "symbol": _first(snapshot, ["symbol"], default=""),
        "price": _format_price_value(price),
        "session": session,

        "market_trade_allowed": _first(
            conditions,
            ["trade_allowed", "is_safe", "spread_safe"],
            default="",
        ),
        "price_valid": _first(conditions, ["price_valid"], default=""),
        "candles_loaded": _first(conditions, ["candles_loaded"], default=""),
        "spread_safe": _first(conditions, ["spread_safe"], default=""),
        "session_active": _first(conditions, ["session_active"], default=""),

        "overall_trend": _first(
            trend,
            ["overall_trend", "direction", "trend"],
            default="",
        ),
        "trend_confidence": _first(
            trend,
            ["trend_confidence", "confidence", "strength"],
            default="",
        ),

        "overall_volatility": _first(
            volatility,
            ["overall_volatility", "level"],
            default="",
        ),
        "volatility_risk_level": _first(
            volatility,
            ["trade_risk_level", "risk_level", "risk"],
            default="",
        ),
        "volatility_confidence": _first(
            volatility,
            ["volatility_confidence", "confidence"],
            default="",
        ),

        "structure_bias": _first(
            structure,
            ["structure_bias", "bias"],
            default="",
        ),
        "structure_confidence": _first(
            structure,
            ["structure_confidence", "confidence"],
            default="",
        ),
        "nearest_support": _first(structure, ["nearest_support"], default=""),
        "nearest_resistance": _first(structure, ["nearest_resistance"], default=""),

        "decision_action": _first(
            decision,
            ["action", "decision"],
            default="",
        ),
        "decision_trade_allowed": _first(
            decision,
            ["trade_allowed", "can_trade"],
            default="",
        ),
        "decision_confidence": _first(
            decision,
            ["confidence", "decision_confidence"],
            default="",
        ),

        "ai_action": _first(
            ai_result,
            ["ai_action", "action"],
            default="",
        ),
        "ai_bias": _first(ai_result, ["bias"], default=""),
        "ai_can_trade": _first(ai_result, ["can_trade", "trade_allowed"], default=""),
        "ai_confidence": _first(ai_result, ["confidence", "ai_confidence"], default=""),
        "ai_explanation": _first(ai_result, ["explanation", "reason"], default=""),

        "gate_allowed": _first(
            execution_gate,
            ["allowed", "allowed_to_execute", "can_execute"],
            default="",
        ),
        "gate_reason": _first(
            execution_gate,
            ["reason", "message"],
            default="",
        ),

        "trade_attempted": _first(
            trade_execution,
            ["attempted", "trade_attempted"],
            default="",
        ),
        "trade_success": _first(
            trade_execution,
            ["success", "trade_success"],
            default="",
        ),
        "trade_message": _first(
            trade_execution,
            ["message", "reason"],
            default="",
        ),

        "dry_run_action": _first(
            trade_execution,
            ["dry_run_action"],
            default="",
        ),
        "dry_run_direction": _first(
            trade_execution,
            ["dry_run_direction"],
            default="",
        ),
        "dry_run_reason": _first(
            trade_execution,
            ["dry_run_reason"],
            default="",
        ),

        "profit_action": _first(
            profit_manager,
            ["action", "status"],
            default="",
        ),
        "profit_message": _first(
            profit_manager,
            ["message", "reason"],
            default="",
        ),
    }


def log_bot_cycle(cycle):
    file_path = get_daily_cycle_log_path()
    row = _build_cycle_row(cycle)

    file_exists = file_path.exists()

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=row.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    print(f"Cycle logged to: {file_path}")

    return str(file_path)


# Compatibility aliases
def log_cycle(cycle):
    return log_bot_cycle(cycle)


def save_cycle_log(cycle):
    return log_bot_cycle(cycle)