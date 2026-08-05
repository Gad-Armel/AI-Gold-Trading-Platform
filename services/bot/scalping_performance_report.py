from __future__ import annotations

import csv
import html
import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from config import scalping_settings
from services.bot.scalping_trade_repository import (
    filter_strategy_trades,
    load_all_scalping_trades,
    parse_trade_time,
    split_trade_statuses,
    trade_profit,
)
from services.risk.scalping_risk_guard import get_scalping_log_folder


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _max_drawdown(closed: list[dict[str, Any]]) -> float:
    equity = 0.0
    peak = 0.0
    maximum = 0.0
    ordered = sorted(
        closed,
        key=lambda item: parse_trade_time(item.get("closed_at")) or datetime.min,
    )
    for trade in ordered:
        equity += trade_profit(trade)
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return _round(maximum)


def _streaks(closed: list[dict[str, Any]]) -> tuple[int, int]:
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    ordered = sorted(
        closed,
        key=lambda item: parse_trade_time(item.get("closed_at")) or datetime.min,
    )
    for trade in ordered:
        profit = trade_profit(trade)
        if profit > 0:
            current_wins += 1
            current_losses = 0
        elif profit < 0:
            current_losses += 1
            current_wins = 0
        else:
            current_wins = 0
            current_losses = 0
        max_wins = max(max_wins, current_wins)
        max_losses = max(max_losses, current_losses)

    return max_wins, max_losses


def _breakdown(
    closed: Iterable[dict[str, Any]],
    key: str,
    default: str = "UNKNOWN",
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in closed:
        label = str(trade.get(key, default) or default).strip() or default
        grouped[label].append(trade)

    result: dict[str, dict[str, Any]] = {}
    for label, items in sorted(grouped.items()):
        profits = [trade_profit(item) for item in items]
        wins = sum(value > 0 for value in profits)
        losses = sum(value < 0 for value in profits)
        gross_profit = sum(value for value in profits if value > 0)
        gross_loss = abs(sum(value for value in profits if value < 0))
        result[label] = {
            "trades": len(items),
            "wins": wins,
            "losses": losses,
            "win_rate": _round(wins / len(items) * 100.0) if items else 0.0,
            "net_profit_usd": _round(sum(profits)),
            "average_profit_usd": _round(statistics.fmean(profits)) if profits else 0.0,
            "profit_factor": (
                _round(gross_profit / gross_loss, 3)
                if gross_loss > 0
                else (None if gross_profit <= 0 else "INF")
            ),
        }
    return result


def _data_quality(trades: list[dict[str, Any]]) -> dict[str, Any]:
    required = (
        "id",
        "status",
        "symbol",
        "direction",
        "opened_at",
        "entry_price",
    )
    missing: dict[str, int] = {field: 0 for field in required}
    invalid_closed_profit = 0
    invalid_times = 0

    for trade in trades:
        for field in required:
            if trade.get(field) in (None, ""):
                missing[field] += 1

        if str(trade.get("status", "")).upper() == "CLOSED":
            if trade.get("final_profit_usd") in (None, ""):
                invalid_closed_profit += 1
            if parse_trade_time(trade.get("closed_at")) is None:
                invalid_times += 1

        if parse_trade_time(trade.get("opened_at")) is None:
            invalid_times += 1

    errors = []
    for field, count in missing.items():
        if count:
            errors.append(f"{count} trade(s) are missing {field}.")
    if invalid_closed_profit:
        errors.append(
            f"{invalid_closed_profit} closed trade(s) are missing final_profit_usd."
        )
    if invalid_times:
        errors.append(f"{invalid_times} trade timestamp(s) could not be parsed.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "missing_fields": missing,
        "invalid_closed_profit": invalid_closed_profit,
        "invalid_times": invalid_times,
    }


def build_scalping_performance_report() -> dict[str, Any]:
    all_trades = filter_strategy_trades(load_all_scalping_trades())
    closed, opened = split_trade_statuses(all_trades)
    profits = [trade_profit(trade) for trade in closed]
    wins = [value for value in profits if value > 0]
    losses = [value for value in profits if value < 0]
    breakeven = [value for value in profits if value == 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor: float | str | None
    if gross_loss > 0:
        profit_factor = _round(gross_profit / gross_loss, 3)
    elif gross_profit > 0:
        profit_factor = "INF"
    else:
        profit_factor = None

    hold_seconds = [
        max(0.0, _safe_float(trade.get("hold_seconds")))
        for trade in closed
        if trade.get("hold_seconds") not in (None, "")
    ]
    spreads = [
        max(0.0, _safe_float(trade.get("entry_spread")))
        for trade in closed
        if trade.get("entry_spread") not in (None, "")
    ]

    opened_times = [
        value
        for value in (parse_trade_time(trade.get("opened_at")) for trade in closed)
        if value is not None
    ]
    active_dates = sorted({value.date().isoformat() for value in opened_times})
    date_span_days = 0
    if opened_times:
        date_span_days = (max(opened_times).date() - min(opened_times).date()).days + 1

    max_winning_streak, max_losing_streak = _streaks(closed)
    net_profit = sum(profits)
    closed_count = len(closed)
    average_profit = statistics.fmean(profits) if profits else 0.0

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy_id": getattr(
            scalping_settings, "SCALPING_STRATEGY_ID", "XAUUSD_SCALP_V1"
        ),
        "summary": {
            "total_trades": len(all_trades),
            "closed_trades": closed_count,
            "open_trades": len(opened),
            "wins": len(wins),
            "losses": len(losses),
            "breakeven_trades": len(breakeven),
            "win_rate": _round(len(wins) / closed_count * 100.0)
            if closed_count
            else 0.0,
            "loss_rate": _round(len(losses) / closed_count * 100.0)
            if closed_count
            else 0.0,
            "net_profit_usd": _round(net_profit),
            "gross_profit_usd": _round(gross_profit),
            "gross_loss_usd": _round(gross_loss),
            "profit_factor": profit_factor,
            "average_trade_usd": _round(average_profit),
            "average_win_usd": _round(statistics.fmean(wins)) if wins else 0.0,
            "average_loss_usd": _round(statistics.fmean(losses)) if losses else 0.0,
            "largest_win_usd": _round(max(wins)) if wins else 0.0,
            "largest_loss_usd": _round(min(losses)) if losses else 0.0,
            "expectancy_usd": _round(average_profit),
            "max_drawdown_usd": _max_drawdown(closed),
            "max_winning_streak": max_winning_streak,
            "max_losing_streak": max_losing_streak,
            "average_hold_seconds": _round(statistics.fmean(hold_seconds), 1)
            if hold_seconds
            else 0.0,
            "median_hold_seconds": _round(statistics.median(hold_seconds), 1)
            if hold_seconds
            else 0.0,
            "average_entry_spread_usd": _round(statistics.fmean(spreads), 4)
            if spreads
            else 0.0,
            "active_trading_days": len(active_dates),
            "calendar_span_days": date_span_days,
            "trades_per_active_day": _round(closed_count / len(active_dates), 2)
            if active_dates
            else 0.0,
            "first_trade_at": min(opened_times).strftime("%Y-%m-%d %H:%M:%S")
            if opened_times
            else "",
            "last_trade_at": max(opened_times).strftime("%Y-%m-%d %H:%M:%S")
            if opened_times
            else "",
        },
        "breakdowns": {
            "direction": _breakdown(closed, "direction"),
            "session": _breakdown(closed, "session"),
            "pattern": _breakdown(closed, "entry_pattern"),
            "close_reason": _breakdown(closed, "close_reason"),
            "profit_calculation_method": _breakdown(
                closed, "profit_calculation_method", "LEGACY_OR_FALLBACK"
            ),
        },
        "active_dates": active_dates,
        "data_quality": _data_quality(all_trades),
        "source_file_count": len(
            {
                str(trade.get("source_file", ""))
                for trade in all_trades
                if trade.get("source_file")
            }
        ),
    }
    return report


def _format_factor(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _breakdown_lines(title: str, data: dict[str, dict[str, Any]]) -> list[str]:
    lines = ["", title, "-" * 70]
    if not data:
        lines.append("No closed trades available.")
        return lines

    for label, values in data.items():
        lines.append(
            f"{label}: trades={values['trades']}, win_rate={values['win_rate']:.2f}%, "
            f"net=${values['net_profit_usd']:.2f}, "
            f"profit_factor={_format_factor(values['profit_factor'])}"
        )
    return lines


def save_scalping_performance_report(report: dict[str, Any] | None = None) -> dict[str, str]:
    report = report or build_scalping_performance_report()
    folder = get_scalping_log_folder()
    os.makedirs(folder, exist_ok=True)

    json_path = os.path.join(folder, "scalping_performance_report.json")
    text_path = os.path.join(folder, "scalping_performance_report.txt")
    csv_path = os.path.join(folder, "scalping_performance_breakdown.csv")
    html_path = os.path.join(folder, "scalping_performance_dashboard.html")

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    summary = report["summary"]
    lines = [
        "=" * 70,
        "XAUUSD SCALPING PERFORMANCE REPORT",
        "=" * 70,
        f"Generated At: {report['generated_at']}",
        f"Strategy: {report['strategy_id']}",
        f"Source Files: {report['source_file_count']}",
        "-" * 70,
        f"Total Trades: {summary['total_trades']}",
        f"Closed Trades: {summary['closed_trades']}",
        f"Open Trades: {summary['open_trades']}",
        f"Wins / Losses / Breakeven: {summary['wins']} / {summary['losses']} / {summary['breakeven_trades']}",
        f"Win Rate: {summary['win_rate']:.2f}%",
        f"Net Profit: ${summary['net_profit_usd']:.2f}",
        f"Gross Profit: ${summary['gross_profit_usd']:.2f}",
        f"Gross Loss: ${summary['gross_loss_usd']:.2f}",
        f"Profit Factor: {_format_factor(summary['profit_factor'])}",
        f"Average Trade / Expectancy: ${summary['expectancy_usd']:.2f}",
        f"Average Win: ${summary['average_win_usd']:.2f}",
        f"Average Loss: ${summary['average_loss_usd']:.2f}",
        f"Maximum Drawdown: ${summary['max_drawdown_usd']:.2f}",
        f"Maximum Winning Streak: {summary['max_winning_streak']}",
        f"Maximum Losing Streak: {summary['max_losing_streak']}",
        f"Average Hold: {summary['average_hold_seconds']:.1f} seconds",
        f"Average Entry Spread: ${summary['average_entry_spread_usd']:.4f}",
        f"Active Trading Days: {summary['active_trading_days']}",
        f"Trades Per Active Day: {summary['trades_per_active_day']:.2f}",
        f"Data Quality Valid: {report['data_quality']['valid']}",
    ]
    if report["data_quality"]["errors"]:
        lines.append("Data Quality Errors:")
        lines.extend(f"  - {item}" for item in report["data_quality"]["errors"])

    for title, key in (
        ("DIRECTION BREAKDOWN", "direction"),
        ("SESSION BREAKDOWN", "session"),
        ("PATTERN BREAKDOWN", "pattern"),
        ("EXIT-REASON BREAKDOWN", "close_reason"),
    ):
        lines.extend(_breakdown_lines(title, report["breakdowns"][key]))
    lines.extend(["", "=" * 70])

    with open(text_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "category",
                "value",
                "trades",
                "wins",
                "losses",
                "win_rate",
                "net_profit_usd",
                "average_profit_usd",
                "profit_factor",
            ],
        )
        writer.writeheader()
        for category, values in report["breakdowns"].items():
            for label, metrics in values.items():
                writer.writerow(
                    {
                        "category": category,
                        "value": label,
                        **metrics,
                    }
                )

    cards = [
        ("Closed Trades", summary["closed_trades"]),
        ("Win Rate", f"{summary['win_rate']:.2f}%"),
        ("Net Profit", f"${summary['net_profit_usd']:.2f}"),
        ("Profit Factor", _format_factor(summary["profit_factor"])),
        ("Max Drawdown", f"${summary['max_drawdown_usd']:.2f}"),
        ("Avg Hold", f"{summary['average_hold_seconds']:.1f}s"),
    ]
    card_html = "".join(
        f"<div class='card'><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>"
        for label, value in cards
    )
    table_rows = []
    for category in ("direction", "session", "pattern", "close_reason"):
        for label, metrics in report["breakdowns"][category].items():
            table_rows.append(
                "<tr>"
                f"<td>{html.escape(category)}</td>"
                f"<td>{html.escape(label)}</td>"
                f"<td>{metrics['trades']}</td>"
                f"<td>{metrics['win_rate']:.2f}%</td>"
                f"<td>${metrics['net_profit_usd']:.2f}</td>"
                f"<td>{html.escape(_format_factor(metrics['profit_factor']))}</td>"
                "</tr>"
            )

    dashboard = f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>XAUUSD Scalping Performance</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#111827;color:#e5e7eb}}
main{{max-width:1200px;margin:auto;padding:24px}}
h1{{margin:0 0 6px}} .muted{{color:#9ca3af}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:22px 0}}
.card{{background:#1f2937;border:1px solid #374151;border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:8px}}
.card span{{color:#9ca3af}} .card strong{{font-size:1.5rem}}
table{{width:100%;border-collapse:collapse;background:#1f2937;border-radius:12px;overflow:hidden}}
th,td{{padding:10px;border-bottom:1px solid #374151;text-align:left}} th{{background:#273449}}
.ok{{color:#86efac}} .bad{{color:#fca5a5}}
</style>
</head>
<body><main>
<h1>XAUUSD Scalping Performance</h1>
<p class='muted'>Generated {html.escape(report['generated_at'])} — {html.escape(report['strategy_id'])}</p>
<div class='cards'>{card_html}</div>
<h2>Breakdowns</h2>
<table><thead><tr><th>Category</th><th>Value</th><th>Trades</th><th>Win Rate</th><th>Net</th><th>Profit Factor</th></tr></thead>
<tbody>{''.join(table_rows) or '<tr><td colspan="6">No closed trades yet.</td></tr>'}</tbody></table>
<p class='muted'>Data quality: <span class='{'ok' if report['data_quality']['valid'] else 'bad'}'>{'VALID' if report['data_quality']['valid'] else 'REVIEW REQUIRED'}</span></p>
</main></body></html>"""
    with open(html_path, "w", encoding="utf-8") as file:
        file.write(dashboard)

    return {
        "json": json_path,
        "text": text_path,
        "csv": csv_path,
        "html": html_path,
    }


def print_scalping_performance_report() -> dict[str, Any]:
    report = build_scalping_performance_report()
    paths = save_scalping_performance_report(report)
    summary = report["summary"]

    print("")
    print("=" * 70)
    print("XAUUSD SCALPING PERFORMANCE REPORT")
    print("=" * 70)
    print(f"Closed Trades: {summary['closed_trades']}")
    print(f"Win Rate: {summary['win_rate']:.2f}%")
    print(f"Net Profit: ${summary['net_profit_usd']:.2f}")
    print(f"Profit Factor: {_format_factor(summary['profit_factor'])}")
    print(f"Expectancy: ${summary['expectancy_usd']:.2f} per trade")
    print(f"Maximum Drawdown: ${summary['max_drawdown_usd']:.2f}")
    print(f"Active Trading Days: {summary['active_trading_days']}")
    print(f"Data Quality Valid: {report['data_quality']['valid']}")
    print(f"Text Report: {paths['text']}")
    print(f"Dashboard: {paths['html']}")
    print("=" * 70)
    return report
