from __future__ import annotations

"""Research-only inverse M1 candle-colour benchmark.

This module never imports an execution service and cannot submit broker orders.
It fades the current live M1 candle: green -> SELL, red -> BUY, doji -> WAIT.
After a close it may re-enter on the next loop cycle, including within the same
candle. Real bid/ask prices are used so every re-entry charges the spread.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState
from services.utils.atomic_json import atomic_write_json


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_state() -> dict[str, Any]:
    path = Path(scalping_settings.SCALPING_CANDLE_FOLLOW_STATE_PATH)
    if not path.exists():
        return {"open_trade": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {"open_trade": None}


def _save_state(state: dict[str, Any]) -> None:
    atomic_write_json(str(scalping_settings.SCALPING_CANDLE_FOLLOW_STATE_PATH), state, indent=2)


def _append_history(record: dict[str, Any]) -> None:
    path = Path(scalping_settings.SCALPING_CANDLE_FOLLOW_HISTORY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _live_m1(snapshot: ScalpingSnapshotState) -> dict[str, Any] | None:
    frame = snapshot.candles.get("M1") if isinstance(snapshot.candles, dict) else None
    if frame is None or getattr(frame, "empty", True):
        return None
    row = frame.iloc[-1]
    opened = _float(row.get("open"))
    closed = _float(row.get("close"))
    stamp = row.get("time")
    candle_id = str(getattr(stamp, "isoformat", lambda: str(stamp))())
    color = "GREEN" if closed > opened else "RED" if closed < opened else "DOJI"
    direction = "SELL" if color == "GREEN" else "BUY" if color == "RED" else "NEUTRAL"
    candle_time = getattr(stamp, "to_pydatetime", lambda: stamp)()
    if isinstance(candle_time, datetime):
        if candle_time.tzinfo is not None:
            candle_time = candle_time.astimezone(timezone.utc).replace(tzinfo=None)
        snapshot_time = snapshot.timestamp
        if snapshot_time.tzinfo is not None:
            snapshot_time = snapshot_time.astimezone(timezone.utc).replace(tzinfo=None)
        candle_age = max(0.0, (snapshot_time - candle_time).total_seconds())
    else:
        candle_age = 999999.0
    if candle_age > float(scalping_settings.SCALPING_CANDLE_FOLLOW_MAX_CLOSED_CANDLE_AGE_SECONDS):
        direction = "STALE"
    return {
        "candle_id": candle_id,
        "color": color,
        "direction": direction,
        "open": opened,
        "high": _float(row.get("high")),
        "low": _float(row.get("low")),
        "close": closed,
        "body_usd": abs(closed - opened),
        "age_seconds": round(candle_age, 3),
    }


def _pnl(snapshot: ScalpingSnapshotState, trade: dict[str, Any]) -> float:
    direction = str(trade.get("direction"))
    exit_price = float(snapshot.bid if direction == "BUY" else snapshot.ask)
    move = exit_price - _float(trade.get("entry_price"))
    if direction == "SELL":
        move = -move
    return move * _float(trade.get("lot_size"), 0.01) * _float(trade.get("contract_size"), 100.0)


def update_candle_follow_shadow(snapshot: ScalpingSnapshotState) -> dict[str, Any]:
    state = _load_state()
    now = datetime.now(timezone.utc)
    trade = state.get("open_trade") if isinstance(state.get("open_trade"), dict) else None
    closed_record: dict[str, Any] | None = None
    action = "WAIT"
    message = "Waiting for a new closed M1 candle."

    if trade is not None:
        pnl = _pnl(snapshot, trade)
        age = max(0.0, (now - datetime.fromisoformat(str(trade["opened_at"]))).total_seconds())
        trade["current_profit_usd"] = round(pnl, 4)
        trade["hold_seconds"] = round(age, 3)
        reason = ""
        if pnl >= _float(trade.get("target_profit_usd")):
            reason = "TARGET"
        elif pnl <= -_float(trade.get("stop_loss_usd")):
            reason = "STOP"
        elif age >= _float(trade.get("max_hold_seconds")):
            reason = "TIME"
        if reason:
            # Targets are capped at the planned barrier; adverse stops and time
            # exits retain the observed executable quote.
            final_pnl = min(pnl, _float(trade.get("target_profit_usd"))) if reason == "TARGET" else pnl
            closed_record = {
                **trade,
                "status": "CLOSED",
                "closed_at": now.isoformat(),
                "exit_price": float(snapshot.bid if trade["direction"] == "BUY" else snapshot.ask),
                "observed_profit_usd": round(pnl, 4),
                "final_profit_usd": round(final_pnl, 4),
                "close_reason": reason,
            }
            _append_history(closed_record)
            state["open_trade"] = None
            action = "CLOSE"
            message = f"Closed {trade['direction']} ${final_pnl:+.2f}: {reason}."
        else:
            state["open_trade"] = trade
            action = "MONITOR"
            message = f"{trade['direction']} open ${pnl:+.2f}, age={age:.1f}s."

    candle = _live_m1(snapshot)
    if state.get("open_trade") is None and closed_record is None and candle is not None:
        direction = str(candle["direction"])
        if direction in {"BUY", "SELL"}:
            entry = float(snapshot.ask if direction == "BUY" else snapshot.bid)
            trade = {
                    "status": "OPEN",
                    "strategy_id": scalping_settings.SCALPING_CANDLE_FOLLOW_STRATEGY_ID,
                    "symbol": snapshot.symbol,
                    "opened_at": now.isoformat(),
                    "source_candle": candle,
                    "direction": direction,
                    "entry_price": entry,
                    "entry_spread_usd": round(float(snapshot.spread), 6),
                    "lot_size": float(scalping_settings.SCALPING_LOT_SIZE),
                    "contract_size": float(snapshot.contract_size),
                    "target_profit_usd": float(scalping_settings.SCALPING_CANDLE_FOLLOW_TARGET_USD),
                    "stop_loss_usd": float(scalping_settings.SCALPING_CANDLE_FOLLOW_STOP_USD),
                    "max_hold_seconds": float(scalping_settings.SCALPING_CANDLE_FOLLOW_MAX_HOLD_SECONDS),
                    "current_profit_usd": round(-float(snapshot.spread) * float(scalping_settings.SCALPING_LOT_SIZE) * float(snapshot.contract_size), 4),
            }
            state["open_trade"] = trade
            action = "OPEN"
            message = f"Live M1 candle is {candle['color']}; opened inverse {direction} shadow at {entry:.5f}."
        else:
            action = "STALE" if direction == "STALE" else "DOJI"
            message = (
                f"Live M1 candle is stale ({candle['age_seconds']:.1f}s); no position."
                if direction == "STALE"
                else "Live M1 candle is a doji; no position."
            )

    state["updated_at"] = now.isoformat()
    _save_state(state)
    return {
        "action": action,
        "message": message,
        "open_trade": state.get("open_trade"),
        "closed_record": closed_record,
        "source_candle": candle,
    }


def candle_follow_metrics(*, since: datetime | None = None) -> dict[str, Any]:
    path = Path(scalping_settings.SCALPING_CANDLE_FOLLOW_HISTORY_PATH)
    values: list[float] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
                closed_at = datetime.fromisoformat(str(row.get("closed_at")))
                if row.get("strategy_id") != scalping_settings.SCALPING_CANDLE_FOLLOW_STRATEGY_ID:
                    continue
                if since is not None and closed_at < since:
                    continue
                values.append(float(row.get("final_profit_usd")))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    wins = sum(value > 0 for value in values)
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    return {
        "trades": len(values),
        "wins": wins,
        "losses": sum(value < 0 for value in values),
        "net_profit": round(sum(values), 4),
        "win_rate": round(wins / len(values), 6) if values else 0.0,
        "expectancy": round(sum(values) / len(values), 6) if values else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
    }
