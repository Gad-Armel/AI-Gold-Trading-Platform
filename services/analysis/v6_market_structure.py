from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState


_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_LAST_RENDER_EPOCH: dict[str, float] = {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return default if math.isnan(result) else result
    except (TypeError, ValueError):
        return default


def _direction(value: Any) -> str:
    text = str(value or "NEUTRAL").upper()
    if text in {"BUY", "BULL", "BULLISH", "LONG"}:
        return "BUY"
    if text in {"SELL", "BEAR", "BEARISH", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def _closed_frame(snapshot: ScalpingSnapshotState, timeframe: str) -> pd.DataFrame:
    value = snapshot.candles.get(timeframe)
    if not isinstance(value, pd.DataFrame) or value.empty:
        return pd.DataFrame()
    required = {"time", "open", "high", "low", "close"}
    if not required.issubset(value.columns):
        return pd.DataFrame()
    frame = value.iloc[:-1].copy() if len(value) > 1 else value.copy()
    for column in ("open", "high", "low", "close", "tick_volume"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    return frame.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    previous = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous).abs(),
            (frame["low"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return ranges.ewm(alpha=1.0 / period, adjust=False).mean()


def _swings(frame: pd.DataFrame, window: int = 2) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []
    if len(frame) < window * 2 + 3:
        return highs, lows
    high_values = frame["high"].to_numpy(float)
    low_values = frame["low"].to_numpy(float)
    for index in range(window, len(frame) - window):
        left = index - window
        right = index + window + 1
        if high_values[index] >= np.max(high_values[left:right]) and high_values[index] > np.max(
            np.delete(high_values[left:right], window)
        ):
            highs.append({"index": index, "price": float(high_values[index]), "time": frame.iloc[index]["time"]})
        if low_values[index] <= np.min(low_values[left:right]) and low_values[index] < np.min(
            np.delete(low_values[left:right], window)
        ):
            lows.append({"index": index, "price": float(low_values[index]), "time": frame.iloc[index]["time"]})
    return highs, lows


def _timeframe_trend(frame: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    if len(frame) < 55:
        return {"timeframe": timeframe, "direction": "NEUTRAL", "confidence": 0.0, "reason": "insufficient_bars"}
    atr = max(_float(_atr(frame).iloc[-1]), 1e-9)
    close = frame["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema_gap = _float(ema20.iloc[-1] - ema50.iloc[-1]) / atr
    slope = _float(ema20.iloc[-1] - ema20.iloc[-6]) / atr
    highs, lows = _swings(frame, window=2)
    swing_vote = 0
    if len(highs) >= 2 and len(lows) >= 2:
        higher_high = highs[-1]["price"] > highs[-2]["price"]
        higher_low = lows[-1]["price"] > lows[-2]["price"]
        lower_high = highs[-1]["price"] < highs[-2]["price"]
        lower_low = lows[-1]["price"] < lows[-2]["price"]
        if higher_high and higher_low:
            swing_vote = 1
        elif lower_high and lower_low:
            swing_vote = -1
    ema_vote = 1 if ema_gap > 0.05 and slope > 0.02 else -1 if ema_gap < -0.05 and slope < -0.02 else 0
    combined = ema_vote + swing_vote
    direction = "BUY" if combined > 0 else "SELL" if combined < 0 else "NEUTRAL"
    confidence = min(1.0, 0.25 + 0.25 * abs(combined) + 0.15 * min(abs(ema_gap), 1.5) + 0.10 * min(abs(slope), 1.0))
    return {
        "timeframe": timeframe,
        "direction": direction,
        "confidence": round(confidence if direction != "NEUTRAL" else 0.0, 6),
        "ema_gap_atr": round(ema_gap, 6),
        "ema20_slope_atr": round(slope, 6),
        "swing_vote": swing_vote,
        "ema_vote": ema_vote,
        "last_swing_high": round(_float(highs[-1]["price"]), 5) if highs else None,
        "last_swing_low": round(_float(lows[-1]["price"]), 5) if lows else None,
    }


def _htf_family(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    weights = {"H4": 0.45, "H1": 0.35, "M15": 0.20}
    details = {name: _timeframe_trend(frames[name], name) for name in weights}
    score = 0.0
    confidence_weight = 0.0
    for name, weight in weights.items():
        item = details[name]
        signed = 1.0 if item["direction"] == "BUY" else -1.0 if item["direction"] == "SELL" else 0.0
        confidence = _float(item.get("confidence"))
        score += signed * weight * confidence
        confidence_weight += weight * confidence
    direction = "BUY" if score >= 0.18 else "SELL" if score <= -0.18 else "NEUTRAL"
    return {
        "name": "HTF_TREND",
        "direction": direction,
        "confidence": round(min(1.0, abs(score) / 0.65), 6) if direction != "NEUTRAL" else 0.0,
        "signed_score": round(score, 6),
        "timeframes": details,
        "agreement_strength": round(confidence_weight, 6),
    }


def _cluster_levels(points: list[dict[str, Any]], tolerance: float, kind: str) -> list[dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for point in sorted(points, key=lambda item: item["price"]):
        if not clusters:
            clusters.append([point])
            continue
        center = float(np.average([item["price"] for item in clusters[-1]], weights=[item["weight"] for item in clusters[-1]]))
        if abs(point["price"] - center) <= tolerance:
            clusters[-1].append(point)
        else:
            clusters.append([point])
    result: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for cluster in clusters:
        prices = [item["price"] for item in cluster]
        weights = [item["weight"] for item in cluster]
        center = float(np.average(prices, weights=weights))
        last_time = max(item["time"] for item in cluster)
        age_hours = max(0.0, (now - last_time.to_pydatetime()).total_seconds() / 3600.0)
        freshness = math.exp(-age_hours / 96.0)
        strength = sum(weights) * (0.55 + 0.45 * freshness)
        result.append(
            {
                "kind": kind,
                "center": round(center, 5),
                "lower": round(min(prices) - tolerance * 0.35, 5),
                "upper": round(max(prices) + tolerance * 0.35, 5),
                "touches": len(cluster),
                "strength": round(strength, 6),
                "last_touch": last_time.isoformat(),
                "timeframes": sorted({item["timeframe"] for item in cluster}),
            }
        )
    return sorted(result, key=lambda item: item["strength"], reverse=True)


def _level_family(frames: dict[str, pd.DataFrame], price: float) -> dict[str, Any]:
    timeframe_weights = {"M15": 1.0, "H1": 1.6, "H4": 2.2}
    points_high: list[dict[str, Any]] = []
    points_low: list[dict[str, Any]] = []
    for timeframe, weight in timeframe_weights.items():
        frame = frames[timeframe]
        highs, lows = _swings(frame, window=2)
        for point in highs[-12:]:
            points_high.append({**point, "weight": weight, "timeframe": timeframe})
        for point in lows[-12:]:
            points_low.append({**point, "weight": weight, "timeframe": timeframe})
    m15_atr = max(_float(_atr(frames["M15"]).iloc[-1]) if not frames["M15"].empty else 0.0, 0.01)
    tolerance = max(m15_atr * float(getattr(scalping_settings, "SCALPING_V6_LEVEL_CLUSTER_ATR", 0.22)), 0.08)
    resistances = _cluster_levels(points_high, tolerance, "RESISTANCE")
    supports = _cluster_levels(points_low, tolerance, "SUPPORT")
    nearest_support = min((item for item in supports if item["center"] <= price), key=lambda item: price - item["center"], default=None)
    nearest_resistance = min((item for item in resistances if item["center"] >= price), key=lambda item: item["center"] - price, default=None)

    m15 = frames["M15"]
    recent = m15.tail(4)
    direction = "NEUTRAL"
    confidence = 0.0
    event = "NONE"
    if len(recent) >= 3:
        last = recent.iloc[-1]
        previous = recent.iloc[-2]
        body = abs(_float(last["close"] - last["open"]))
        lower_wick = min(_float(last["open"]), _float(last["close"])) - _float(last["low"])
        upper_wick = _float(last["high"]) - max(_float(last["open"]), _float(last["close"]))
        near_support = bool(nearest_support and price - nearest_support["upper"] <= m15_atr * 0.45)
        near_resistance = bool(nearest_resistance and nearest_resistance["lower"] - price <= m15_atr * 0.45)
        bullish_rejection = last["close"] > last["open"] and lower_wick > max(body * 1.2, m15_atr * 0.08)
        bearish_rejection = last["close"] < last["open"] and upper_wick > max(body * 1.2, m15_atr * 0.08)
        swept_support = bool(nearest_support and last["low"] < nearest_support["lower"] and last["close"] > nearest_support["center"])
        swept_resistance = bool(nearest_resistance and last["high"] > nearest_resistance["upper"] and last["close"] < nearest_resistance["center"])
        broke_resistance = bool(nearest_resistance and last["close"] > nearest_resistance["upper"] and previous["close"] <= nearest_resistance["upper"])
        broke_support = bool(nearest_support and last["close"] < nearest_support["lower"] and previous["close"] >= nearest_support["lower"])
        if (near_support and bullish_rejection) or swept_support or broke_resistance:
            direction = "BUY"
            event = "SUPPORT_REJECTION" if near_support and bullish_rejection else "LIQUIDITY_SWEEP" if swept_support else "BOS_UP"
            confidence = 0.62 if event != "BOS_UP" else 0.68
        elif (near_resistance and bearish_rejection) or swept_resistance or broke_support:
            direction = "SELL"
            event = "RESISTANCE_REJECTION" if near_resistance and bearish_rejection else "LIQUIDITY_SWEEP" if swept_resistance else "BOS_DOWN"
            confidence = 0.62 if event != "BOS_DOWN" else 0.68
        else:
            # A confirmed sequence or rolling-range break can vote even away from a level.
            highs, lows = _swings(m15, window=2)
            prior_window = m15.iloc[-22:-2] if len(m15) >= 24 else m15.iloc[:-2]
            rolling_high = _float(prior_window["high"].max(), 0.0) if not prior_window.empty else 0.0
            rolling_low = _float(prior_window["low"].min(), 0.0) if not prior_window.empty else 0.0
            if (highs and last["close"] > highs[-1]["price"] + tolerance * 0.25) or (rolling_high and last["close"] > rolling_high):
                direction, confidence, event = "BUY", 0.58, "STRUCTURE_BREAK_UP"
            elif (lows and last["close"] < lows[-1]["price"] - tolerance * 0.25) or (rolling_low and last["close"] < rolling_low):
                direction, confidence, event = "SELL", 0.58, "STRUCTURE_BREAK_DOWN"
    room_buy = _float(nearest_resistance["lower"] - price, 999.0) if nearest_resistance else 999.0
    room_sell = _float(price - nearest_support["upper"], 999.0) if nearest_support else 999.0
    return {
        "name": "SUPPORT_RESISTANCE",
        "direction": direction,
        "confidence": round(confidence, 6),
        "event": event,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "room_buy_usd": round(room_buy, 5),
        "room_sell_usd": round(room_sell, 5),
        "cluster_tolerance_usd": round(tolerance, 5),
        "supports": supports[:8],
        "resistances": resistances[:8],
    }


def _find_order_blocks(frame: pd.DataFrame, timeframe: str) -> list[dict[str, Any]]:
    if len(frame) < 35:
        return []
    working = frame.copy()
    working["atr"] = _atr(working)
    blocks: list[dict[str, Any]] = []
    lookback = min(80, len(working) - 8)
    start = max(8, len(working) - lookback)
    for index in range(start, len(working) - 3):
        candle = working.iloc[index]
        atr = max(_float(candle["atr"]), 1e-9)
        prior_high = _float(working.iloc[max(0, index - 7):index]["high"].max())
        prior_low = _float(working.iloc[max(0, index - 7):index]["low"].min())
        future = working.iloc[index + 1:index + 4]
        if future.empty:
            continue
        bullish_origin = candle["close"] < candle["open"]
        bearish_origin = candle["close"] > candle["open"]
        bullish_displacement = _float(future["close"].max() - candle["low"]) >= atr * 1.10 and _float(future["close"].max()) > prior_high
        bearish_displacement = _float(candle["high"] - future["close"].min()) >= atr * 1.10 and _float(future["close"].min()) < prior_low
        direction = "BUY" if bullish_origin and bullish_displacement else "SELL" if bearish_origin and bearish_displacement else "NEUTRAL"
        if direction == "NEUTRAL":
            continue
        if direction == "BUY":
            lower = _float(candle["low"])
            upper = max(_float(candle["open"]), _float(candle["close"]))
        else:
            lower = min(_float(candle["open"]), _float(candle["close"]))
            upper = _float(candle["high"])
        after = working.iloc[index + 4:]
        invalidated = bool((after["close"] < lower).any()) if direction == "BUY" else bool((after["close"] > upper).any())
        touches = int(((after["low"] <= upper) & (after["high"] >= lower)).sum()) if not after.empty else 0
        if invalidated or touches > 3:
            continue
        displacement = (
            _float(future["high"].max() - lower) / atr
            if direction == "BUY"
            else _float(upper - future["low"].min()) / atr
        )
        freshness = max(0.0, 1.0 - (len(working) - index) / 90.0)
        confidence = min(1.0, 0.45 + 0.12 * min(displacement, 2.5) + 0.12 * freshness - 0.07 * touches)
        blocks.append(
            {
                "direction": direction,
                "timeframe": timeframe,
                "lower": round(lower, 5),
                "upper": round(upper, 5),
                "formed_at": candle["time"].isoformat(),
                "touches": touches,
                "displacement_atr": round(displacement, 5),
                "confidence": round(confidence, 6),
            }
        )
    return blocks[-12:]


def _order_block_family(frames: dict[str, pd.DataFrame], price: float) -> dict[str, Any]:
    blocks = _find_order_blocks(frames["H1"], "H1") + _find_order_blocks(frames["M15"], "M15")
    m15_atr = max(_float(_atr(frames["M15"]).iloc[-1]) if not frames["M15"].empty else 0.0, 0.01)
    weight = {"H1": 1.25, "M15": 1.0}
    for block in blocks:
        distance = 0.0 if block["lower"] <= price <= block["upper"] else min(abs(price - block["lower"]), abs(price - block["upper"]))
        block["distance_atr"] = round(distance / m15_atr, 6)
        block["weighted_confidence"] = round(_float(block["confidence"]) * weight.get(block["timeframe"], 1.0), 6)
    nearby = [block for block in blocks if _float(block.get("distance_atr"), 999.0) <= 0.55]
    nearby.sort(key=lambda block: (_float(block.get("distance_atr")), -_float(block.get("weighted_confidence"))))
    best = nearby[0] if nearby else None
    direction = _direction(best.get("direction")) if best else "NEUTRAL"
    confidence = min(1.0, _float(best.get("weighted_confidence"))) if best else 0.0
    bullish = sorted((item for item in blocks if item["direction"] == "BUY"), key=lambda item: _float(item.get("distance_atr")))
    bearish = sorted((item for item in blocks if item["direction"] == "SELL"), key=lambda item: _float(item.get("distance_atr")))
    return {
        "name": "ORDER_BLOCK",
        "direction": direction,
        "confidence": round(confidence, 6),
        "active_block": best,
        "nearest_bullish": bullish[0] if bullish else None,
        "nearest_bearish": bearish[0] if bearish else None,
        "blocks": sorted(blocks, key=lambda item: _float(item.get("distance_atr")))[:10],
    }


def _cache_key(snapshot: ScalpingSnapshotState) -> tuple[Any, ...]:
    values: list[Any] = [snapshot.symbol, round(float(snapshot.mid), 2)]
    for timeframe in ("M15", "H1", "H4"):
        frame = _closed_frame(snapshot, timeframe)
        if frame.empty:
            values.extend([timeframe, 0, None])
        else:
            last = frame.iloc[-1]
            values.extend([timeframe, len(frame), str(last["time"]), round(_float(last["close"]), 5)])
    return tuple(values)


def build_v6_market_structure(snapshot: ScalpingSnapshotState) -> dict[str, Any]:
    key = _cache_key(snapshot)
    cached = _CACHE.get(key)
    if cached is not None:
        result = dict(cached)
        result["cache_hit"] = True
        return result
    frames = {name: _closed_frame(snapshot, name) for name in ("M15", "H1", "H4")}
    if any(frame.empty for frame in frames.values()):
        return {
            "valid": False,
            "consensus_direction": "NEUTRAL",
            "consensus_votes": 0,
            "required_votes": int(getattr(scalping_settings, "SCALPING_V6_STRUCTURE_MIN_VOTES", 2)),
            "location_safe": False,
            "reason": "Missing M15/H1/H4 closed-candle data.",
            "cache_hit": False,
        }
    htf = _htf_family(frames)
    levels = _level_family(frames, float(snapshot.mid))
    order_blocks = _order_block_family(frames, float(snapshot.mid))
    families = [htf, levels, order_blocks]
    buy_votes = sum(1 for item in families if item["direction"] == "BUY")
    sell_votes = sum(1 for item in families if item["direction"] == "SELL")
    required = int(getattr(scalping_settings, "SCALPING_V6_STRUCTURE_MIN_VOTES", 2))
    consensus = "BUY" if buy_votes >= required and buy_votes > sell_votes else "SELL" if sell_votes >= required and sell_votes > buy_votes else "NEUTRAL"
    winning = [item for item in families if item["direction"] == consensus]
    confidence = float(np.mean([_float(item.get("confidence")) for item in winning])) if winning else 0.0
    target_room = float(getattr(scalping_settings, "SCALPING_V6_TARGET_USD", 0.85)) + float(snapshot.spread)
    room = levels["room_buy_usd"] if consensus == "BUY" else levels["room_sell_usd"] if consensus == "SELL" else 0.0
    location_safe = consensus in {"BUY", "SELL"} and room + 1e-9 >= target_room
    opposing_block = order_blocks.get("nearest_bearish") if consensus == "BUY" else order_blocks.get("nearest_bullish") if consensus == "SELL" else None
    if opposing_block and _float(opposing_block.get("distance_atr"), 999.0) <= 0.30:
        location_safe = False
    result = {
        "valid": True,
        "consensus_direction": consensus,
        "consensus_votes": max(buy_votes, sell_votes),
        "required_votes": required,
        "buy_votes": buy_votes,
        "sell_votes": sell_votes,
        "confidence": round(confidence, 6),
        "location_safe": bool(location_safe),
        "room_to_target_usd": round(room, 5),
        "required_room_usd": round(target_room, 5),
        "families": {"htf_trend": htf, "support_resistance": levels, "order_block": order_blocks},
        "reason": (
            f"{consensus} structural consensus {max(buy_votes, sell_votes)}/{len(families)}."
            if consensus != "NEUTRAL"
            else f"No 2-of-3 structural consensus: BUY={buy_votes}, SELL={sell_votes}."
        ),
        "cache_hit": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _CACHE.clear()
    _CACHE[key] = result
    return dict(result)


def maybe_render_v6_market_map(
    snapshot: ScalpingSnapshotState,
    analysis: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    if not bool(getattr(scalping_settings, "SCALPING_V6_CHART_EXPORT_ENABLED", True)):
        return {"rendered": False, "reason": "disabled"}
    interval = float(getattr(scalping_settings, "SCALPING_V6_CHART_EXPORT_INTERVAL_SECONDS", 300.0))
    now = time.time()
    last = _LAST_RENDER_EPOCH.get(snapshot.symbol, 0.0)
    if not force and now - last < interval:
        return {"rendered": False, "reason": "throttled", "seconds_until_next": round(interval - (now - last), 2)}
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except Exception as exc:
        return {"rendered": False, "reason": f"matplotlib_unavailable: {exc}"}
    frames = {name: _closed_frame(snapshot, name).tail(80) for name in ("M15", "H1")}
    if any(frame.empty for frame in frames.values()):
        return {"rendered": False, "reason": "missing_frames"}
    figure, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=False)
    families = analysis.get("families", {}) if isinstance(analysis, dict) else {}
    levels = families.get("support_resistance", {}) if isinstance(families, dict) else {}
    order_blocks = families.get("order_block", {}) if isinstance(families, dict) else {}
    for axis, timeframe in zip(axes, ("H1", "M15")):
        frame = frames[timeframe].reset_index(drop=True)
        for index, row in frame.iterrows():
            up = row["close"] >= row["open"]
            axis.vlines(index, row["low"], row["high"], linewidth=0.8)
            lower = min(row["open"], row["close"])
            height = max(abs(row["close"] - row["open"]), 0.005)
            axis.add_patch(Rectangle((index - 0.32, lower), 0.64, height, fill=up, alpha=0.55))
        for level in levels.get("supports", [])[:4]:
            axis.axhline(level["center"], linestyle="--", linewidth=0.8, alpha=0.55)
        for level in levels.get("resistances", [])[:4]:
            axis.axhline(level["center"], linestyle=":", linewidth=0.8, alpha=0.55)
        start_time = frame.iloc[0]["time"]
        for block in order_blocks.get("blocks", [])[:8]:
            if block.get("timeframe") != timeframe:
                continue
            formed = pd.Timestamp(block["formed_at"])
            candidates = frame.index[frame["time"] >= formed].tolist()
            x0 = candidates[0] if candidates else 0
            axis.add_patch(
                Rectangle(
                    (x0, block["lower"]),
                    max(1, len(frame) - x0),
                    block["upper"] - block["lower"],
                    alpha=0.12,
                )
            )
        axis.axhline(snapshot.mid, linewidth=1.0)
        axis.set_title(f"{snapshot.symbol} {timeframe} | closed candles | {analysis.get('consensus_direction')} {analysis.get('consensus_votes')}/3")
        axis.grid(alpha=0.15)
    figure.tight_layout()
    date_folder = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = Path(getattr(scalping_settings, "SCALPING_V6_CHART_EXPORT_FOLDER", "logs/v6_market_maps")) / date_folder
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{snapshot.symbol}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
    path = folder / filename
    figure.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(figure)
    _LAST_RENDER_EPOCH[snapshot.symbol] = now
    return {"rendered": True, "path": str(path)}
