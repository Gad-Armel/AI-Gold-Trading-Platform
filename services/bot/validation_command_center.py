from config import settings

from services.bot.system_auditor import run_system_audit
from services.execution.paper_trade_report import build_paper_trade_report
from services.bot.decision_tuning_analyzer import save_decision_tuning_report
from services.risk.advanced_risk_engine import evaluate_advanced_risk
from services.bot.live_readiness_checker import check_live_readiness
from dashboard.paper_trade_dashboard import generate_paper_trade_dashboard


def run_validation_command_center():
    symbol = getattr(settings, "SYMBOL", "XAUUSD")

    results = {}

    results["system_audit"] = run_system_audit()
    results["paper_report"] = build_paper_trade_report(symbol)
    results["decision_tuning"] = save_decision_tuning_report()
    results["advanced_risk"] = evaluate_advanced_risk(symbol)
    results["live_readiness"] = check_live_readiness(symbol)

    try:
        results["dashboard"] = generate_paper_trade_dashboard(open_browser=False)
    except Exception as error:
        results["dashboard"] = {
            "success": False,
            "error": str(error),
        }

    return results


def print_validation_command_center_report(results=None):
    if results is None:
        results = run_validation_command_center()

    audit = results.get("system_audit", {})
    paper = results.get("paper_report", {})
    tuning = results.get("decision_tuning", {})
    risk = results.get("advanced_risk", {})
    readiness = results.get("live_readiness", {})
    dashboard = results.get("dashboard", {})

    print("")
    print("=" * 70)
    print("VALIDATION COMMAND CENTER")
    print("=" * 70)

    print(f"Symbol: {getattr(settings, 'SYMBOL', 'XAUUSD')}")
    print(f"ENABLE_LIVE_TRADING: {getattr(settings, 'ENABLE_LIVE_TRADING', False)}")
    print(f"EMERGENCY_STOP: {getattr(settings, 'EMERGENCY_STOP', False)}")
    print(f"LIVE_TRADING_CONFIRMATION: {getattr(settings, 'LIVE_TRADING_CONFIRMATION', '') or 'EMPTY'}")

    print("-" * 70)
    print("SYSTEM AUDIT")
    print(f"Audit Passed: {audit.get('audit_passed')}")
    print(f"Critical Failures: {audit.get('critical_failures')}")

    print("-" * 70)
    print("PAPER PERFORMANCE")
    print(f"Total Paper Trades: {paper.get('total_paper_trades')}")
    print(f"Open Paper Trades: {paper.get('open_paper_trades')}")
    print(f"Closed Paper Trades: {paper.get('closed_paper_trades')}")
    print(f"Winning Trades: {paper.get('winning_trades')}")
    print(f"Losing Trades: {paper.get('losing_trades')}")
    print(f"Realized Profit USD: {paper.get('realized_profit_usd')}")
    print(f"Unrealized Profit USD: {paper.get('unrealized_profit_usd')}")
    print(f"Win Rate: {paper.get('win_rate_percent')}%")

    print("-" * 70)
    print("DECISION TUNING")
    print(f"Report Created: {tuning.get('success')}")
    print(f"Report File: {tuning.get('report_path')}")
    print(f"Total Cycles Reviewed: {tuning.get('total_cycles')}")
    print(f"Average Trade Score: {tuning.get('average_trade_score')}")
    print(f"WAIT Count: {tuning.get('wait_count')}")
    print(f"WOULD_BUY Count: {tuning.get('would_buy_count')}")
    print(f"WOULD_SELL Count: {tuning.get('would_sell_count')}")

    print("-" * 70)
    print("ADVANCED RISK")
    print(f"Risk Allowed: {risk.get('allowed')}")
    print(f"Risk Action: {risk.get('action')}")
    print(f"Daily Realized P/L: {risk.get('daily_realized_profit')}")
    print(f"Daily Trade Count: {risk.get('daily_trade_count')}")
    print(f"Consecutive Losses: {risk.get('consecutive_losses')}")
    print(f"Max Drawdown: {risk.get('max_drawdown')}")
    print(f"Risk Block Reasons: {risk.get('block_reasons')}")

    print("-" * 70)
    print("LIVE READINESS")
    print(f"Ready For Review: {readiness.get('ready_for_review')}")
    print(f"Closed Paper Trades: {readiness.get('closed_paper_trades')}")
    print(f"Paper Win Rate: {readiness.get('paper_win_rate')}%")
    print(f"Paper Realized Profit: {readiness.get('paper_realized_profit')}")
    print(f"Blockers: {readiness.get('blockers')}")
    print(f"Warnings: {readiness.get('warnings')}")

    print("-" * 70)
    print("DASHBOARD")
    print(f"Dashboard Updated: {dashboard.get('success')}")
    print(f"Dashboard File: {dashboard.get('file_path', dashboard.get('error', 'N/A'))}")

    print("=" * 70)

    if readiness.get("ready_for_review"):
        print("STATUS: READY FOR LIVE REVIEW ONLY. LIVE TRADING IS STILL DISABLED.")
    else:
        print("STATUS: NOT READY FOR LIVE TRADING YET.")

    print("=" * 70)
    print("")

    return results