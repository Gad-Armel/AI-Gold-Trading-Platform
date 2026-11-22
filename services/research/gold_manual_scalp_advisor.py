"""Conservative, read-only conjunction of candle and MT5 tick-flow scalp signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any


def _utc_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _finite_positive(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a positive finite number.") from error
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{field} must be a positive finite number.")
    return result


def build_manual_scalp_advisory(
    candle_report: dict[str, Any],
    tick_report: dict[str, Any],
    *,
    now: datetime | None = None,
    max_report_age_seconds: float = 5.0,
    max_tick_age_seconds: float = 3.0,
    max_spread_price: float = 0.30,
    max_quote_disagreement_price: float = 0.05,
    minimum_score: float = 60.0,
    minimum_reward_risk: float = 0.65,
    validity_seconds: int = 15,
) -> dict[str, Any]:
    """Emit a manual-only scalp signal; any failed gate returns WAIT."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a timezone.")
    current = current.astimezone(timezone.utc)
    limits = (max_report_age_seconds, max_tick_age_seconds, max_spread_price,
              max_quote_disagreement_price, minimum_score, minimum_reward_risk)
    if any(not math.isfinite(float(value)) or float(value) <= 0 for value in limits):
        raise ValueError("Advisory limits must be positive finite values.")
    if validity_seconds <= 0:
        raise ValueError("validity_seconds must be positive.")

    symbol = str(candle_report.get("symbol", ""))
    if symbol != "XAUUSD" or str(tick_report.get("symbol", "")) != symbol:
        raise ValueError("Both input reports must describe the exact XAUUSD symbol.")
    candle_time = _utc_datetime(candle_report.get("generated_at"), "candle generated_at")
    tick_time = _utc_datetime(tick_report.get("generated_at"), "tick generated_at")
    candle_age = (current - candle_time).total_seconds()
    tick_age_report = (current - tick_time).total_seconds()
    blocks: list[str] = []
    if not 0 <= candle_age <= max_report_age_seconds:
        blocks.append("Candle analysis is stale or future-dated.")
    if not 0 <= tick_age_report <= max_report_age_seconds:
        blocks.append("Tick analysis is stale or future-dated.")
    if tick_report.get("available") is not True:
        blocks.append("Tick feed/history is unavailable.")

    candle_horizon = (candle_report.get("horizons") or {}).get("SCALP") or {}
    tick_horizon = (tick_report.get("horizons") or {}).get("SCALP") or {}
    candle_action = str(candle_horizon.get("action", "WAIT"))
    tick_action = str(tick_horizon.get("action", "WAIT"))
    if candle_action not in {"BUY", "SELL"}:
        blocks.append("Closed-candle scalp model does not confirm a direction.")
    if tick_action not in {"BUY", "SELL"}:
        blocks.append("Short-window tick-flow model does not confirm a direction.")
    if candle_action in {"BUY", "SELL"} and tick_action in {"BUY", "SELL"} and candle_action != tick_action:
        blocks.append("Candle and tick-flow directions disagree.")

    candle_score = float(candle_horizon.get("directional_score", 0.0))
    tick_score = float(tick_horizon.get("directional_score", 0.0))
    if not math.isfinite(candle_score) or not math.isfinite(tick_score):
        raise ValueError("Input directional scores must be finite.")
    if candle_score < minimum_score or tick_score < minimum_score:
        blocks.append(f"Both directional scores must be at least {minimum_score:.0f}/100.")
    if tick_horizon.get("source_usable") is not True:
        blocks.append("Tick-flow data quality is below its source usability gate.")

    bid = _finite_positive(tick_report.get("bid"), "tick bid")
    ask = _finite_positive(tick_report.get("ask"), "tick ask")
    candle_bid = _finite_positive(candle_report.get("bid"), "candle bid")
    candle_ask = _finite_positive(candle_report.get("ask"), "candle ask")
    if ask < bid or candle_ask < candle_bid:
        raise ValueError("Input bid/ask quotes are crossed.")
    spread = ask - bid
    if spread > max_spread_price:
        blocks.append(f"Spread {spread:.4f} exceeds the ${max_spread_price:.4f} advisory ceiling.")
    quote_difference = abs((bid + ask - candle_bid - candle_ask) / 2.0)
    if quote_difference > max_quote_disagreement_price:
        blocks.append("Candle and tick reports use materially different quote snapshots.")

    latest_tick_age = tick_report.get("latest_tick_age_seconds")
    try:
        latest_tick_age = float(latest_tick_age)
    except (TypeError, ValueError):
        latest_tick_age = math.inf
    if not math.isfinite(latest_tick_age) or latest_tick_age < 0 or latest_tick_age > max_tick_age_seconds:
        blocks.append("Latest observed tick is stale or its age is unavailable.")

    levels = candle_horizon.get("levels") or {}
    direction = candle_action if candle_action == tick_action else "WAIT"
    risk = reward = reward_risk = None
    if direction in {"BUY", "SELL"}:
        required = ("entry_reference", "entry_zone", "sl", "tp1", "tp2", "tp3")
        if any(name not in levels for name in required):
            blocks.append("Candle model did not provide complete scalp scenario levels.")
        else:
            entry = _finite_positive(levels["entry_reference"], "entry reference")
            stop = _finite_positive(levels["sl"], "stop scenario")
            target = _finite_positive(levels["tp1"], "first target scenario")
            _finite_positive(levels["tp2"], "second target scenario")
            _finite_positive(levels["tp3"], "third target scenario")
            zone = levels["entry_zone"]
            if not isinstance(zone, (list, tuple)) or len(zone) != 2:
                raise ValueError("entry_zone must contain exactly two positive prices.")
            zone_low = _finite_positive(zone[0], "entry zone low")
            zone_high = _finite_positive(zone[1], "entry zone high")
            if zone_low > zone_high:
                raise ValueError("entry_zone low must not exceed its high.")
            risk = entry - stop if direction == "BUY" else stop - entry
            reward = target - entry if direction == "BUY" else entry - target
            if risk <= 0 or reward <= 0:
                blocks.append("Scenario stop/target is on the wrong side of the entry reference.")
            else:
                reward_risk = reward / risk
                if reward <= spread:
                    blocks.append("First target distance does not exceed the current spread.")
                if reward_risk < minimum_reward_risk:
                    blocks.append(
                        f"Scenario reward/risk {reward_risk:.2f} is below {minimum_reward_risk:.2f}."
                    )

    action = direction if direction in {"BUY", "SELL"} and not blocks else "WAIT"
    valid_until = min(
        candle_time + timedelta(seconds=validity_seconds),
        tick_time + timedelta(seconds=validity_seconds),
        current + timedelta(seconds=validity_seconds),
    )
    return {
        "advisor_name": "XAUUSD MANUAL SCALP ADVISOR (CANDLE + TICK CONFLUENCE)",
        "version": "0.1-research",
        "generated_at": current.isoformat(),
        "valid_until": valid_until.isoformat(),
        "symbol": symbol,
        "action": action,
        "bias": direction,
        "directional_evidence_score": round(min(candle_score, tick_score), 2),
        "score_note": "Minimum of two uncalibrated directional evidence scores; not a win probability.",
        "reports": {
            "candle_generated_at": candle_time.isoformat(),
            "tick_generated_at": tick_time.isoformat(),
            "candle_age_seconds": round(candle_age, 3),
            "tick_report_age_seconds": round(tick_age_report, 3),
            "latest_tick_age_seconds": latest_tick_age if math.isfinite(latest_tick_age) else None,
            "candle_action": candle_action,
            "candle_score": round(candle_score, 2),
            "tick_action": tick_action,
            "tick_score": round(tick_score, 2),
            "tick_data_quality": tick_horizon.get("window_metrics", {}).get("1", {}).get("data_quality"),
        },
        "quote": {
            "bid": bid,
            "ask": ask,
            "spread": round(spread, 6),
            "snapshot_mid_difference": round(quote_difference, 6),
        },
        "scenario_levels": levels if action in {"BUY", "SELL"} else {},
        "scenario_risk_price_units": round(risk, 6) if risk is not None else None,
        "scenario_reward_to_risk": round(reward_risk, 4) if reward_risk is not None else None,
        "reasons": [
            "Both closed-candle and short-window MT5 quote-flow scalp models must agree.",
            "Tick-flow is a broker quote-change proxy, not centralized trade aggressor flow.",
            *[str(reason) for reason in candle_horizon.get("reasons", [])],
            *[str(reason) for reason in tick_horizon.get("reasons", [])],
        ],
        "blocks": blocks,
        "execution_enabled": False,
        "orders_sent": False,
        "disclaimer": (
            "Manual decision support only, not a promise of performance or calibrated probability. "
            "Check the live quote and your risk plan; skip expired or WAIT signals."
        ),
    }
