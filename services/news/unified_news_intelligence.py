from __future__ import annotations

"""Session-aware economic context for the single V3.4 scalping engine.

The trading loop consumes local normalized events and a provider-health cache.
No provider can authorize a trade and no network request occurs inside a cycle.
"""

import json
import math
import os
import re
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
# Sign means the expected short-run gold response to a positive surprise.
# `scale` is a conservative meaningful surprise in the indicator's usual unit.
_GOLD_EVENT_RULES = (
    (("ADP EMPLOYMENT", "ADP NONFARM"), -0.55, 50.0, "ADP_EMPLOYMENT"),
    (("NONFARM", "NFP", "PAYROLL"), -1.0, 50.0, "PAYROLLS"),
    (("CORE CPI", "CPI", "CORE PCE", "PCE", "INFLATION"), -1.0, 0.10, "INFLATION"),
    (("CORE PPI", "PPI", "PRODUCER PRICE"), -0.65, 0.20, "PRODUCER_INFLATION"),
    (("AVERAGE HOURLY EARNINGS", "WAGE GROWTH"), -0.75, 0.10, "WAGES"),
    (("UNEMPLOYMENT RATE",), 1.0, 0.10, "UNEMPLOYMENT"),
    (("JOBLESS CLAIM",), 0.7, 25.0, "JOBLESS_CLAIMS"),
    (("JOLTS", "JOB OPENINGS"), -0.55, 250.0, "JOB_OPENINGS"),
    (("RETAIL SALES",), -0.65, 0.30, "RETAIL_SALES"),
    (("ISM MANUFACTURING", "MANUFACTURING PMI", "ISM SERVICES", "SERVICES PMI"),
     -0.45, 1.0, "BUSINESS_ACTIVITY"),
    (("DURABLE GOODS",), -0.40, 1.0, "DURABLE_GOODS"),
    (("INDUSTRIAL PRODUCTION",), -0.40, 0.30, "INDUSTRIAL_PRODUCTION"),
    (("CONSUMER CONFIDENCE",), -0.30, 3.0, "CONSUMER_CONFIDENCE"),
    (("GDP",), -0.55, 0.30, "GDP"),
    (("FED FUNDS RATE", "INTEREST RATE DECISION"), -0.8, 0.25, "POLICY_RATE"),
)


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    text = str(value).strip().replace(",", "")
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*([KMB%]?)", text, re.I)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {"": 1.0, "%": 1.0, "K": 1.0, "M": 1000.0, "B": 1_000_000.0}[match.group(2).upper()]
    result = number * multiplier
    return result if math.isfinite(result) else None


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
    comparison_basis = str(event.get("comparison_basis", "CONSENSUS")).upper()
    if forecast is None and comparison_basis == "PREVIOUS_RELEASE":
        forecast = _safe_float(event.get("previous"))
    if actual is None or forecast is None:
        return 0.0, "No verified actual-versus-forecast surprise.", None
    title = str(event.get("title", "")).upper()
    sensitivity, scale, matched = 0.0, 0.0, ""
    for keywords, rule_sensitivity, rule_scale, rule_name in _GOLD_EVENT_RULES:
        if any(keyword in title for keyword in keywords):
            sensitivity, scale, matched = rule_sensitivity, rule_scale, rule_name
            break
    if not matched:
        return 0.0, "Event has no configured gold-surprise mapping.", None
    surprise = max(-2.0, min(2.0, (actual - forecast) / max(scale, 1e-9)))
    bias = max(-1.0, min(1.0, sensitivity * surprise))
    if comparison_basis == "PREVIOUS_RELEASE":
        return (
            bias,
            f"{matched} change versus the prior release produced provisional gold bias "
            f"{bias:+.3f}; this is not a consensus surprise.",
            surprise,
        )
    return bias, f"{matched} consensus surprise produced gold bias {bias:+.3f}.", surprise


def build_unified_news_context(
    session: str,
    news_risk: dict[str, Any] | None,
    current_time: datetime | None = None,
    *,
    extra_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = _parse_time(current_time or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    news_risk = news_risk or {}
    weights = _SESSION_CURRENCY_WEIGHTS.get(session, {"USD": 1.0})
    combined_events = list(load_events()) + list(extra_events or [])
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in combined_events:
        identity = str(
            event.get("external_id")
            or f"{event.get('title')}:{event.get('event_time')}:{event.get('source')}"
        )
        if identity in seen:
            continue
        seen.add(identity)
        events.append(event)

    relevant: list[dict[str, Any]] = []
    directional_sum = 0.0
    directional_weight = 0.0
    gross_directional_pressure = 0.0
    positive_biases = 0
    negative_biases = 0
    directional_event_count = 0
    directional_quality_sum = 0.0
    consensus_sum = consensus_weight = consensus_quality_sum = 0.0
    consensus_count = 0
    official_change_sum = official_change_weight = official_change_quality_sum = 0.0
    official_change_count = 0
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
        calendar_confidence = str(event.get("calendar_confidence", "UNVERIFIED")).upper()
        verified_release = calendar_confidence in {"VERIFIED", "PROVIDER_VERIFIED"}
        comparison_basis = str(event.get("comparison_basis", "CONSENSUS")).upper()
        if comparison_basis == "PREVIOUS_RELEASE":
            release_quality = min(
                0.35,
                max(0.0, _safe_float(event.get("directional_quality")) or 0.0),
            ) if verified_release else 0.0
        else:
            release_quality = 1.0 if calendar_confidence == "VERIFIED" else 0.75 if verified_release else 0.0
        released = event_time <= now
        bias, reason, surprise = _event_gold_bias(event) if verified_release and released else (
            0.0,
            "Scheduled event is not yet released or is not verified; calendar protection only.",
            None,
        )
        impact = str(event.get("impact", "LOW")).upper()
        impact_weight = {"HIGH": 1.0, "MEDIUM": 0.55, "LOW": 0.2}.get(impact, 0.2)
        recency_weight = max(0.0, 1.0 - distance / (3 * 3600)) if released else 0.0
        combined = currency_weight * impact_weight * recency_weight
        if bias:
            directional_sum += bias * combined
            directional_weight += combined
            gross_directional_pressure += abs(bias) * combined
            directional_quality_sum += combined * release_quality
            directional_event_count += 1
            positive_biases += int(bias > 0)
            negative_biases += int(bias < 0)
            if comparison_basis == "PREVIOUS_RELEASE":
                official_change_sum += bias * combined
                official_change_weight += combined
                official_change_quality_sum += combined * release_quality
                official_change_count += 1
            else:
                consensus_sum += bias * combined
                consensus_weight += combined
                consensus_quality_sum += combined * release_quality
                consensus_count += 1
        source = str(event.get("source", "LOCAL_CALENDAR")).upper()
        sources.add(source)
        relevant.append({
            "title": event.get("title", ""), "currency": currency, "impact": impact,
            "source": source, "event_time": event.get("event_time", ""),
            "actual": event.get("actual"), "forecast": event.get("forecast"),
            "previous": event.get("previous"), "surprise": surprise,
            "calendar_confidence": calendar_confidence,
            "comparison_basis": comparison_basis,
            "directional_quality": release_quality,
            "reaction_eligible": bool(event.get("reaction_eligible", False)),
            "source_url": event.get("source_url", ""),
            "gold_bias": round(bias, 4), "reason": reason,
        })

    provider_conflict = positive_biases > 0 and negative_biases > 0
    directional_coherence = (
        abs(directional_sum) / gross_directional_pressure if gross_directional_pressure else 0.0
    )
    raw_bias_value = directional_sum / directional_weight if directional_weight else 0.0
    bias_value = raw_bias_value * (0.5 + 0.5 * directional_coherence)
    if bias_value > 0.15:
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

    consensus_bias_value = consensus_sum / consensus_weight if consensus_weight else 0.0
    consensus_quality = consensus_quality_sum / consensus_weight if consensus_weight else 0.0
    official_change_bias_value = (
        official_change_sum / official_change_weight if official_change_weight else 0.0
    )
    official_change_quality = (
        official_change_quality_sum / official_change_weight if official_change_weight else 0.0
    )

    if consensus_count and official_change_count:
        data_mode = "VERIFIED_SURPRISE_PLUS_OFFICIAL_CHANGE"
    elif consensus_count:
        data_mode = "VERIFIED_SURPRISE_CONFLICT" if provider_conflict else "VERIFIED_SURPRISE"
    elif official_change_count:
        data_mode = "OFFICIAL_CHANGE_NOT_CONSENSUS"
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
        "directional_data_quality": round(
            (directional_quality_sum / directional_weight) * (0.5 + 0.5 * directional_coherence)
            if directional_weight else 0.0, 4
        ),
        "directional_bias": directional_bias,
        "directional_bias_value": round(bias_value, 4),
        "provider_conflict": provider_conflict,
        "directional_coherence": round(directional_coherence, 4),
        "consensus_event_count": consensus_count,
        "consensus_bias_value": round(consensus_bias_value, 4),
        "consensus_data_quality": round(consensus_quality, 4),
        "official_change_event_count": official_change_count,
        "official_change_bias_value": round(official_change_bias_value, 4),
        "official_change_data_quality": round(official_change_quality, 4),
        "provider_quality": round(provider_quality, 4),
        "provider_healthy_count": healthy_count,
        "provider_configured_count": configured_count,
        "provider_cache_updated_at": cache_updated.isoformat() if cache_updated else "",
        "provider_cache_age_hours": round(cache_age_hours, 2) if cache_age_hours is not None else None,
        "provider_cache_stale": cache_stale,
        "sources": sorted(sources),
        "data_mode": data_mode,
    }
