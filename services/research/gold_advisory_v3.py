from __future__ import annotations

"""MT5 tick-flow research advisor.

V3 is kept as a compatibility module, but the microstructure calculation is
stronger than the original version:
- spread-normalized movement,
- directional efficiency,
- realized volatility,
- tick rate,
- acceleration/reversal,
- quote-flow pressure,
- optional microprice pressure,
- DOM is diagnostic only.

No component is presented as calibrated probability.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from services.market_data.gold_broker_clock import to_broker_time
from config import gold_consensus_settings as settings


HORIZONS = {
    "SCALP": {"windows": (1, 5, 15), "minutes": 2},
    "INTRADAY": {"windows": (15, 60, 300), "minutes": 10},
    "SWING": {"windows": (60, 300, 900), "minutes": 30},
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return default if not np.isfinite(x) else x
    except (TypeError, ValueError):
        return default


def _depth(mt5: Any, symbol: str) -> dict[str, Any]:
    subscribed = False
    try:
        subscribed = bool(mt5.market_book_add(symbol))
        if not subscribed:
            return {"available": False, "imbalance": 0.0, "reason": "MT5 market depth unavailable."}

        rows = mt5.market_book_get(symbol) or ()
        buy_types = {
            int(getattr(mt5, "BOOK_TYPE_BUY", 2)),
            int(getattr(mt5, "BOOK_TYPE_BUY_MARKET", 4)),
        }
        sell_types = {
            int(getattr(mt5, "BOOK_TYPE_SELL", 1)),
            int(getattr(mt5, "BOOK_TYPE_SELL_MARKET", 3)),
        }

        buy = sum(
            _f(getattr(row, "volume_dbl", getattr(row, "volume", 0.0)))
            for row in rows
            if int(getattr(row, "type", -1)) in buy_types
        )
        sell = sum(
            _f(getattr(row, "volume_dbl", getattr(row, "volume", 0.0)))
            for row in rows
            if int(getattr(row, "type", -1)) in sell_types
        )
        total = buy + sell
        if total <= 0:
            return {"available": False, "imbalance": 0.0, "reason": "DOM contains no usable volume."}

        return {
            "available": True,
            "buy_volume": round(buy, 4),
            "sell_volume": round(sell, 4),
            "imbalance": round((buy - sell) / total, 4),
            "reason": "Broker-specific DOM snapshot; not centralized exchange order flow.",
        }
    except Exception as exc:
        return {
            "available": False,
            "imbalance": 0.0,
            "reason": f"DOM error: {type(exc).__name__}.",
        }
    finally:
        if subscribed:
            try:
                mt5.market_book_release(symbol)
            except Exception:
                pass


def _tick_frame(rows: Any) -> pd.DataFrame:
    try:
        frame = pd.DataFrame(rows)
    except (ValueError, TypeError):
        return pd.DataFrame(columns=['timestamp', 'bid', 'ask', 'mid', 'spread'])
    if frame.empty or not {"bid", "ask"}.issubset(frame.columns):
        return pd.DataFrame(columns=['timestamp', 'bid', 'ask', 'mid', 'spread'])

    for col in ("bid", "ask"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    if "time_msc" in frame:
        frame["timestamp"] = pd.to_numeric(frame["time_msc"], errors="coerce") / 1000.0
    elif "time" in frame:
        frame["timestamp"] = pd.to_numeric(frame["time"], errors="coerce")
    else:
        return pd.DataFrame(columns=['timestamp', 'bid', 'ask', 'mid', 'spread'])

    frame = frame.dropna(subset=["timestamp", "bid", "ask"])
    frame = frame[np.isfinite(frame[['timestamp', 'bid', 'ask']]).all(axis=1)]
    frame = frame[(frame["bid"] > 0) & (frame["ask"] >= frame["bid"])]
    frame = frame.sort_values("timestamp").drop_duplicates(
        subset=["timestamp", "bid", "ask"], keep="last"
    )
    frame["mid"] = (frame["bid"] + frame["ask"]) / 2.0
    frame["spread"] = frame["ask"] - frame["bid"]

    # Optional quote-volume fields from MT5.
    for col in ("volume", "volume_real"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)

    return frame.reset_index(drop=True)


def _window(frame: pd.DataFrame, seconds: int, now_timestamp: float) -> dict[str, Any]:
    if frame.empty or not {'timestamp','bid','ask','mid','spread'}.issubset(frame.columns):
        return dict(seconds=seconds, direction='NEUTRAL', evidence=0., data_quality=0., ticks=0,
                    reason='Tick history unavailable or malformed')
    sample = frame[(frame["timestamp"] >= now_timestamp - float(seconds))
                   & (frame["timestamp"] <= now_timestamp)].copy()
    minimum = 4 if seconds <= 5 else 8 if seconds <= 60 else 12
    if len(sample) < minimum:
        return {
            "seconds": seconds,
            "direction": "NEUTRAL",
            "evidence": 0.0,
            "data_quality": 0.0,
            "ticks": len(sample),
            "reason": f"only {len(sample)}/{minimum} ticks",
        }

    changes = sample["mid"].diff().dropna()
    nonzero = changes[changes != 0.0]

    if nonzero.empty:
        return {
            "seconds": seconds,
            "direction": "NEUTRAL",
            "evidence": 0.0,
            "data_quality": 0.2,
            "ticks": len(sample),
            "reason": "no mid-price movement",
        }

    signs = np.sign(nonzero.to_numpy(dtype=float))
    tick_imbalance = float(np.mean(signs))

    net_move = float(sample["mid"].iloc[-1] - sample["mid"].iloc[0])
    path = float(np.abs(changes).sum())
    efficiency = abs(net_move) / path if path > 0 else 0.0

    median_spread = max(float(sample["spread"].median()), 0.01)
    spread_ratio = net_move / median_spread
    spread_expansion = (
        float(sample["spread"].iloc[-1] - sample["spread"].iloc[0]) / median_spread
    )

    realized = float(np.sqrt(np.square(changes.to_numpy(dtype=float)).sum()))
    vol_normalized_move = abs(net_move) / max(realized, median_spread)

    # Quote pressure: direction of bid/ask updates. This is a quote-flow proxy,
    # not aggressor-side trade classification.
    bid_pressure = float(np.sign(sample["bid"].diff().fillna(0.0)).mean())
    ask_pressure = float(np.sign(sample["ask"].diff().fillna(0.0)).mean())
    quote_pressure = (bid_pressure + ask_pressure) / 2.0

    # Reversal rate: high reversal is a warning for breakout continuation.
    sign_changes = np.sum(signs[1:] != signs[:-1]) if len(signs) > 1 else 0
    reversal_rate = float(sign_changes / max(1, len(signs) - 1))

    # Acceleration: compare the second half and first half of the window.
    midpoint = max(1, len(nonzero) // 2)
    first = float(np.mean(signs[:midpoint]))
    second = float(np.mean(signs[midpoint:]))
    acceleration = second - first

    microprice_pressure = 0.0
    microprice_available = False
    # MqlTick volume and volume_real represent the SAME last-trade volume
    # at different precision, not bid-size and ask-size. Microprice requires
    # synchronized depth sizes and cannot be inferred from these fields.

    bullish = (
        tick_imbalance >= 0.12
        and quote_pressure >= 0.04
        and spread_ratio >= 0.12
        and efficiency >= 0.20
    )
    bearish = (
        tick_imbalance <= -0.12
        and quote_pressure <= -0.04
        and spread_ratio <= -0.12
        and efficiency >= 0.20
    )

    direction = "BUY" if bullish else "SELL" if bearish else "NEUTRAL"

    if direction == "NEUTRAL":
        evidence = 0.0
    else:
        aligned = (
            0.35 * min(abs(tick_imbalance) / 0.50, 1.0)
            + 0.20 * min(abs(quote_pressure) / 0.40, 1.0)
            + 0.20 * min(abs(spread_ratio) / 2.0, 1.0)
            + 0.15 * min(efficiency / 0.80, 1.0)
            + 0.10 * min(vol_normalized_move / 2.0, 1.0)
        )
        penalty = 0.15 * min(reversal_rate / 0.80, 1.0)
        if spread_expansion > 0.50:
            penalty += 0.10
        evidence = max(0.0, min(100.0, 100.0 * (aligned - penalty)))

    quality = min(
        1.0,
        0.35
        + 0.25 * min(len(sample) / 100.0, 1.0)
        + 0.20 * min(path / max(median_spread * 5.0, 0.01), 1.0)
        + 0.20 * (1.0 - min(reversal_rate, 1.0)),
    )

    return {
        "seconds": seconds,
        "direction": direction,
        "evidence": round(evidence, 2),
        "data_quality": round(quality, 4),
        "ticks": len(sample),
        "tick_imbalance": round(tick_imbalance, 5),
        "quote_pressure": round(quote_pressure, 5),
        "microprice_pressure": round(microprice_pressure, 5),
        "microprice_available": microprice_available,
        "net_move_usd": round(net_move, 6),
        "path_usd": round(path, 6),
        "efficiency": round(efficiency, 5),
        "realized_move": round(realized, 6),
        "vol_normalized_move": round(vol_normalized_move, 5),
        "move_spread_ratio": round(spread_ratio, 5),
        "median_spread_usd": round(median_spread, 6),
        "spread_expansion": round(spread_expansion, 5),
        "reversal_rate": round(reversal_rate, 5),
        "acceleration": round(acceleration, 5),
    }


def build_gold_advisory_v3(
    mt5_module: Any,
    symbol: str = "XAUUSD",
    *,
    now: datetime | None = None,
    history: Any = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    start = current - timedelta(seconds=920)
    rows = None
    if history is None:
        try:
            rows = mt5_module.copy_ticks_from(
                symbol, to_broker_time(start), 100_000,
                int(getattr(mt5_module, "COPY_TICKS_ALL", -1)),
            )
        except Exception:
            rows = None

    if history is None:
        frame = _tick_frame(rows)
        if not frame.empty:
            frame['timestamp'] -= float(settings.MT5_SERVER_UTC_OFFSET_SECONDS)
        history_status = {}
    else:
        frame, history_status = history.refresh(mt5_module, symbol, current)
    depth = _depth(mt5_module, symbol)

    try:
        tick = mt5_module.symbol_info_tick(symbol)
    except Exception:
        tick = None
    bid = _f(getattr(tick, "bid", 0.0))
    ask = _f(getattr(tick, "ask", 0.0))
    spread = max(0.0, ask - bid)

    latest_timestamp = _f(frame["timestamp"].iloc[-1]) if not frame.empty else 0.0
    tick_age = (
        max(0.0, current.timestamp() - latest_timestamp)
        if latest_timestamp > 0
        else float("inf")
    )
    source_ok = bool(not frame.empty and tick_age <= 3. and latest_timestamp <= current.timestamp()+settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS
                     and bid > 0 and ask >= bid and history_status.get('available', True))

    # Preserve tick spacing; tolerated skew shifts the analysis window only.
    flow_now = max(current.timestamp(), latest_timestamp) if source_ok else current.timestamp()
    windows = {
        seconds: _window(frame, seconds, flow_now)
        for seconds in (1, 5, 15, 60, 300, 900)
    }

    outputs: dict[str, Any] = {}
    for name, config in HORIZONS.items():
        selected = [windows[seconds] for seconds in config["windows"]]
        buy = sum(x["direction"] == "BUY" for x in selected)
        sell = sum(x["direction"] == "SELL" for x in selected)

        bias = (
            "BUY" if buy >= 2 and buy > sell
            else "SELL" if sell >= 2 and sell > buy
            else "WAIT"
        )

        supporters = [x for x in selected if x["direction"] == bias]
        score = (
            float(np.mean([x["evidence"] for x in supporters]))
            if supporters else 0.0
        )

        # DOM never creates direction. It is reported as an independent
        # diagnostic so broker-specific depth cannot silently dominate the model.
        dom_imbalance = _f(depth.get("imbalance"))
        blocks: list[str] = []

        if frame.empty:
            blocks.append("MT5 tick history unavailable")
        if tick_age > 3.0:
            blocks.append(f"latest MT5 tick stale ({tick_age:.1f}s)")
        if latest_timestamp > current.timestamp() + settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS:
            blocks.append("MT5 tick timestamp is in the future; clock alignment unavailable")
        if bid <= 0 or ask < bid:
            blocks.append("MT5 current quote unavailable or invalid")
        if spread > 0.50:
            blocks.append(f"spread ${spread:.2f} exceeds research ceiling")
        if bias == "WAIT":
            blocks.append("tick windows have no 2-of-3 directional majority")
        if score < 60.0:
            blocks.append("microstructure evidence below 60/100")

        data_quality = (
            float(np.mean([x["data_quality"] for x in selected]))
            if selected else 0.0
        )
        if data_quality < 0.65:
            blocks.append("microstructure data quality is low")

        action = bias if bias in {"BUY", "SELL"} and not blocks else "WAIT"

        outputs[name] = {
            'source_usable': source_ok and data_quality >= .65,
            "action": action,
            "bias": bias,
            "directional_score": round(score, 2),
            "calibrated_probability": None,
            "probability_status": "UNCALIBRATED",
            "valid_for_minutes": int(config["minutes"]),
            "review_at": (
                current + timedelta(seconds=max(15, int(config["minutes"] * 20)))
            ).isoformat(),
            "valid_until": (
                current + timedelta(minutes=int(config["minutes"]))
            ).isoformat(),
            "votes": {
                "BUY": buy,
                "SELL": sell,
                "NEUTRAL": len(selected) - buy - sell,
            },
            "supporting_timeframes": [
                f"{seconds}s ticks" for seconds in config["windows"]
            ],
            "reasons": [
                f"{buy}/3 BUY, {sell}/3 SELL tick-window votes",
                f"microstructure data quality {data_quality:.2f}",
            ],
            "blocks": blocks,
            "levels": {},
            "window_metrics": {
                str(item["seconds"]): item for item in selected
            },
            "dom_diagnostic": {
                "available": bool(depth.get("available")),
                "imbalance": round(dom_imbalance, 5),
            },
        }

    actionable = [
        item["action"]
        for item in outputs.values()
        if item["action"] in {"BUY", "SELL"}
    ]
    overall = (
        "BUY" if actionable.count("BUY") >= 2 and actionable.count("BUY") > actionable.count("SELL")
        else "SELL" if actionable.count("SELL") >= 2 and actionable.count("SELL") > actionable.count("BUY")
        else "WAIT"
    )

    return {
        'available': source_ok,
        'error': '' if source_ok else (history_status.get('error') or 'MT5 tick history empty, stale, future-dated or current quote invalid'),
        'history_health': history_status,
        "advisor_name": "GOLD MARKET ADVISOR V3 - MT5 MICROSTRUCTURE",
        "version": "3.1-research",
        "generated_at": current.isoformat(),
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0,
        "spread": round(spread, 6),
        "overall": overall,
        "horizons": outputs,
        "tick_count": len(frame),
        "latest_tick_age_seconds": round(tick_age, 3) if np.isfinite(tick_age) else None,
        "market_depth": depth,
        "execution_enabled": False,
        "orders_sent": False,
        "data_source": "MT5 raw bid/ask ticks + optional broker DOM",
        "disclaimer": (
            "Tick-flow fields are broker-feed quote proxies, not centralized "
            "exchange aggressor flow. No calibrated probability is implied."
        ),
    }
