from __future__ import annotations

import json
import os
from glob import glob
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from config import scalping_settings
from services.execution.scalp_demo_journal import load_all_demo_history
from services.risk.scalping_risk_guard import get_scalping_log_folder


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _closed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("status", "")).upper() != "CLOSED":
            continue
        if row.get("final_profit_usd") is None:
            continue
        key = str(row.get("position_ticket") or row.get("deal_ticket") or row.get("order_ticket") or "")
        if not key:
            key = "|".join(
                [
                    str(row.get("opened_at", "")),
                    str(row.get("direction", "")),
                    str(row.get("entry_price", "")),
                ]
            )
        dedup[key] = dict(row)
    return sorted(dedup.values(), key=lambda item: str(item.get("closed_at", "")))


def load_demo_history_from_root(root: str) -> list[dict[str, Any]]:
    filename = str(scalping_settings.SCALPING_DEMO_HISTORY_FILENAME)
    paths = {os.path.join(root, filename)}
    paths.update(glob(os.path.join(root, "**", filename), recursive=True))
    rows: list[dict[str, Any]] = []
    for path in sorted(paths):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            rows.extend(dict(item) for item in payload if isinstance(item, dict))
    return rows


def _max_losing_streak(rows: list[dict[str, Any]]) -> int:
    maximum = current = 0
    for row in rows:
        if _float(row.get("final_profit_usd")) < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _breakdown(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key) or "UNKNOWN")].append(_float(row.get("final_profit_usd")))
    result: dict[str, dict[str, Any]] = {}
    for label, profits in sorted(groups.items()):
        wins = sum(value > 0 for value in profits)
        losses = sum(value < 0 for value in profits)
        result[label] = {
            "trades": len(profits),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(profits) * 100.0, 2) if profits else 0.0,
            "net_profit_usd": round(sum(profits), 2),
        }
    return result


def build_demo_performance_report(
    rows: list[dict[str, Any]] | None = None,
    *,
    root: str | None = None,
) -> dict[str, Any]:
    source_rows = (
        list(rows)
        if rows is not None
        else load_demo_history_from_root(root)
        if root
        else load_all_demo_history()
    )
    closed = _closed_rows(source_rows)
    profits = [_float(row.get("final_profit_usd")) for row in closed]
    wins = [value for value in profits if value > 0]
    losses = [value for value in profits if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "source_root": root or str(scalping_settings.SCALPING_LOG_ROOT),
        "summary": {
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": sum(value == 0 for value in profits),
            "win_rate": round(len(wins) / len(closed) * 100.0, 2) if closed else 0.0,
            "net_profit_usd": round(sum(profits), 2),
            "gross_profit_usd": round(gross_profit, 2),
            "gross_loss_usd": round(gross_loss, 2),
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else ("INF" if gross_profit else None),
            "average_win_usd": round(sum(wins) / len(wins), 2) if wins else 0.0,
            "average_loss_usd": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "payoff_ratio": round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 3)
            if wins and losses
            else None,
            "max_losing_streak": _max_losing_streak(closed),
        },
        "breakdowns": {
            "direction": _breakdown(closed, "direction"),
            "signal_pattern": _breakdown(closed, "signal_pattern"),
            "close_reason": _breakdown(closed, "close_reason"),
        },
        "close_reason_counts": dict(Counter(str(row.get("close_reason") or "UNKNOWN") for row in closed)),
    }


def save_demo_performance_report(report: dict[str, Any] | None = None) -> dict[str, str]:
    payload = report or build_demo_performance_report()
    folder = get_scalping_log_folder()
    os.makedirs(folder, exist_ok=True)
    json_path = os.path.join(folder, "scalp_demo_performance_report.json")
    text_path = os.path.join(folder, "scalp_demo_performance_report.txt")
    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
    summary = payload["summary"]
    with open(text_path, "w", encoding="utf-8") as file:
        file.write("CONTROLLED DEMO SCALPING PERFORMANCE REPORT\n")
        file.write("=" * 70 + "\n")
        for key, value in summary.items():
            file.write(f"{key}: {value}\n")
        file.write("\nCLOSE REASONS\n")
        for reason, values in payload["breakdowns"]["close_reason"].items():
            file.write(f"- {reason}: {values}\n")
    return {"json": json_path, "text": text_path}
