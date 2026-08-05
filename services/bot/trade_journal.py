import csv
import os
from datetime import datetime

from config import settings


TRADE_JOURNAL_FIELDS = [
    "timestamp",
    "symbol",
    "decision_action",
    "decision_trade_allowed",
    "decision_confidence",
    "ai_action",
    "ai_can_trade",
    "ai_confidence",
    "gate_allowed",
    "gate_reason",
    "trade_attempted",
    "trade_success",
    "trade_message",
    "dry_run_action",
    "dry_run_direction",
    "dry_run_reason",
    "profit_action",
    "profit_message",
    "paper_trade_action",
    "paper_trade_message",
    "paper_trade_opened",
    "paper_trade_closed",
    "paper_trade_open_count",
    "paper_trade_profit",
    "runtime_seconds",
]


def _get_value(source, *keys, default=""):
    """
    Safely read values from either dictionaries or objects.
    """
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
    if isinstance(value, bool):
        return "YES" if value else "NO"

    if value is None:
        return ""

    return str(value)


def _get_log_folder():
    """
    Creates:
    logs/YYYY-MM-DD/
    when USE_DAILY_LOG_FOLDERS = True
    """
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def get_trade_journal_path():
    log_folder = _get_log_folder()
    return os.path.join(log_folder, "trade_journal.csv")


def _get_section(cycle, *possible_names):
    for name in possible_names:
        section = _get_value(cycle, name, default=None)
        if section is not None:
            return section

    return None


def build_trade_journal_row(cycle):
    """
    Builds one journal row from the completed bot cycle.
    Works with dictionaries and BotCycleState objects.
    """

    decision = _get_section(
        cycle,
        "decision",
        "trade_decision",
        "decision_result",
    )

    ai_result = _get_section(
        cycle,
        "ai_result",
        "ai_brain_result",
        "ai_decision",
    )

    execution_gate = _get_section(
        cycle,
        "execution_gate",
        "gate_result",
        "gate",
    )

    trade_result = _get_section(
        cycle,
        "trade_result",
        "execution_result",
        "trade_execution",
    )

    dry_run_plan = _get_section(
        cycle,
        "dry_run_plan",
        "dry_run_trade_plan",
        "dry_run_result",
    )

    profit_result = _get_section(
        cycle,
        "profit_result",
        "profit_manager_result",
        "profit_manager",
    )

    paper_trade_result = _get_section(
        cycle,
        "paper_trade_result",
        "paper_trade",
        "paper_manager_result",
    )

    row = {
        "timestamp": _get_value(
            cycle,
            "timestamp",
            "cycle_timestamp",
            default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),

        "symbol": _get_value(
            cycle,
            "symbol",
            default=getattr(settings, "SYMBOL", "UNKNOWN"),
        ),

        "decision_action": _get_value(
            decision,
            "action",
            "decision_action",
            "trade_action",
            default="UNKNOWN",
        ),

        "decision_trade_allowed": _yes_no(
            _get_value(
                decision,
                "trade_allowed",
                "can_trade",
                "allowed",
                default="",
            )
        ),

        "decision_confidence": _get_value(
            decision,
            "confidence",
            "decision_confidence",
            default="",
        ),

        "ai_action": _get_value(
            ai_result,
            "action",
            "ai_action",
            default="UNKNOWN",
        ),

        "ai_can_trade": _yes_no(
            _get_value(
                ai_result,
                "can_trade",
                "trade_allowed",
                default="",
            )
        ),

        "ai_confidence": _get_value(
            ai_result,
            "confidence",
            "ai_confidence",
            default="",
        ),

        "gate_allowed": _yes_no(
            _get_value(
                execution_gate,
                "allowed",
                "gate_allowed",
                default="",
            )
        ),

        "gate_reason": _get_value(
            execution_gate,
            "reason",
            "message",
            "gate_reason",
            default="",
        ),

        "trade_attempted": _yes_no(
            _get_value(
                trade_result,
                "attempted",
                "trade_attempted",
                default=_get_value(cycle, "trade_attempted", default=""),
            )
        ),

        "trade_success": _yes_no(
            _get_value(
                trade_result,
                "success",
                "trade_success",
                default=_get_value(cycle, "trade_success", default=""),
            )
        ),

        "trade_message": _get_value(
            trade_result,
            "message",
            "trade_message",
            "reason",
            default="",
        ),

        "dry_run_action": _get_value(
            dry_run_plan,
            "action",
            "dry_run_action",
            default="",
        ),

        "dry_run_direction": _get_value(
            dry_run_plan,
            "direction",
            "dry_run_direction",
            default="",
        ),

        "dry_run_reason": _get_value(
            dry_run_plan,
            "reason",
            "message",
            "dry_run_reason",
            default="",
        ),

        "profit_action": _get_value(
            profit_result,
            "action",
            "profit_action",
            default="",
        ),

        "profit_message": _get_value(
            profit_result,
            "message",
            "profit_message",
            default="",
        ),

        "paper_trade_action": _get_value(
            paper_trade_result,
            "action",
            default="",
        ),

        "paper_trade_message": _get_value(
            paper_trade_result,
            "message",
            default="",
        ),

        "paper_trade_opened": _yes_no(
            _get_value(
                paper_trade_result,
                "opened_trade",
                default="",
            )
        ),

        "paper_trade_closed": _yes_no(
            _get_value(
                paper_trade_result,
                "closed_trade",
                default="",
            )
        ),

        "paper_trade_open_count": _get_value(
            paper_trade_result,
            "open_paper_trades",
            default="",
        ),

        "paper_trade_profit": _get_value(
            paper_trade_result,
            "paper_profit",
            default="",
        ),

        "runtime_seconds": _get_value(
            cycle,
            "runtime_seconds",
            "runtime",
            default="",
        ),
    }

    return row


def log_trade_journal_entry(cycle):
    """
    Saves one trade journal row into:
    logs/YYYY-MM-DD/trade_journal.csv
    """

    journal_path = get_trade_journal_path()
    file_exists = os.path.exists(journal_path)

    row = build_trade_journal_row(cycle)

    with open(journal_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=TRADE_JOURNAL_FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    return journal_path