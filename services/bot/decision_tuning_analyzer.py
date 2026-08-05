import csv
import os
from collections import Counter
from datetime import datetime

from config import settings


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    return base_log_folder


def get_forward_validation_log_path():
    return os.path.join(_get_log_folder(), "forward_validation_log.csv")


def get_decision_tuning_report_path():
    return os.path.join(_get_log_folder(), "decision_tuning_report.txt")


def _safe_float(value, default=0.0):
    try:
        if value in ["", None]:
            return default
        return float(value)
    except Exception:
        return default


def _load_forward_validation_rows():
    path = get_forward_validation_log_path()

    if not os.path.exists(path):
        return [], path

    with open(path, mode="r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return list(reader), path


def analyze_forward_validation():
    rows, source_path = _load_forward_validation_rows()

    if not rows:
        return {
            "success": False,
            "source_path": source_path,
            "message": "No forward validation rows found.",
            "report_lines": [],
        }

    total_cycles = len(rows)

    success_counter = Counter(row.get("success", "") for row in rows)
    decision_counter = Counter(row.get("decision_action", "") for row in rows)
    ai_counter = Counter(row.get("ai_action", "") for row in rows)
    dry_run_counter = Counter(row.get("dry_run_action", "") for row in rows)
    paper_trade_counter = Counter(row.get("paper_trade_action", "") for row in rows)
    trade_quality_counter = Counter(row.get("trade_quality", "") for row in rows)

    risk_allowed_counter = Counter(str(row.get("advanced_risk_allowed", "")) for row in rows)
    slippage_allowed_counter = Counter(str(row.get("slippage_allowed", "")) for row in rows)

    trade_scores = [
        _safe_float(row.get("trade_score"))
        for row in rows
        if row.get("trade_score") not in ["", None]
    ]

    avg_trade_score = 0.0
    min_trade_score = 0.0
    max_trade_score = 0.0

    if trade_scores:
        avg_trade_score = round(sum(trade_scores) / len(trade_scores), 2)
        min_trade_score = round(min(trade_scores), 2)
        max_trade_score = round(max(trade_scores), 2)

    errors = [
        row.get("error_message", "")
        for row in rows
        if row.get("error_message", "")
    ]

    wait_count = decision_counter.get("WAIT", 0)
    buy_count = decision_counter.get("READY_FOR_BUY_ANALYSIS", 0)
    sell_count = decision_counter.get("READY_FOR_SELL_ANALYSIS", 0)

    no_trade_count = dry_run_counter.get("NO_TRADE", 0)
    would_buy_count = dry_run_counter.get("WOULD_BUY", 0)
    would_sell_count = dry_run_counter.get("WOULD_SELL", 0)

    recommendations = []

    wait_ratio = wait_count / total_cycles if total_cycles else 0
    no_trade_ratio = no_trade_count / total_cycles if total_cycles else 0

    if errors:
        recommendations.append("Fix cycle errors before tuning strategy settings.")

    if wait_ratio > 0.90:
        recommendations.append(
            "The bot is waiting more than 90% of the time. This may be okay, but review whether filters are too strict."
        )

    if avg_trade_score < getattr(settings, "MIN_TRADE_SCORE", 70):
        recommendations.append(
            "Average trade score is below MIN_TRADE_SCORE. Keep strict settings, but review trend/structure logic."
        )

    if would_buy_count == 0 and would_sell_count == 0:
        recommendations.append(
            "No paper BUY/SELL setups were created. More forward validation or slightly less strict filters may be needed."
        )

    if risk_allowed_counter.get("False", 0) > 0:
        recommendations.append(
            "Advanced risk blocked some cycles. Review risk_engine_log.csv before changing limits."
        )

    if slippage_allowed_counter.get("False", 0) > 0:
        recommendations.append(
            "Slippage guard blocked some cycles. Review MAX_SLIPPAGE_USD and market speed."
        )

    if not recommendations:
        recommendations.append("No major tuning problem detected from this validation run.")

    report_lines = [
        "=" * 70,
        "DECISION TUNING REPORT",
        "=" * 70,
        f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Source File: {source_path}",
        f"Symbol: {getattr(settings, 'SYMBOL', 'XAUUSD')}",
        "-" * 70,
        "SUMMARY",
        f"Total Cycles: {total_cycles}",
        f"Successful Cycles: {success_counter.get('True', 0)}",
        f"Failed Cycles: {success_counter.get('False', 0)}",
        f"Average Trade Score: {avg_trade_score}",
        f"Min Trade Score: {min_trade_score}",
        f"Max Trade Score: {max_trade_score}",
        "-" * 70,
        "DECISIONS",
        f"WAIT: {wait_count}",
        f"READY_FOR_BUY_ANALYSIS: {buy_count}",
        f"READY_FOR_SELL_ANALYSIS: {sell_count}",
        "-" * 70,
        "AI ACTIONS",
    ]

    for key, value in ai_counter.items():
        report_lines.append(f"{key}: {value}")

    report_lines.extend([
        "-" * 70,
        "DRY RUN ACTIONS",
        f"NO_TRADE: {no_trade_count}",
        f"WOULD_BUY: {would_buy_count}",
        f"WOULD_SELL: {would_sell_count}",
        "-" * 70,
        "PAPER TRADE ACTIONS",
    ])

    for key, value in paper_trade_counter.items():
        report_lines.append(f"{key}: {value}")

    report_lines.extend([
        "-" * 70,
        "TRADE QUALITY",
    ])

    for key, value in trade_quality_counter.items():
        report_lines.append(f"{key}: {value}")

    report_lines.extend([
        "-" * 70,
        "RISK / SLIPPAGE",
        f"Advanced Risk Allowed Counts: {dict(risk_allowed_counter)}",
        f"Slippage Allowed Counts: {dict(slippage_allowed_counter)}",
        "-" * 70,
        "ERRORS",
    ])

    if errors:
        for error in errors:
            report_lines.append(f"[ERROR] {error}")
    else:
        report_lines.append("No cycle errors found.")

    report_lines.extend([
        "-" * 70,
        "RECOMMENDATIONS",
    ])

    for item in recommendations:
        report_lines.append(f"- {item}")

    report_lines.extend([
        "=" * 70,
    ])

    return {
        "success": True,
        "source_path": source_path,
        "total_cycles": total_cycles,
        "average_trade_score": avg_trade_score,
        "wait_count": wait_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "would_buy_count": would_buy_count,
        "would_sell_count": would_sell_count,
        "recommendations": recommendations,
        "report_lines": report_lines,
    }


def save_decision_tuning_report():
    result = analyze_forward_validation()
    report_path = get_decision_tuning_report_path()

    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    with open(report_path, mode="w", encoding="utf-8") as file:
        if result.get("report_lines"):
            file.write("\n".join(result["report_lines"]))
        else:
            file.write(result.get("message", "No report generated."))

    result["report_path"] = report_path
    return result