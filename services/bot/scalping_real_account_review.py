from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from config import scalping_settings
from services.bot.scalping_trade_repository import get_scalping_log_root, parse_trade_time
from services.risk.scalping_risk_guard import get_scalping_log_folder


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_all_demo_records() -> list[dict[str, Any]]:
    root = get_scalping_log_root()
    filename = str(scalping_settings.SCALPING_DEMO_HISTORY_FILENAME)
    records: dict[str, dict[str, Any]] = {}
    if not os.path.exists(root):
        return []

    for current_root, _, files in os.walk(root):
        if filename not in files:
            continue
        path = os.path.join(current_root, filename)
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            identity = str(
                item.get("position_ticket")
                or item.get("order_ticket")
                or f"{item.get('opened_at')}|{item.get('direction')}|{item.get('entry_price')}"
            )
            candidate = dict(item)
            existing = records.get(identity)
            if existing is None or (
                str(candidate.get("status", "")).upper() == "CLOSED"
                and str(existing.get("status", "")).upper() != "CLOSED"
            ):
                records[identity] = candidate
    return list(records.values())


def _drawdown(records: list[dict[str, Any]]) -> float:
    ordered = sorted(
        records,
        key=lambda item: parse_trade_time(item.get("closed_at")) or datetime.min,
    )
    equity = 0.0
    peak = 0.0
    maximum = 0.0
    for item in ordered:
        equity += _float(item.get("final_profit_usd"))
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return round(maximum, 2)


def build_real_account_review() -> dict[str, Any]:
    records = _load_all_demo_records()
    closed = [
        item
        for item in records
        if str(item.get("status", "")).upper() == "CLOSED"
        and item.get("final_profit_usd") not in (None, "")
    ]
    profits = [_float(item.get("final_profit_usd")) for item in closed]
    wins = [value for value in profits if value > 0]
    losses = [value for value in profits if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    opened_dates = {
        value.date().isoformat()
        for value in (parse_trade_time(item.get("opened_at")) for item in closed)
        if value is not None
    }
    win_rate = len(wins) / len(closed) * 100.0 if closed else 0.0
    net = sum(profits)
    max_drawdown = _drawdown(closed)

    criteria = [
        {
            "name": "Closed demo trades",
            "actual": len(closed),
            "required": f">= {scalping_settings.SCALPING_REAL_REVIEW_MIN_CLOSED_DEMO_TRADES}",
            "passed": len(closed)
            >= int(scalping_settings.SCALPING_REAL_REVIEW_MIN_CLOSED_DEMO_TRADES),
        },
        {
            "name": "Active demo days",
            "actual": len(opened_dates),
            "required": f">= {scalping_settings.SCALPING_REAL_REVIEW_MIN_ACTIVE_DAYS}",
            "passed": len(opened_dates)
            >= int(scalping_settings.SCALPING_REAL_REVIEW_MIN_ACTIVE_DAYS),
        },
        {
            "name": "Demo win rate",
            "actual": round(win_rate, 2),
            "required": f">= {scalping_settings.SCALPING_REAL_REVIEW_MIN_WIN_RATE:.2f}%",
            "passed": win_rate
            >= float(scalping_settings.SCALPING_REAL_REVIEW_MIN_WIN_RATE),
        },
        {
            "name": "Demo net profit",
            "actual": round(net, 2),
            "required": "> $0.00",
            "passed": net > 0,
        },
        {
            "name": "Demo profit factor",
            "actual": round(profit_factor, 3),
            "required": f">= {scalping_settings.SCALPING_REAL_REVIEW_MIN_PROFIT_FACTOR:.2f}",
            "passed": profit_factor
            >= float(scalping_settings.SCALPING_REAL_REVIEW_MIN_PROFIT_FACTOR),
        },
        {
            "name": "Demo maximum drawdown",
            "actual": max_drawdown,
            "required": f"<= ${scalping_settings.SCALPING_REAL_REVIEW_MAX_DRAWDOWN_USD:.2f}",
            "passed": max_drawdown
            <= float(scalping_settings.SCALPING_REAL_REVIEW_MAX_DRAWDOWN_USD),
        },
        {
            "name": "Real execution code flag",
            "actual": scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED,
            "required": "False",
            "passed": not bool(
                scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED
            ),
        },
    ]
    passed = all(item["passed"] for item in criteria)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "review_passed": passed,
        "closed_demo_trades": len(closed),
        "active_demo_days": len(opened_dates),
        "demo_win_rate": round(win_rate, 2),
        "demo_net_profit_usd": round(net, 2),
        "demo_profit_factor": round(profit_factor, 3),
        "demo_max_drawdown_usd": max_drawdown,
        "criteria": criteria,
        "recommendation": (
            "Evidence qualifies only for a manual real-account risk review. "
            "Real execution remains unimplemented and disabled."
            if passed
            else "Continue one-position paper validation; demo and real-account review remain blocked."
        ),
        "real_execution_available": False,
    }


def save_real_account_review(report: dict[str, Any] | None = None) -> dict[str, str]:
    report = report or build_real_account_review()
    folder = get_scalping_log_folder()
    os.makedirs(folder, exist_ok=True)
    text_path = os.path.join(folder, "scalping_real_account_review.txt")
    json_path = os.path.join(folder, "scalping_real_account_review.json")
    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    lines = [
        "=" * 70,
        "XAUUSD REAL-ACCOUNT REVIEW — EVIDENCE ONLY",
        "=" * 70,
        f"Generated At: {report['generated_at']}",
        f"Review Passed: {report['review_passed']}",
        f"Recommendation: {report['recommendation']}",
        "Real Execution Available: NO",
        "",
    ]
    for item in report["criteria"]:
        marker = "PASS" if item["passed"] else "BLOCK"
        lines.append(
            f"[{marker}] {item['name']}: {item['actual']} (required {item['required']})"
        )
    lines.extend(["", "=" * 70])
    with open(text_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return {"text": text_path, "json": json_path}


def print_real_account_review() -> dict[str, Any]:
    report = build_real_account_review()
    paths = save_real_account_review(report)
    print("")
    print("=" * 70)
    print("XAUUSD REAL-ACCOUNT REVIEW — EVIDENCE ONLY")
    print("=" * 70)
    print(f"Review Passed: {report['review_passed']}")
    print(report["recommendation"])
    print("Real Execution Available: NO")
    print(f"Report: {paths['text']}")
    print("=" * 70)
    return report
