from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Any

from config import scalping_settings
from services.bot.scalping_performance_report import build_scalping_performance_report
from services.bot.scalping_trade_repository import get_scalping_log_root
from services.risk.scalping_risk_guard import get_scalping_log_folder


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value == "INF":
        return 999.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _cycle_health() -> dict[str, Any]:
    root = get_scalping_log_root()
    file_name = str(
        getattr(
            scalping_settings,
            "SCALPING_CYCLE_LOG_FILENAME",
            "scalp_cycle_log.csv",
        )
    )
    files: list[str] = []
    if os.path.exists(root):
        for current_root, _, names in os.walk(root):
            if file_name in names:
                files.append(os.path.join(current_root, file_name))

    cycles = 0
    failed = 0
    errors = 0
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", newline="") as file:
                for row in csv.DictReader(file):
                    cycles += 1
                    success = str(row.get("success", "")).strip().lower()
                    if success not in {"true", "1", "yes"}:
                        failed += 1
                    if str(row.get("error_message", "")).strip():
                        errors += 1
        except OSError:
            errors += 1

    error_rate = errors / cycles * 100.0 if cycles else 0.0
    return {
        "cycle_files": len(files),
        "cycles": cycles,
        "failed_cycles": failed,
        "cycles_with_errors": errors,
        "error_rate_percent": round(error_rate, 3),
    }


def _criterion(name: str, actual: Any, required: str, passed: bool) -> dict[str, Any]:
    return {
        "name": name,
        "actual": actual,
        "required": required,
        "passed": bool(passed),
    }


def _stage(
    name: str,
    summary: dict[str, Any],
    data_quality_valid: bool,
    cycle_health: dict[str, Any],
    *,
    minimum_trades: int,
    minimum_days: int,
    minimum_win_rate: float,
    minimum_profit_factor: float,
    maximum_drawdown: float,
    maximum_losing_streak: int,
    maximum_cycle_error_rate: float,
) -> dict[str, Any]:
    profit_factor = _safe_float(summary.get("profit_factor"), 0.0)
    criteria = [
        _criterion(
            "Closed trades",
            summary.get("closed_trades", 0),
            f">= {minimum_trades}",
            int(summary.get("closed_trades", 0)) >= minimum_trades,
        ),
        _criterion(
            "Active trading days",
            summary.get("active_trading_days", 0),
            f">= {minimum_days}",
            int(summary.get("active_trading_days", 0)) >= minimum_days,
        ),
        _criterion(
            "Win rate",
            summary.get("win_rate", 0.0),
            f">= {minimum_win_rate:.2f}%",
            float(summary.get("win_rate", 0.0)) >= minimum_win_rate,
        ),
        _criterion(
            "Net profit",
            summary.get("net_profit_usd", 0.0),
            "> $0.00",
            float(summary.get("net_profit_usd", 0.0)) > 0.0,
        ),
        _criterion(
            "Profit factor",
            summary.get("profit_factor"),
            f">= {minimum_profit_factor:.2f}",
            profit_factor >= minimum_profit_factor,
        ),
        _criterion(
            "Expectancy",
            summary.get("expectancy_usd", 0.0),
            "> $0.00 per trade",
            float(summary.get("expectancy_usd", 0.0)) > 0.0,
        ),
        _criterion(
            "Maximum drawdown",
            summary.get("max_drawdown_usd", 0.0),
            f"<= ${maximum_drawdown:.2f}",
            float(summary.get("max_drawdown_usd", 0.0)) <= maximum_drawdown,
        ),
        _criterion(
            "Maximum losing streak",
            summary.get("max_losing_streak", 0),
            f"<= {maximum_losing_streak}",
            int(summary.get("max_losing_streak", 0)) <= maximum_losing_streak,
        ),
        _criterion(
            "Cycle error rate",
            cycle_health.get("error_rate_percent", 0.0),
            f"<= {maximum_cycle_error_rate:.2f}%",
            float(cycle_health.get("error_rate_percent", 0.0))
            <= maximum_cycle_error_rate,
        ),
        _criterion(
            "Trade data quality",
            data_quality_valid,
            "VALID",
            data_quality_valid,
        ),
    ]
    blockers = [
        f"{item['name']}: actual={item['actual']} required={item['required']}"
        for item in criteria
        if not item["passed"]
    ]
    return {
        "name": name,
        "passed": len(blockers) == 0,
        "criteria": criteria,
        "blockers": blockers,
    }


def build_scalping_readiness_report(
    performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    performance = performance or build_scalping_performance_report()
    summary = performance["summary"]
    quality_valid = bool(performance["data_quality"]["valid"])
    health = _cycle_health()

    stages = {
        "baseline_complete": _stage(
            "Baseline Paper Validation",
            summary,
            quality_valid,
            health,
            minimum_trades=int(
                getattr(scalping_settings, "SCALPING_BASELINE_MIN_CLOSED_TRADES", 50)
            ),
            minimum_days=int(
                getattr(scalping_settings, "SCALPING_BASELINE_MIN_ACTIVE_DAYS", 3)
            ),
            minimum_win_rate=float(
                getattr(scalping_settings, "SCALPING_BASELINE_MIN_WIN_RATE", 55.0)
            ),
            minimum_profit_factor=float(
                getattr(scalping_settings, "SCALPING_BASELINE_MIN_PROFIT_FACTOR", 1.10)
            ),
            maximum_drawdown=float(
                getattr(scalping_settings, "SCALPING_BASELINE_MAX_DRAWDOWN_USD", 15.0)
            ),
            maximum_losing_streak=int(
                getattr(scalping_settings, "SCALPING_BASELINE_MAX_LOSING_STREAK", 4)
            ),
            maximum_cycle_error_rate=float(
                getattr(scalping_settings, "SCALPING_MAX_CYCLE_ERROR_RATE_PERCENT", 2.0)
            ),
        ),
        "two_position_review": _stage(
            "Two Paper Positions Review",
            summary,
            quality_valid,
            health,
            minimum_trades=int(
                getattr(scalping_settings, "SCALPING_TWO_POSITION_MIN_TRADES", 100)
            ),
            minimum_days=int(
                getattr(scalping_settings, "SCALPING_TWO_POSITION_MIN_DAYS", 5)
            ),
            minimum_win_rate=float(
                getattr(scalping_settings, "SCALPING_TWO_POSITION_MIN_WIN_RATE", 55.0)
            ),
            minimum_profit_factor=float(
                getattr(scalping_settings, "SCALPING_TWO_POSITION_MIN_PROFIT_FACTOR", 1.20)
            ),
            maximum_drawdown=float(
                getattr(scalping_settings, "SCALPING_TWO_POSITION_MAX_DRAWDOWN_USD", 15.0)
            ),
            maximum_losing_streak=int(
                getattr(scalping_settings, "SCALPING_TWO_POSITION_MAX_LOSING_STREAK", 4)
            ),
            maximum_cycle_error_rate=float(
                getattr(scalping_settings, "SCALPING_MAX_CYCLE_ERROR_RATE_PERCENT", 2.0)
            ),
        ),
        "three_position_review": _stage(
            "Three Paper Positions Review",
            summary,
            quality_valid,
            health,
            minimum_trades=int(
                getattr(scalping_settings, "SCALPING_THREE_POSITION_MIN_TRADES", 200)
            ),
            minimum_days=int(
                getattr(scalping_settings, "SCALPING_THREE_POSITION_MIN_DAYS", 10)
            ),
            minimum_win_rate=float(
                getattr(scalping_settings, "SCALPING_THREE_POSITION_MIN_WIN_RATE", 57.0)
            ),
            minimum_profit_factor=float(
                getattr(scalping_settings, "SCALPING_THREE_POSITION_MIN_PROFIT_FACTOR", 1.25)
            ),
            maximum_drawdown=float(
                getattr(scalping_settings, "SCALPING_THREE_POSITION_MAX_DRAWDOWN_USD", 20.0)
            ),
            maximum_losing_streak=int(
                getattr(scalping_settings, "SCALPING_THREE_POSITION_MAX_LOSING_STREAK", 4)
            ),
            maximum_cycle_error_rate=float(
                getattr(scalping_settings, "SCALPING_MAX_CYCLE_ERROR_RATE_PERCENT", 2.0)
            ),
        ),
        "demo_review": _stage(
            "Controlled MT5 Demo Review",
            summary,
            quality_valid,
            health,
            minimum_trades=int(
                getattr(scalping_settings, "SCALPING_DEMO_MIN_PAPER_TRADES", 150)
            ),
            minimum_days=int(
                getattr(scalping_settings, "SCALPING_DEMO_MIN_ACTIVE_DAYS", 7)
            ),
            minimum_win_rate=float(
                getattr(scalping_settings, "SCALPING_DEMO_MIN_WIN_RATE", 55.0)
            ),
            minimum_profit_factor=float(
                getattr(scalping_settings, "SCALPING_DEMO_MIN_PROFIT_FACTOR", 1.20)
            ),
            maximum_drawdown=float(
                getattr(scalping_settings, "SCALPING_DEMO_MAX_DRAWDOWN_USD", 15.0)
            ),
            maximum_losing_streak=int(
                getattr(scalping_settings, "SCALPING_DEMO_MAX_LOSING_STREAK", 3)
            ),
            maximum_cycle_error_rate=float(
                getattr(scalping_settings, "SCALPING_DEMO_MAX_CYCLE_ERROR_RATE_PERCENT", 1.0)
            ),
        ),
    }

    if stages["three_position_review"]["passed"]:
        current_recommendation = "Eligible for manual review of up to three paper positions."
    elif stages["two_position_review"]["passed"]:
        current_recommendation = "Eligible for manual review of up to two paper positions."
    elif stages["baseline_complete"]["passed"]:
        current_recommendation = "Baseline complete; continue one-position validation."
    else:
        current_recommendation = "Continue one-position paper scalping with unchanged parameters."

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy_id": performance["strategy_id"],
        "summary": summary,
        "cycle_health": health,
        "stages": stages,
        "recommendation": current_recommendation,
        "demo_execution_should_remain_disabled": not stages["demo_review"]["passed"],
        "automatic_setting_changes_applied": False,
    }


def save_scalping_readiness_report(
    report: dict[str, Any] | None = None,
) -> dict[str, str]:
    report = report or build_scalping_readiness_report()
    folder = get_scalping_log_folder()
    os.makedirs(folder, exist_ok=True)
    text_path = os.path.join(folder, "scalping_readiness_report.txt")
    json_path = os.path.join(folder, "scalping_readiness_report.json")

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    lines = [
        "=" * 70,
        "XAUUSD SCALPING READINESS REPORT",
        "=" * 70,
        f"Generated At: {report['generated_at']}",
        f"Strategy: {report['strategy_id']}",
        f"Recommendation: {report['recommendation']}",
        f"Demo Execution Must Remain Disabled: {report['demo_execution_should_remain_disabled']}",
        "Automatic Setting Changes Applied: NO",
    ]
    for key, stage in report["stages"].items():
        lines.extend(["", stage["name"], "-" * 70])
        lines.append(f"Passed: {stage['passed']}")
        for criterion in stage["criteria"]:
            marker = "PASS" if criterion["passed"] else "BLOCK"
            lines.append(
                f"[{marker}] {criterion['name']}: {criterion['actual']} "
                f"(required {criterion['required']})"
            )
    lines.extend(["", "=" * 70])

    with open(text_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    return {"text": text_path, "json": json_path}


def print_scalping_readiness_report() -> dict[str, Any]:
    report = build_scalping_readiness_report()
    paths = save_scalping_readiness_report(report)
    print("")
    print("=" * 70)
    print("XAUUSD SCALPING READINESS REPORT")
    print("=" * 70)
    for stage in report["stages"].values():
        print(f"{stage['name']}: {'PASSED' if stage['passed'] else 'BLOCKED'}")
        if stage["blockers"]:
            for blocker in stage["blockers"][:5]:
                print(f"  - {blocker}")
    print(f"Recommendation: {report['recommendation']}")
    print(f"Report: {paths['text']}")
    print("=" * 70)
    return report
