from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from config import scalping_settings
from services.bot.scalping_performance_report import build_scalping_performance_report
from services.risk.scalping_risk_guard import get_scalping_log_folder


def _factor_value(value: Any) -> float:
    if value == "INF":
        return 999.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_scalping_parameter_review(
    performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    performance = performance or build_scalping_performance_report()
    summary = performance["summary"]
    breakdowns = performance["breakdowns"]
    minimum = int(
        getattr(scalping_settings, "SCALPING_MIN_TRADES_FOR_PARAMETER_REVIEW", 50)
    )
    closed = int(summary["closed_trades"])

    findings: list[str] = []
    recommendations: list[dict[str, str]] = []
    warnings: list[str] = []

    if closed < minimum:
        warnings.append(
            f"Only {closed}/{minimum} closed scalps are available. Keep parameters unchanged."
        )
        recommendations.append(
            {
                "parameter": "ALL STRATEGY PARAMETERS",
                "action": "HOLD",
                "reason": "Insufficient evidence for a reliable parameter change.",
            }
        )
    else:
        win_rate = float(summary["win_rate"])
        expectancy = float(summary["expectancy_usd"])
        profit_factor = _factor_value(summary["profit_factor"])
        max_drawdown = float(summary["max_drawdown_usd"])
        average_hold = float(summary["average_hold_seconds"])

        findings.extend(
            [
                f"Win rate is {win_rate:.2f}%.",
                f"Profit factor is {summary['profit_factor']}.",
                f"Expectancy is ${expectancy:.2f} per trade.",
                f"Maximum drawdown is ${max_drawdown:.2f}.",
                f"Average holding time is {average_hold:.1f} seconds.",
            ]
        )

        if expectancy <= 0 or profit_factor < 1.0:
            recommendations.append(
                {
                    "parameter": "SCALPING_MIN_ENTRY_SCORE",
                    "action": "REVIEW_UPWARD",
                    "reason": (
                        "The strategy is not producing positive expectancy. Raising the entry "
                        "score may reduce weak signals; verify using paper data before editing."
                    ),
                }
            )
        else:
            recommendations.append(
                {
                    "parameter": "SCALPING_MIN_ENTRY_SCORE",
                    "action": "HOLD",
                    "reason": "Current entries have positive expectancy; do not loosen the filter.",
                }
            )

        close_reasons = breakdowns.get("close_reason", {})
        timeout = next(
            (
                value
                for label, value in close_reasons.items()
                if "maximum hold" in label.lower()
            ),
            None,
        )
        timeout_share = (
            float(timeout["trades"]) / closed * 100.0 if timeout and closed else 0.0
        )
        if timeout_share >= 30.0:
            recommendations.append(
                {
                    "parameter": "SCALPING_MAX_HOLD_SECONDS",
                    "action": "INVESTIGATE",
                    "reason": (
                        f"{timeout_share:.1f}% of exits are timeouts. Inspect whether timeout "
                        "trades are profitable before changing the hold limit."
                    ),
                }
            )
        else:
            recommendations.append(
                {
                    "parameter": "SCALPING_MAX_HOLD_SECONDS",
                    "action": "HOLD",
                    "reason": "Timeout exits are not dominating the sample.",
                }
            )

        trailing = next(
            (
                value
                for label, value in close_reasons.items()
                if "trailing-profit" in label.lower()
            ),
            None,
        )
        if trailing and float(trailing["average_profit_usd"]) <= 0:
            recommendations.append(
                {
                    "parameter": "SCALPING_TRAILING_GIVEBACK_USD",
                    "action": "REVIEW_TIGHTER",
                    "reason": "Trailing exits are not preserving positive profit on average.",
                }
            )
        else:
            recommendations.append(
                {
                    "parameter": "SCALPING_TRAILING_GIVEBACK_USD",
                    "action": "HOLD",
                    "reason": "No evidence currently supports changing trailing protection.",
                }
            )

        stop_reason = next(
            (
                value
                for label, value in close_reasons.items()
                if "stop loss" in label.lower()
            ),
            None,
        )
        stop_share = (
            float(stop_reason["trades"]) / closed * 100.0
            if stop_reason and closed
            else 0.0
        )
        if stop_share >= 45.0:
            recommendations.append(
                {
                    "parameter": "ENTRY LOGIC / STOP RANGE",
                    "action": "DIAGNOSE",
                    "reason": (
                        f"Stop-loss exits represent {stop_share:.1f}% of trades. Diagnose signal "
                        "quality and spread/session effects before widening stops."
                    ),
                }
            )

        spread = float(summary["average_entry_spread_usd"])
        if spread > float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD) * 0.75:
            recommendations.append(
                {
                    "parameter": "SCALPING_MAX_ENTRY_SPREAD_USD",
                    "action": "REVIEW_TIGHTER",
                    "reason": "Average entry spread is close to the permitted maximum.",
                }
            )

        losing_sessions = [
            label
            for label, value in breakdowns.get("session", {}).items()
            if int(value["trades"]) >= 10 and float(value["net_profit_usd"]) < 0
        ]
        if losing_sessions:
            recommendations.append(
                {
                    "parameter": "SESSION FILTERS",
                    "action": "REVIEW",
                    "reason": "Negative sessions with meaningful samples: "
                    + ", ".join(losing_sessions),
                }
            )

        losing_directions = [
            label
            for label, value in breakdowns.get("direction", {}).items()
            if int(value["trades"]) >= 15 and float(value["net_profit_usd"]) < 0
        ]
        if losing_directions:
            recommendations.append(
                {
                    "parameter": "DIRECTION-SPECIFIC FILTERS",
                    "action": "REVIEW",
                    "reason": "Negative direction sample(s): " + ", ".join(losing_directions),
                }
            )

        if win_rate >= 55.0 and profit_factor >= 1.2 and expectancy > 0:
            findings.append(
                "The sample meets a basic positive-performance profile, but settings must still "
                "remain unchanged until readiness and drawdown requirements pass."
            )

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "closed_trades": closed,
        "minimum_required": minimum,
        "evidence_sufficient": closed >= minimum,
        "findings": findings,
        "recommendations": recommendations,
        "warnings": warnings,
        "automatic_changes_applied": False,
    }


def save_scalping_parameter_review(
    review: dict[str, Any] | None = None,
) -> dict[str, str]:
    review = review or build_scalping_parameter_review()
    folder = get_scalping_log_folder()
    os.makedirs(folder, exist_ok=True)
    text_path = os.path.join(folder, "scalping_parameter_review.txt")
    json_path = os.path.join(folder, "scalping_parameter_review.json")

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(review, file, indent=2, ensure_ascii=False)

    lines = [
        "=" * 70,
        "XAUUSD SCALPING PARAMETER REVIEW",
        "=" * 70,
        f"Generated At: {review['generated_at']}",
        f"Closed Trades: {review['closed_trades']} / {review['minimum_required']}",
        f"Evidence Sufficient: {review['evidence_sufficient']}",
        "Automatic Changes Applied: NO",
    ]
    if review["warnings"]:
        lines.extend(["", "WARNINGS", "-" * 70])
        lines.extend(f"- {item}" for item in review["warnings"])
    if review["findings"]:
        lines.extend(["", "FINDINGS", "-" * 70])
        lines.extend(f"- {item}" for item in review["findings"])
    lines.extend(["", "RECOMMENDATIONS", "-" * 70])
    for item in review["recommendations"]:
        lines.append(
            f"{item['parameter']}: {item['action']} — {item['reason']}"
        )
    lines.extend(["", "=" * 70])

    with open(text_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    return {"text": text_path, "json": json_path}


def print_scalping_parameter_review() -> dict[str, Any]:
    review = build_scalping_parameter_review()
    paths = save_scalping_parameter_review(review)
    print("")
    print("=" * 70)
    print("XAUUSD SCALPING PARAMETER REVIEW")
    print("=" * 70)
    print(
        f"Evidence: {review['closed_trades']} / {review['minimum_required']} closed trades"
    )
    print(f"Evidence Sufficient: {review['evidence_sufficient']}")
    print("Automatic Parameter Changes: NO")
    for item in review["recommendations"]:
        print(f"- {item['parameter']}: {item['action']}")
    print(f"Report: {paths['text']}")
    print("=" * 70)
    return review
