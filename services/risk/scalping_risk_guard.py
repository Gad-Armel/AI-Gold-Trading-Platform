from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from config import scalping_settings
from config import settings as core_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.risk.adaptive_spread_policy import evaluate_adaptive_spread_policy


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_scalping_log_folder() -> str:
    folder = scalping_settings.SCALPING_LOG_ROOT
    if scalping_settings.SCALPING_USE_DAILY_LOG_FOLDERS:
        folder = os.path.join(
            folder,
            datetime.now().strftime(scalping_settings.SCALPING_DATE_FORMAT),
        )
    os.makedirs(folder, exist_ok=True)
    return folder


def get_scalping_trades_path() -> str:
    return os.path.join(
        get_scalping_log_folder(),
        scalping_settings.SCALPING_TRADES_FILENAME,
    )


def load_scalping_trades() -> list[dict[str, Any]]:
    path = get_scalping_trades_path()
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _closed_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [trade for trade in trades if str(trade.get("status", "")).upper() == "CLOSED"]


def _open_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [trade for trade in trades if str(trade.get("status", "")).upper() == "OPEN"]


def _consecutive_losses(closed: list[dict[str, Any]]) -> int:
    losses = 0
    for trade in sorted(closed, key=lambda item: str(item.get("closed_at", "")), reverse=True):
        if _safe_float(trade.get("final_profit_usd")) < 0:
            losses += 1
        else:
            break
    return losses


def _parse_closed_at(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value), DATETIME_FORMAT)
    except (TypeError, ValueError):
        return None


def _loss_streak_cooldown(
    closed: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the cooldown state for complete groups of consecutive losses.

    A cooldown is triggered by loss 3, 6, 9, and so on within the current
    uninterrupted losing streak. Once a group's cooldown expires, trading
    resumes automatically; losses 4 and 5 do not restart the first cooldown.
    Any non-losing trade resets the streak.
    """

    threshold = max(1, int(
        scalping_settings.SCALPING_LOSS_STREAK_COOLDOWN_AFTER_LOSSES
    ))
    duration = max(0.0, float(
        scalping_settings.SCALPING_LOSS_STREAK_COOLDOWN_SECONDS
    ))
    ordered = sorted(closed, key=lambda item: str(item.get("closed_at", "")))

    trailing_losses: list[dict[str, Any]] = []
    for trade in reversed(ordered):
        if _safe_float(trade.get("final_profit_usd")) < 0:
            trailing_losses.append(trade)
        else:
            break
    trailing_losses.reverse()

    streak = len(trailing_losses)
    completed_groups = streak // threshold
    state: dict[str, Any] = {
        "active": False,
        "status": "INACTIVE",
        "threshold": threshold,
        "duration_seconds": duration,
        "consecutive_losses": streak,
        "completed_groups": completed_groups,
        "triggered_at": "",
        "elapsed_seconds": 0.0,
        "remaining_seconds": 0.0,
        "timestamp_valid": True,
    }
    if completed_groups <= 0 or duration <= 0:
        return state

    trigger_index = completed_groups * threshold - 1
    trigger_trade = trailing_losses[trigger_index]
    triggered_at = _parse_closed_at(trigger_trade.get("closed_at"))
    if triggered_at is None:
        state.update({
            "status": "TIMESTAMP_INVALID",
            "timestamp_valid": False,
        })
        return state

    current = now or datetime.now()
    elapsed = max(0.0, (current - triggered_at).total_seconds())
    remaining = max(0.0, duration - elapsed)
    active = remaining > 0.0
    state.update({
        "active": active,
        "status": "ACTIVE" if active else "COMPLETED",
        "triggered_at": triggered_at.strftime(DATETIME_FORMAT),
        "elapsed_seconds": round(elapsed, 3),
        "remaining_seconds": round(remaining, 3),
    })
    return state


def _max_drawdown(closed: list[dict[str, Any]]) -> float:
    running = 0.0
    peak = 0.0
    maximum = 0.0

    for trade in sorted(closed, key=lambda item: str(item.get("closed_at", ""))):
        running += _safe_float(trade.get("final_profit_usd"))
        peak = max(peak, running)
        maximum = max(maximum, peak - running)

    return round(maximum, 2)


def evaluate_scalping_risk(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    news_risk: dict[str, Any],
) -> dict[str, Any]:
    trades = load_scalping_trades()
    closed = _closed_trades(trades)
    opened = _open_trades(trades)

    realized = round(
        sum(_safe_float(trade.get("final_profit_usd")) for trade in closed),
        2,
    )
    trade_count = len(trades)
    consecutive_losses = _consecutive_losses(closed)
    drawdown = _max_drawdown(closed)

    block_reasons: list[str] = []
    warnings: list[str] = []

    if not scalping_settings.SCALPING_ENABLED:
        block_reasons.append("Scalping mode is disabled.")

    if not scalping_settings.SCALPING_PAPER_ONLY:
        block_reasons.append("Scalping paper-only safety flag is not enabled.")

    if (
        scalping_settings.REQUIRE_CORE_LIVE_TRADING_DISABLED
        and bool(getattr(core_settings, "ENABLE_LIVE_TRADING", False))
    ):
        block_reasons.append(
            "Core ENABLE_LIVE_TRADING must remain False while the paper scalper runs."
        )

    spread_policy = evaluate_adaptive_spread_policy(
        snapshot, signal, require_normal_economics=False
    )
    if not bool(spread_policy.get("accepted", False)):
        block_reasons.append(
            "Entry spread/economics policy rejected entry: "
            + str(spread_policy.get("reason", "unknown spread-policy failure"))
        )

    if not bool(news_risk.get("allowed", False)):
        block_reasons.extend(
            news_risk.get("block_reasons", [])
            or ["News risk filter blocked new scalps."]
        )

    if trade_count >= int(scalping_settings.SCALPING_MAX_DAILY_TRADES):
        block_reasons.append(
            "Daily scalp limit reached: "
            f"{trade_count} >= {scalping_settings.SCALPING_MAX_DAILY_TRADES}."
        )

    if realized <= -float(scalping_settings.SCALPING_DAILY_LOSS_LIMIT_USD):
        block_reasons.append(
            "Daily scalping loss limit reached: "
            f"{realized:.2f} <= -{scalping_settings.SCALPING_DAILY_LOSS_LIMIT_USD:.2f}."
        )

    loss_cooldown = _loss_streak_cooldown(closed)
    if bool(loss_cooldown.get("active", False)):
        block_reasons.append(
            "Three-loss cooldown active: "
            f"{loss_cooldown.get('remaining_seconds', 0.0):.1f}s remaining "
            f"after {consecutive_losses} consecutive losses."
        )
    elif loss_cooldown.get("status") == "COMPLETED":
        warnings.append(
            "Three-loss cooldown completed; paper trading resumed automatically."
        )
    elif loss_cooldown.get("status") == "TIMESTAMP_INVALID":
        warnings.append(
            "Loss-streak cooldown timestamp was invalid; no permanent block was applied."
        )

    if drawdown >= float(scalping_settings.SCALPING_MAX_DRAWDOWN_USD):
        block_reasons.append(
            "Scalping drawdown limit reached: "
            f"{drawdown:.2f} >= "
            f"{scalping_settings.SCALPING_MAX_DRAWDOWN_USD:.2f}."
        )

    if len(opened) >= int(scalping_settings.SCALPING_MAX_OPEN_POSITIONS):
        warnings.append(
            "Maximum scalp positions are already open; existing positions will still be managed."
        )

    same_direction = sum(
        str(trade.get("direction", "")).upper() == signal.direction
        for trade in opened
    )
    if (
        signal.allowed
        and same_direction
        >= int(scalping_settings.SCALPING_MAX_SAME_DIRECTION_POSITIONS)
    ):
        block_reasons.append(
            "Same-direction scalp position limit reached: "
            f"{same_direction}/{scalping_settings.SCALPING_MAX_SAME_DIRECTION_POSITIONS}."
        )

    existing_open_risk = sum(
        max(0.0, _safe_float(trade.get("stop_loss_usd")))
        for trade in opened
    )
    proposed_open_risk = existing_open_risk + (
        max(0.0, _safe_float(signal.stop_loss_usd)) if signal.allowed else 0.0
    )
    if (
        signal.allowed
        and proposed_open_risk
        > float(scalping_settings.SCALPING_MAX_TOTAL_OPEN_RISK_USD)
    ):
        block_reasons.append(
            "Aggregate open scalp risk would exceed the configured limit: "
            f"${proposed_open_risk:.2f} > "
            f"${scalping_settings.SCALPING_MAX_TOTAL_OPEN_RISK_USD:.2f}."
        )

    if realized < 0:
        warnings.append(f"Daily realized scalping P/L is negative: ${realized:.2f}.")

    # A WAIT signal is not a risk failure. It simply cannot open a new trade.
    entry_allowed = len(block_reasons) == 0 and signal.allowed

    return {
        "allowed": len(block_reasons) == 0,
        "spread_policy": spread_policy,
        "entry_allowed": entry_allowed,
        "action": "SCALP_RISK_ALLOWED" if len(block_reasons) == 0 else "SCALP_RISK_BLOCKED",
        "daily_realized_profit": realized,
        "daily_trade_count": trade_count,
        "closed_trade_count": len(closed),
        "open_trade_count": len(opened),
        "consecutive_losses": consecutive_losses,
        "loss_cooldown_active": bool(loss_cooldown.get("active", False)),
        "loss_cooldown_status": loss_cooldown.get("status", "INACTIVE"),
        "loss_cooldown_remaining_seconds": loss_cooldown.get("remaining_seconds", 0.0),
        "loss_cooldown_duration_seconds": loss_cooldown.get("duration_seconds", 0.0),
        "loss_cooldown_triggered_at": loss_cooldown.get("triggered_at", ""),
        "loss_cooldown_completed_groups": loss_cooldown.get("completed_groups", 0),
        "max_drawdown": drawdown,
        "same_direction_open_count": same_direction,
        "existing_open_risk_usd": round(existing_open_risk, 2),
        "proposed_open_risk_usd": round(proposed_open_risk, 2),
        "block_reasons": block_reasons,
        "warnings": warnings,
    }
