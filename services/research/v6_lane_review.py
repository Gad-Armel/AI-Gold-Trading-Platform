from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import scalping_settings
from services.research.v6_outcome_quality import research_outcome_eligible


def _history_path(lane: str) -> Path:
    name = lane.upper()
    if name == "STRICT":
        return Path(scalping_settings.SCALPING_V6_SHADOW_HISTORY_PATH)
    return Path(scalping_settings.SCALPING_V6_SHADOW_LANE_HISTORY_FOLDER) / f"{name.lower()}_history.jsonl"


def _load_pnl(lane: str) -> list[float]:
    path = _history_path(lane)
    values: list[float] = []
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("status") != "CLOSED":
            continue
        if not research_outcome_eligible(row):
            continue
        profile = row.get("entry_profile") if isinstance(row.get("entry_profile"), dict) else {}
        row_strategy = str(row.get("strategy_id") or profile.get("strategy_id") or "")
        if row_strategy != str(scalping_settings.SCALPING_STRATEGY_ID):
            continue
        try:
            values.append(float(row.get("final_profit_usd")))
        except (TypeError, ValueError):
            continue
    return values


def build_v6_session_summary(since: datetime) -> dict[str, Any]:
    """Summarize closed shadow P/L since this loop process started."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    lanes: dict[str, Any] = {}
    for lane in ("STRICT", "FAST", "BALANCED", "EXPLORATORY", "LEARNED"):
        path = _history_path(lane)
        values: list[float] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                    closed_at = datetime.fromisoformat(str(row.get("closed_at", "")).replace("Z", "+00:00"))
                    profile = row.get("entry_profile") if isinstance(row.get("entry_profile"), dict) else {}
                    row_strategy = str(row.get("strategy_id") or profile.get("strategy_id") or "")
                    if (
                        row.get("status") == "CLOSED"
                        and research_outcome_eligible(row)
                        and row_strategy == str(scalping_settings.SCALPING_STRATEGY_ID)
                        and closed_at >= since
                    ):
                        values.append(float(row.get("final_profit_usd")))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        lanes[lane] = _metrics(values)
    return {"since": since.isoformat(), "lanes": lanes}


def format_v6_session_summary(report: dict[str, Any]) -> str:
    parts: list[str] = []
    total_trades = 0
    total_net = 0.0
    for lane in ("STRICT", "FAST", "BALANCED", "EXPLORATORY", "LEARNED"):
        metrics = report.get("lanes", {}).get(lane, {})
        trades = int(metrics.get("trades", 0) or 0)
        if trades:
            net = float(metrics.get("net_profit", 0.0) or 0.0)
            parts.append(f"{lane} {trades} trades ${net:+.2f}")
            total_trades += trades
            total_net += net
    detail = " | ".join(parts) if parts else "no closed shadow trades"
    return f"Session P/L: {total_trades} closes ${total_net:+.2f} | {detail}"


def _metrics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "trades": 0,
            "net_profit": 0.0,
            "expectancy": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "maximum_drawdown": 0.0,
        }
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "trades": len(values),
        "net_profit": round(sum(values), 4),
        "expectancy": round(sum(values) / len(values), 6),
        "win_rate": round(sum(1 for value in values if value > 0) / len(values), 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "maximum_drawdown": round(max_drawdown, 4),
    }


def build_v6_lane_review() -> dict[str, Any]:
    lanes: dict[str, Any] = {}
    for lane in ("STRICT", "FAST", "BALANCED", "EXPLORATORY", "LEARNED"):
        values = _load_pnl(lane)
        lanes[lane] = {
            "history_path": str(_history_path(lane)),
            "demo_eligible": lane == "STRICT",
            "metrics": _metrics(values),
        }
    sufficiently_sampled = [
        lane for lane, payload in lanes.items()
        if int(payload["metrics"]["trades"]) >= 30
    ]
    ranked = sorted(
        sufficiently_sampled,
        key=lambda lane: (
            float(lanes[lane]["metrics"]["expectancy"]),
            float(lanes[lane]["metrics"]["profit_factor"]),
        ),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "lanes": lanes,
        "best_research_lane": best,
        "recommendation": (
            f"{best} currently has the strongest sampled research metrics. This is not demo approval."
            if best
            else "Collect at least 30 closed trades in a lane before ranking policies."
        ),
        "strict_demo_approval_unchanged": True,
    }


def print_v6_lane_review(report: dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print("V6.3 MULTI-LANE + FAST + LEARNED SHADOW COMPARISON")
    print("=" * 78)
    for lane in ("STRICT", "FAST", "BALANCED", "EXPLORATORY", "LEARNED"):
        payload = report["lanes"][lane]
        metrics = payload["metrics"]
        print(
            f"{lane}: trades={metrics['trades']} net=${metrics['net_profit']:.2f} "
            f"expectancy=${metrics['expectancy']:.3f} PF={metrics['profit_factor']:.2f} "
            f"WR={metrics['win_rate']*100:.1f}% DD=${metrics['maximum_drawdown']:.2f} "
            f"demo_eligible={'YES' if payload['demo_eligible'] else 'NO'}"
        )
    print("Recommendation: " + report["recommendation"])
    print("Only STRICT can be promoted by run_v6_walk_forward_review.py.")
    print("=" * 78)
