from __future__ import annotations

"""Isolated, research-only XAUUSD medium-horizon shadow engine.

No execution service is imported. Entries and exits use executable bid/ask
quotes, so spread is charged. Signals use completed bars only; 45-minute and
2-hour views are derived from broker M15 and H1 bars respectively.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState
from services.utils.atomic_json import atomic_write_json


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _closed(snapshot: ScalpingSnapshotState, name: str) -> pd.DataFrame:
    raw = snapshot.candles.get(name) if isinstance(snapshot.candles, dict) else None
    if raw is None or getattr(raw, "empty", True):
        return pd.DataFrame()
    frame = raw.copy()
    required = {"time", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame = frame.dropna(subset=list(required)).sort_values("time")
    return frame.iloc[:-1].copy() if len(frame) > 1 else pd.DataFrame()


def _aggregate(frame: pd.DataFrame, rule: str, expected_bars: int) -> pd.DataFrame:
    """Aggregate completed broker bars on stable UTC clock boundaries."""
    if frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    work["time"] = pd.to_datetime(work["time"], utc=True, errors="coerce")
    work = work.dropna(subset=["time"]).set_index("time")
    grouped = work.resample(rule, origin="epoch", label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    counts = grouped["close"].count()
    result = result.loc[counts >= expected_bars].dropna().reset_index()
    return result


def _view(frame: pd.DataFrame) -> dict[str, Any]:
    minimum = int(scalping_settings.SCALPING_MEDIUM_MIN_BARS)
    if len(frame) < minimum:
        return {"direction": "NEUTRAL", "reason": f"only {len(frame)}/{minimum} bars"}
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)
    atr = max(_float(true_range.rolling(14).mean().iloc[-1]), 0.01)
    separation = _float(fast.iloc[-1] - slow.iloc[-1])
    slope = _float(fast.iloc[-1] - fast.iloc[-4])
    threshold = atr * float(scalping_settings.SCALPING_MEDIUM_MIN_EMA_SEPARATION_ATR)
    direction = "NEUTRAL"
    if separation >= threshold and slope > 0:
        direction = "BUY"
    elif separation <= -threshold and slope < 0:
        direction = "SELL"
    return {
        "direction": direction,
        "last_close": round(_float(close.iloc[-1]), 6),
        "ema_fast": round(_float(fast.iloc[-1]), 6),
        "ema_slow": round(_float(slow.iloc[-1]), 6),
        "atr": round(atr, 6),
        "separation_atr": round(separation / atr, 6),
        "slope": round(slope, 6),
    }


def analyze_medium_horizon(snapshot: ScalpingSnapshotState) -> dict[str, Any]:
    m15, h1, h4 = (_closed(snapshot, name) for name in ("M15", "H1", "H4"))
    frames = {
        "M45": _aggregate(m15, "45min", 3),
        "H1": h1,
        "H2": _aggregate(h1, "2h", 2),
        "H4": h4,
    }
    views = {name: _view(frame) for name, frame in frames.items()}
    buy_votes = sum(view["direction"] == "BUY" for view in views.values())
    sell_votes = sum(view["direction"] == "SELL" for view in views.values())
    required = int(scalping_settings.SCALPING_MEDIUM_MIN_DIRECTIONAL_VOTES)
    direction = "BUY" if buy_votes >= required else "SELL" if sell_votes >= required else "NEUTRAL"
    signal_id = ""
    if not m15.empty:
        stamp = m15.iloc[-1]["time"]
        signal_id = getattr(stamp, "isoformat", lambda: str(stamp))()

    signal_age_seconds = 999999.0
    if not m15.empty:
        signal_time = pd.Timestamp(m15.iloc[-1]["time"])
        if signal_time.tzinfo is None:
            signal_time = signal_time.tz_localize("UTC")
        else:
            signal_time = signal_time.tz_convert("UTC")
        reference = pd.Timestamp(snapshot.timestamp)
        if reference.tzinfo is None:
            reference = reference.tz_localize("UTC")
        else:
            reference = reference.tz_convert("UTC")
        signal_age_seconds = max(0.0, (reference - signal_time).total_seconds())
        if signal_age_seconds > float(scalping_settings.SCALPING_MEDIUM_MAX_SIGNAL_AGE_SECONDS):
            direction = "NEUTRAL"

    if (
        direction in {"BUY", "SELL"}
        and bool(scalping_settings.SCALPING_MEDIUM_REQUIRE_H4_NOT_OPPOSED)
        and views["H4"]["direction"] in {"BUY", "SELL"}
        and views["H4"]["direction"] != direction
    ):
        direction = "NEUTRAL"

    entry_distance_atr = 999.0
    if direction in {"BUY", "SELL"} and views["H1"].get("atr"):
        # Compare with the latest completed H1 close, not a lagging EMA.  EMA
        # distance systematically rejects orderly persistent trends; completed
        # close distance instead catches an actual live gap/chase condition.
        entry_distance_atr = abs(snapshot.mid - _float(views["H1"].get("last_close"))) / _float(views["H1"]["atr"], 0.01)
        if entry_distance_atr > float(scalping_settings.SCALPING_MEDIUM_MAX_ENTRY_DISTANCE_ATR):
            direction = "NEUTRAL"

    return {
        "direction": direction,
        "buy_votes": buy_votes,
        "sell_votes": sell_votes,
        "required_votes": required,
        "signal_id": str(signal_id),
        "signal_age_seconds": round(signal_age_seconds, 3),
        "entry_distance_atr": round(entry_distance_atr, 6),
        "views": views,
    }


def _load_state() -> dict[str, Any]:
    path = Path(scalping_settings.SCALPING_MEDIUM_STATE_PATH)
    if not path.exists():
        return {"positions": [], "used_signal_ids": [], "episode_direction": "", "episode_consumed": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"positions": [], "used_signal_ids": [], "episode_direction": "", "episode_consumed": False}
    except (OSError, json.JSONDecodeError):
        return {"positions": [], "used_signal_ids": [], "episode_direction": "", "episode_consumed": False}


def _save_state(state: dict[str, Any]) -> None:
    atomic_write_json(str(scalping_settings.SCALPING_MEDIUM_STATE_PATH), state, indent=2)


def _append(record: dict[str, Any]) -> None:
    path = Path(scalping_settings.SCALPING_MEDIUM_HISTORY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _pnl(snapshot: ScalpingSnapshotState, trade: dict[str, Any]) -> float:
    exit_price = snapshot.bid if trade["direction"] == "BUY" else snapshot.ask
    move = exit_price - _float(trade["entry_price"])
    if trade["direction"] == "SELL":
        move = -move
    return move * _float(trade["lot_size"]) * _float(trade["contract_size"])


def update_medium_horizon_shadow(
    snapshot: ScalpingSnapshotState,
    *,
    news_risk: dict[str, Any] | None = None,
    cross_market: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    state = _load_state()
    positions = [item for item in state.get("positions", []) if isinstance(item, dict)]
    analysis = analyze_medium_horizon(snapshot)
    still_open: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []

    for trade in positions:
        pnl = _pnl(snapshot, trade)
        opened_at = datetime.fromisoformat(str(trade["opened_at"]))
        age = max(0.0, (now - opened_at).total_seconds())
        reason = ""
        if pnl >= _float(trade["target_profit_usd"]):
            reason = "TARGET"
        elif pnl <= -_float(trade["hard_stop_usd"]):
            reason = "HARD_STOP"
        elif age >= _float(trade["max_hold_seconds"]):
            reason = "TIME"
        elif (
            age >= float(scalping_settings.SCALPING_MEDIUM_MIN_HOLD_BEFORE_THESIS_EXIT_SECONDS)
            and analysis["direction"] in {"BUY", "SELL"}
            and analysis["direction"] != trade["direction"]
            and pnl <= -float(scalping_settings.SCALPING_MEDIUM_THESIS_EXIT_LOSS_USD)
        ):
            reason = "THESIS_INVALID"
        if reason:
            final = min(pnl, _float(trade["target_profit_usd"])) if reason == "TARGET" else pnl
            record = {
                **trade,
                "status": "CLOSED",
                "closed_at": now.isoformat(),
                "exit_price": float(snapshot.bid if trade["direction"] == "BUY" else snapshot.ask),
                "observed_profit_usd": round(pnl, 4),
                "final_profit_usd": round(final, 4),
                "close_reason": reason,
                "hold_seconds": round(age, 3),
            }
            _append(record)
            closed.append(record)
        else:
            trade["current_profit_usd"] = round(pnl, 4)
            trade["hold_seconds"] = round(age, 3)
            still_open.append(trade)

    used = [str(value) for value in state.get("used_signal_ids", [])][-200:]
    block_reasons: list[str] = []
    direction = analysis["direction"]
    signal_id = analysis["signal_id"]
    episode_direction = str(state.get("episode_direction", ""))
    episode_consumed = bool(state.get("episode_consumed", False))
    if direction not in {"BUY", "SELL"}:
        episode_direction, episode_consumed = "", False
    elif direction != episode_direction:
        episode_direction, episode_consumed = direction, False
    if direction not in {"BUY", "SELL"}:
        block_reasons.append("no 3-of-4 directional consensus or entry is overextended")
    if not bool(scalping_settings.SCALPING_MEDIUM_ENTRY_ENABLED):
        block_reasons.append("medium-model entries disabled after failed historical validation")
    if float(snapshot.spread) > float(scalping_settings.SCALPING_MEDIUM_MAX_ENTRY_SPREAD_USD):
        block_reasons.append("spread above medium-model ceiling")
    if float(snapshot.quote_age_seconds) > float(scalping_settings.SCALPING_MEDIUM_MAX_QUOTE_AGE_SECONDS):
        block_reasons.append("stale quote")
    if (
        bool(scalping_settings.SCALPING_MEDIUM_USE_NEWS_VETO)
        and isinstance(news_risk, dict)
        and not bool(news_risk.get("allowed", True))
    ):
        block_reasons.extend(str(item) for item in news_risk.get("block_reasons", []))
    if (
        bool(scalping_settings.SCALPING_MEDIUM_USE_CROSS_MARKET_VETO)
        and isinstance(cross_market, dict)
        and cross_market.get("status") == "OK"
        and cross_market.get("gold_bias") in {"BUY", "SELL"}
        and cross_market.get("gold_bias") != direction
    ):
        block_reasons.append(
            f"MT5 USD-pressure context opposes entry ({cross_market.get('gold_bias')})"
        )
    if signal_id in used or not signal_id:
        block_reasons.append("M15 signal already used or unavailable")
    if episode_consumed:
        block_reasons.append("directional episode already entered; waiting for neutral/reversal re-arm")
    if len(still_open) >= int(scalping_settings.SCALPING_MEDIUM_MAX_OPEN_POSITIONS):
        block_reasons.append("two-position exposure cap reached")
    if still_open and any(item["direction"] != direction for item in still_open):
        block_reasons.append("hedging is disabled")

    opened: dict[str, Any] | None = None
    if not block_reasons:
        entry = float(snapshot.ask if direction == "BUY" else snapshot.bid)
        opened = {
            "status": "OPEN",
            "strategy_id": scalping_settings.SCALPING_MEDIUM_STRATEGY_ID,
            "symbol": snapshot.symbol,
            "opened_at": now.isoformat(),
            "signal_id": signal_id,
            "direction": direction,
            "entry_price": entry,
            "entry_spread_usd": round(float(snapshot.spread), 6),
            "lot_size": float(scalping_settings.SCALPING_MEDIUM_LOT_SIZE),
            "contract_size": float(snapshot.contract_size),
            "target_profit_usd": float(scalping_settings.SCALPING_MEDIUM_TARGET_USD),
            "hard_stop_usd": float(scalping_settings.SCALPING_MEDIUM_HARD_STOP_USD),
            "max_hold_seconds": float(scalping_settings.SCALPING_MEDIUM_MAX_HOLD_SECONDS),
            "signal": analysis,
            "current_profit_usd": round(-float(snapshot.spread) * float(scalping_settings.SCALPING_MEDIUM_LOT_SIZE) * float(snapshot.contract_size), 4),
        }
        still_open.append(opened)
        used.append(signal_id)
        episode_consumed = True

    state.update({
        "positions": still_open,
        "used_signal_ids": used[-200:],
        "episode_direction": episode_direction,
        "episode_consumed": episode_consumed,
        "updated_at": now.isoformat(),
    })
    _save_state(state)
    action = "OPEN" if opened else "CLOSE" if closed else "MONITOR" if still_open else "WAIT"
    return {
        "action": action,
        "analysis": analysis,
        "opened": opened,
        "closed": closed,
        "positions": still_open,
        "block_reasons": block_reasons,
        "news_risk": news_risk or {},
        "cross_market": cross_market or {},
    }


def medium_horizon_metrics(*, since: datetime | None = None) -> dict[str, Any]:
    values: list[float] = []
    path = Path(scalping_settings.SCALPING_MEDIUM_HISTORY_PATH)
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
                closed_at = datetime.fromisoformat(str(row["closed_at"]))
                if row.get("strategy_id") != scalping_settings.SCALPING_MEDIUM_STRATEGY_ID:
                    continue
                if since is None or closed_at >= since:
                    values.append(float(row["final_profit_usd"]))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
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
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else (999.0 if gross_profit else 0.0),
    }
