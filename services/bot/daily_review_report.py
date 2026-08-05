import csv
import os
from collections import Counter
from datetime import datetime

from config import settings
from services.execution.paper_trade_report import build_paper_trade_report
from services.bot.live_readiness_checker import check_live_readiness
from services.risk.advanced_risk_engine import evaluate_advanced_risk


def _get_log_folder():
    base_log_path = getattr(settings, "LOG_FILE_PATH", "logs/bot_cycle_log.csv")
    base_log_folder = os.path.dirname(base_log_path) or "logs"

    if getattr(settings, "USE_DAILY_LOG_FOLDERS", False):
        date_format = getattr(settings, "LOG_DATE_FORMAT", "%Y-%m-%d")
        today_folder = datetime.now().strftime(date_format)
        base_log_folder = os.path.join(base_log_folder, today_folder)

    os.makedirs(base_log_folder, exist_ok=True)
    return base_log_folder


def _load_csv(file_name):
    path = os.path.join(_get_log_folder(), file_name)

    if not os.path.exists(path):
        return [], path

    try:
        with open(path, mode="r", newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file)), path
    except Exception:
        return [], path


def _count_values(rows, column):
    return Counter(row.get(column, "") for row in rows)


def _count_non_empty(rows, column):
    return sum(1 for row in rows if row.get(column, ""))


def get_daily_review_report_path():
    return os.path.join(_get_log_folder(), "daily_review_report.txt")


def build_daily_review_report():
    symbol = getattr(settings, "SYMBOL", "XAUUSD")

    forward_rows, forward_path = _load_csv("forward_validation_log.csv")
    journal_rows, journal_path = _load_csv("trade_journal.csv")
    decision_rows, decision_path = _load_csv("decision_quality_log.csv")
    risk_rows, risk_path = _load_csv("risk_engine_log.csv")
    news_rows, news_path = _load_csv("news_risk_log.csv")

    paper_report = build_paper_trade_report(symbol)
    live_readiness = check_live_readiness(symbol)
    advanced_risk = evaluate_advanced_risk(symbol)

    decision_counts = _count_values(forward_rows, "decision_action")
    ai_counts = _count_values(forward_rows, "ai_action")
    dry_run_counts = _count_values(forward_rows, "dry_run_action")
    paper_action_counts = _count_values(forward_rows, "paper_trade_action")
    quality_counts = _count_values(forward_rows, "trade_quality")

    risk_block_count = sum(
        1 for row in risk_rows
        if row.get("advanced_risk_allowed", "") in ["NO", "False", "false"]
    )

    slippage_block_count = sum(
        1 for row in risk_rows
        if row.get("slippage_allowed", "") in ["NO", "False", "false"]
    )

    news_block_count = sum(
        1 for row in news_rows
        if row.get("news_allowed", "") in ["NO", "False", "false"]
    )

    cycle_error_count = _count_non_empty(forward_rows, "error_message")

    recommendations = []

    if cycle_error_count > 0:
        recommendations.append("Fix cycle errors before increasing validation cycles.")

    if paper_report.get("closed_paper_trades", 0) < getattr(settings, "MIN_CLOSED_PAPER_TRADES_FOR_LIVE", 20):
        recommendations.append("Keep collecting paper trades. Not enough closed paper trades yet.")

    if paper_report.get("win_rate_percent", 0.0) < getattr(settings, "MIN_PAPER_WIN_RATE_FOR_LIVE", 55.0):
        recommendations.append("Paper win rate is below live-readiness requirement.")

    if paper_report.get("realized_profit_usd", 0.0) <= 0:
        recommendations.append("Paper realized profit is not positive yet.")

    if decision_counts.get("WAIT", 0) > 0 and decision_counts.get("READY_FOR_BUY_ANALYSIS", 0) == 0 and decision_counts.get("READY_FOR_SELL_ANALYSIS", 0) == 0:
        recommendations.append("The bot is only waiting. Review whether filters are too strict or market conditions were weak.")

    if risk_block_count > 0:
        recommendations.append("Advanced risk blocked some cycles. Review risk_engine_log.csv.")

    if slippage_block_count > 0:
        recommendations.append("Slippage blocked some cycles. Review MAX_SLIPPAGE_USD.")

    if news_block_count > 0:
        recommendations.append("News filter blocked some cycles. Review news_risk_log.csv and economic_events.json.")

    if not recommendations:
        recommendations.append("No urgent issues detected in today's paper review.")

    lines = [
        "=" * 70,
        "DAILY PAPER TRADING REVIEW REPORT",
        "=" * 70,
        f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Symbol: {symbol}",
        f"Log Folder: {_get_log_folder()}",
        "-" * 70,
        "SOURCE FILES",
        f"Forward Validation: {forward_path}",
        f"Trade Journal: {journal_path}",
        f"Decision Quality: {decision_path}",
        f"Risk Engine: {risk_path}",
        f"News Risk: {news_path}",
        "-" * 70,
        "PAPER PERFORMANCE",
        f"Total Paper Trades: {paper_report.get('total_paper_trades')}",
        f"Open Paper Trades: {paper_report.get('open_paper_trades')}",
        f"Closed Paper Trades: {paper_report.get('closed_paper_trades')}",
        f"Winning Trades: {paper_report.get('winning_trades')}",
        f"Losing Trades: {paper_report.get('losing_trades')}",
        f"Realized Profit USD: {paper_report.get('realized_profit_usd')}",
        f"Unrealized Profit USD: {paper_report.get('unrealized_profit_usd')}",
        f"Win Rate: {paper_report.get('win_rate_percent')}%",
        "-" * 70,
        "FORWARD VALIDATION",
        f"Cycles Reviewed: {len(forward_rows)}",
        f"Cycle Errors: {cycle_error_count}",
        f"Decision Counts: {dict(decision_counts)}",
        f"AI Counts: {dict(ai_counts)}",
        f"Dry Run Counts: {dict(dry_run_counts)}",
        f"Paper Action Counts: {dict(paper_action_counts)}",
        f"Trade Quality Counts: {dict(quality_counts)}",
        "-" * 70,
        "RISK / NEWS",
        f"Advanced Risk Allowed: {advanced_risk.get('allowed')}",
        f"Advanced Risk Action: {advanced_risk.get('action')}",
        f"Daily Realized P/L: {advanced_risk.get('daily_realized_profit')}",
        f"Daily Trade Count: {advanced_risk.get('daily_trade_count')}",
        f"Consecutive Losses: {advanced_risk.get('consecutive_losses')}",
        f"Max Drawdown: {advanced_risk.get('max_drawdown')}",
        f"Risk Block Count: {risk_block_count}",
        f"Slippage Block Count: {slippage_block_count}",
        f"News Block Count: {news_block_count}",
        "-" * 70,
        "LIVE READINESS",
        f"Ready For Review: {live_readiness.get('ready_for_review')}",
        f"Closed Paper Trades: {live_readiness.get('closed_paper_trades')}",
        f"Paper Win Rate: {live_readiness.get('paper_win_rate')}%",
        f"Paper Realized Profit: {live_readiness.get('paper_realized_profit')}",
        f"Blockers: {live_readiness.get('blockers')}",
        f"Warnings: {live_readiness.get('warnings')}",
        "-" * 70,
        "RECOMMENDATIONS",
    ]

    for item in recommendations:
        lines.append(f"- {item}")

    lines.append("=" * 70)

    return {
        "success": True,
        "report_lines": lines,
        "report_path": get_daily_review_report_path(),
        "recommendations": recommendations,
    }


def save_daily_review_report():
    result = build_daily_review_report()
    report_path = result["report_path"]

    with open(report_path, mode="w", encoding="utf-8") as file:
        file.write("\n".join(result["report_lines"]))

    return result