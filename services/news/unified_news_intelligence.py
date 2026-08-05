from __future__ import annotations

"""Session-aware economic context for the single V3.4 scalping engine.

The trading loop consumes local normalized events and a provider-health cache.
No provider can authorize a trade and no network request occurs inside a cycle.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

from config import scalping_settings
from services.risk.economic_event_manager import load_events

_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_SESSION_CURRENCY_WEIGHTS = {
    "Asian": {"USD": 1.0, "JPY": 0.8, "CNY": 0.8, "AUD": 0.6, "NZD": 0.4},
    "London": {"USD": 1.0, "EUR": 0.9, "GBP": 0.9, "CHF": 0.5},
    "New York": {"USD": 1.0, "CAD": 0.5, "EUR": 0.4, "GBP": 0.4},
}
_GOLD_EVENT_DIRECTION = {
    "CPI": -1.0, "PCE": -1.0, "INFLATION": -1.0,
    "NFP": -1.0, "NONFARM": -1.0, "PAYROLL": -1.0,
    "RETAIL SALES": -0.7, "GDP": -0.6,
    "UNEMPLOYMENT": 1.0, "JOBLESS": 0.8,
    "RATE": -1.0, "INTEREST": -1.0,
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        result = None
        for parser in (datetime.fromisoformat, lambda x: datetime.strptime(x, _DATE_FORMAT)):
            try:
                result = parser(text)
                break
            except Exception:
                continue
        if result is None:
            return None
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _load_provider_cache() -> dict[str, Any]:
    path = str(getattr(scalping_settings, "SCALPING_UNIFIED_PROVIDER_CACHE_FILE", "data/unified_provider_cache.json"))
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _event_gold_bias(event: dict[str, Any]) -> tuple[float, str, float | None]:
    actual = _safe_float(event.get("actual"))
    forecast = _safe_float(event.get("forecast"))
    if actual is None or forecast is None:
        return 0.0, "No verified actual-versus-forecast surprise.", None
    title = str(event.get("title", "")).upper()
    sensitivity = 0.0
    matched = ""
    for keyword, value in _GOLD_EVENT_DIRECTION.items():
        if keyword in title:
            sensitivity, matched = value, keyword
            break
    if not matched:
        return 0.0, "Event has no configured gold-surprise mapping.", None
    scale = max(abs(forecast), 1.0)
    surprise = max(-2.0, min(2.0, (actual - forecast) / scale))
    bias = max(-1.0, min(1.0, sensitivity * surprise))
    return bias, f"{matched} surprise produced gold bias {bias:+.3f}.", surprise


def build_unified_news_context(session: str, news_risk: dict[str, Any] | None, current_time: datetime | None = None) -> dict[str, Any]:
    now = _parse_time(current_time or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    news_risk = news_risk or {}
    weights = _SESSION_CURRENCY_WEIGHTS.get(session, {"USD": 1.0})
    events = load_events()

    relevant: list[dict[str, Any]] = []
    directional_sum = 0.0
    directional_weight = 0.0
    positive_biases = 0
    negative_biases = 0
    directional_event_count = 0
    sources: set[str] = set()

    for event in events:
        event_time = _parse_time(event.get("event_time"))
        if event_time is None:
            continue
        distance = abs((now - event_time).total_seconds())
        if distance > 6 * 3600:
            continue
        currency = str(event.get("currency", "USD")).upper()
        currency_weight = float(weights.get(currency, 0.15 if currency == "USD" else 0.0))
        if currency_weight <= 0:
            continue
        bias, reason, surprise = _event_gold_bias(event)
        impact = str(event.get("impact", "LOW")).upper()
        impact_weight = {"HIGH": 1.0, "MEDIUM": 0.55, "LOW": 0.2}.get(impact, 0.2)
        recency_weight = max(0.1, 1.0 - distance / (6 * 3600))
        combined = currency_weight * impact_weight * recency_weight
        if bias:
            directional_sum += bias * combined
            directional_weight += combined
            directional_event_count += 1
            positive_biases += int(bias > 0)
            negative_biases += int(bias < 0)
        source = str(event.get("source", "LOCAL_CALENDAR")).upper()
        sources.add(source)
        relevant.append({
            "title": event.get("title", ""), "currency": currency, "impact": impact,
            "source": source, "event_time": event.get("event_time", ""),
            "actual": event.get("actual"), "forecast": event.get("forecast"),
            "previous": event.get("previous"), "surprise": surprise,
            "gold_bias": round(bias, 4), "reason": reason,
        })

    provider_conflict = positive_biases > 0 and negative_biases > 0
    bias_value = directional_sum / directional_weight if directional_weight else 0.0
    if provider_conflict:
        directional_bias = "NEUTRAL"
        bias_value = 0.0
    elif bias_value > 0.15:
        directional_bias = "BUY"
    elif bias_value < -0.15:
        directional_bias = "SELL"
    else:
        directional_bias = "NEUTRAL"

    provider_cache = _load_provider_cache()
    provider_records = provider_cache.get("providers", {}) if isinstance(provider_cache, dict) else {}
    healthy_count = sum(1 for record in provider_records.values() if isinstance(record, dict) and record.get("healthy") is True)
    configured_count = len(provider_records)
    provider_quality = healthy_count / configured_count if configured_count else 0.0
    cache_updated = _parse_time(provider_cache.get("updated_at")) if provider_cache else None
    cache_age_hours = (now - cache_updated).total_seconds() / 3600.0 if cache_updated else None
    cache_stale = cache_age_hours is None or cache_age_hours > 24.0

    if directional_weight and not provider_conflict:
        data_mode = "VERIFIED_SURPRISE"
    elif provider_conflict:
        data_mode = "PROVIDER_CONFLICT_NEUTRALIZED"
    else:
        data_mode = "CALENDAR_PROTECTION_ONLY"

    return {
        "allowed": bool(news_risk.get("allowed", True)),
        "hard_block": not bool(news_risk.get("allowed", True)),
        "block_reasons": list(news_risk.get("block_reasons", [])),
        "session": session,
        "currency_weights": weights,
        "relevant_events": relevant,
        "relevant_event_count": len(relevant),
        "directional_event_count": directional_event_count,
        "directional_bias": directional_bias,
        "directional_bias_value": round(bias_value, 4),
        "provider_conflict": provider_conflict,
        "provider_quality": round(provider_quality, 4),
        "provider_healthy_count": healthy_count,
        "provider_configured_count": configured_count,
        "provider_cache_updated_at": cache_updated.isoformat() if cache_updated else "",
        "provider_cache_age_hours": round(cache_age_hours, 2) if cache_age_hours is not None else None,
        "provider_cache_stale": cache_stale,
        "sources": sorted(sources),
        "data_mode": data_mode,
    }
