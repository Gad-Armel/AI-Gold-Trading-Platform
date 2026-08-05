from __future__ import annotations

"""Read-only, multi-horizon XAUUSD decision support.

This module produces advisory levels from completed broker candles. It has no
execution imports and never represents a heuristic score as calibrated odds.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from models.scalping_state import ScalpingSnapshotState
from services.analysis.verified_market_context import build_verified_market_context
from services.analysis.v6_market_structure import build_v6_market_structure

HORIZONS = {
    "SCALP": {"frames": ("M1", "M5", "M15"), "anchor": "M5", "minutes": 5, "atr_mult": (0.45, 0.75, 1.10), "stop": 0.65},
    "INTRADAY": {"frames": ("M5", "M15", "H1"), "anchor": "M15", "minutes": 30, "atr_mult": (0.60, 1.00, 1.50), "stop": 0.85},
    "SWING": {"frames": ("M15", "H1", "H4"), "anchor": "H1", "minutes": 120, "atr_mult": (0.75, 1.25, 2.00), "stop": 1.00},
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return default if pd.isna(result) else result
    except (TypeError, ValueError):
        return default


def _closed(snapshot: ScalpingSnapshotState, timeframe: str) -> pd.DataFrame:
    raw = snapshot.candles.get(timeframe) if isinstance(snapshot.candles, dict) else None
    frame = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
    required = {"time", "open", "high", "low", "close"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    for name in ("open", "high", "low", "close"):
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    frame = frame.dropna(subset=list(required)).sort_values("time")
    return frame.iloc[:-1].copy() if len(frame) > 1 else pd.DataFrame()


def _view(frame: pd.DataFrame) -> dict[str, Any]:
    if len(frame) < 55:
        return {"direction": "NEUTRAL", "strength": 0.0, "atr": 0.0, "reason": f"only {len(frame)}/55 closed bars"}
    close, high, low = frame["close"], frame["high"], frame["low"]
    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()
    baseline = close.ewm(span=50, adjust=False).mean()
    previous = close.shift(1)
    tr = pd.concat(((high-low).abs(), (high-previous).abs(), (low-previous).abs()), axis=1).max(axis=1)
    atr = max(_float(tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]), 0.01)
    separation = _float(fast.iloc[-1] - slow.iloc[-1]) / atr
    slope = _float(fast.iloc[-1] - fast.iloc[-4]) / atr
    price_side = _float(close.iloc[-1] - baseline.iloc[-1]) / atr
    bullish = separation > 0.05 and slope > 0 and price_side > 0
    bearish = separation < -0.05 and slope < 0 and price_side < 0
    direction = "BUY" if bullish else "SELL" if bearish else "NEUTRAL"
    strength = min(1.0, (abs(separation) + abs(slope) + min(abs(price_side), 1.5)) / 2.5) if direction != "NEUTRAL" else 0.0
    return {"direction": direction, "strength": round(strength, 4), "atr": round(atr, 6), "last_close": round(_float(close.iloc[-1]), 6)}


def _round_price(value: float, point: float) -> float:
    digits = max(0, min(8, len(str(point).split(".")[-1].rstrip("0")))) if point < 1 else 0
    return round(value, digits)


def _levels(snapshot: ScalpingSnapshotState, direction: str, atr: float, config: dict[str, Any]) -> dict[str, Any]:
    entry = snapshot.ask if direction == "BUY" else snapshot.bid
    sign = 1.0 if direction == "BUY" else -1.0
    spread_buffer = max(snapshot.spread, snapshot.point)
    zone_half = max(atr * 0.10, spread_buffer)
    return {
        "entry_reference": _round_price(entry, snapshot.point),
        "entry_zone": [_round_price(entry-zone_half, snapshot.point), _round_price(entry+zone_half, snapshot.point)],
        "tp1": _round_price(entry + sign * atr * config["atr_mult"][0], snapshot.point),
        "tp2": _round_price(entry + sign * atr * config["atr_mult"][1], snapshot.point),
        "tp3": _round_price(entry + sign * atr * config["atr_mult"][2], snapshot.point),
        "sl": _round_price(entry - sign * atr * config["stop"], snapshot.point),
        "level_basis": "ATR-derived scenario levels; not guaranteed fills or financial advice.",
    }


def build_gold_advisory(snapshot: ScalpingSnapshotState) -> dict[str, Any]:
    now = snapshot.system_timestamp or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    verified = build_verified_market_context(snapshot)
    structure = build_v6_market_structure(snapshot)
    views = {name: _view(_closed(snapshot, name)) for name in ("M1", "M5", "M15", "H1", "H4")}
    outputs: dict[str, Any] = {}
    for name, config in HORIZONS.items():
        selected = [views[item] for item in config["frames"]]
        buy = sum(item["direction"] == "BUY" for item in selected)
        sell = sum(item["direction"] == "SELL" for item in selected)
        direction = "BUY" if buy >= 2 and buy > sell else "SELL" if sell >= 2 and sell > buy else "WAIT"
        supporting = [item for item in selected if item["direction"] == direction]
        evidence = (sum(item["strength"] for item in supporting) / len(selected)) if supporting else 0.0
        score = min(100.0, 35.0 + evidence * 50.0 + max(buy, sell) * 5.0) if direction != "WAIT" else max(buy, sell) * 15.0
        reasons: list[str] = [f"{buy}/{len(selected)} BUY and {sell}/{len(selected)} SELL closed-bar votes"]
        blocks: list[str] = []
        atr = _float(views[config["anchor"]].get("atr"))
        vwap = abs(_float(verified.get("vwap_distance_atr"), 999.0))
        if snapshot.quote_age_seconds > 3.0: blocks.append("stale quote")
        if snapshot.spread > 0.30: blocks.append(f"spread ${snapshot.spread:.2f} exceeds advisory ceiling")
        if vwap > 2.5: blocks.append(f"price is extended {vwap:.2f} ATR from VWAP")
        structure_direction = str(structure.get("direction", "NEUTRAL"))
        if direction in {"BUY", "SELL"} and structure_direction in {"BUY", "SELL"} and structure_direction != direction:
            blocks.append(f"market structure opposes {direction}")
        if atr <= 0: blocks.append("anchor ATR unavailable")
        if score < 60.0: blocks.append("directional evidence below 60/100")
        action = direction if direction in {"BUY", "SELL"} and not blocks else "WAIT"
        review_at = now + timedelta(minutes=max(1, int(config["minutes"] / 3)))
        valid_until = now + timedelta(minutes=config["minutes"])
        outputs[name] = {
            "action": action, "bias": direction, "directional_score": round(score, 2),
            "calibrated_probability": None,
            "probability_note": "Unavailable until this exact advisor has sufficient chronological out-of-sample outcomes.",
            "supporting_timeframes": list(config["frames"]), "votes": {"BUY": buy, "SELL": sell},
            "review_at": review_at.isoformat(), "valid_until": valid_until.isoformat(),
            "valid_for_minutes": config["minutes"], "reasons": reasons, "blocks": blocks,
            "levels": _levels(snapshot, direction, atr, config) if action in {"BUY", "SELL"} else {},
        }
    actionable = [name for name, item in outputs.items() if item["action"] in {"BUY", "SELL"}]
    directions = {outputs[name]["action"] for name in actionable}
    consensus = directions.pop() if len(directions) == 1 else "WAIT"
    return {
        "generated_at": now.isoformat(), "symbol": snapshot.symbol, "bid": snapshot.bid, "ask": snapshot.ask,
        "spread": round(snapshot.spread, 6), "session": snapshot.session, "overall": consensus,
        "actionable_horizons": actionable, "horizons": outputs, "views": views,
        "verified_context": verified, "structure": structure,
        "execution_enabled": False, "orders_sent": False,
        "disclaimer": "Decision support only. WAIT is a valid forecast. Validate prospectively before risking capital.",
    }
