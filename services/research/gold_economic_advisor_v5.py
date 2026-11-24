from __future__ import annotations

"""Read-only, horizon-aware economic regime advisor for XAUUSD.

Scores are transparent directional context in [-1, +1], never probabilities.
Slow releases cannot create a trade; the execution policy may only use a fresh,
high-quality contradiction as a veto or aligned context as confirmation.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _scaled(value: float, meaningful_move: float) -> float:
    """Map a continuous move to [-1, 1] without a brittle sign-only jump."""
    return math.tanh(float(value) / max(float(meaningful_move), 1e-9))


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_institutional(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _freshness_quality(observation: dict[str, Any], max_age_days: float, now: datetime) -> float:
    observed = _time(observation.get("observation_time") or observation.get("observed_at"))
    if observed is not None:
        age = (now - observed).total_seconds() / 86400.0
        if age < -1.0:
            return 0.0
        age = max(0.0, age)
    else:
        age = _number(observation.get("age_days"), max_age_days + 1.0)
    return max(0.0, min(1.0, 1.0 - max(0.0, age) / max_age_days)) if max_age_days > 0 else 0.0


def _has_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _combine_parts(parts: list[dict[str, Any]]) -> tuple[float, float, float]:
    """Return score, quality and directional coherence for one source family."""
    capacity = sum(float(item["weight"]) for item in parts)
    usable_weight = sum(float(item["weight"]) * float(item["quality"]) for item in parts)
    numerator = sum(
        float(item["weight"]) * float(item["quality"]) * float(item["score"])
        for item in parts
    )
    absolute_pressure = sum(
        float(item["weight"]) * float(item["quality"]) * abs(float(item["score"]))
        for item in parts
    )
    score = numerator / usable_weight if usable_weight else 0.0
    coherence = abs(numerator) / absolute_pressure if absolute_pressure > 1e-9 else 1.0
    availability = usable_weight / capacity if capacity else 0.0
    quality = availability * (0.5 + 0.5 * coherence)
    return _clamp(score), max(0.0, min(1.0, quality)), max(0.0, min(1.0, coherence))


def _candle_time(value: Any) -> datetime | None:
    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    # MT5 candle timestamps in this project use the terminal tick clock and
    # are intentionally compared as clock-naive values after event conversion.
    return parsed.replace(tzinfo=None)


def _official_release_reaction(
    news: dict[str, Any],
    snapshot: Any,
    *,
    now: datetime,
    maximum_age_minutes: float,
    component_name: str,
) -> dict[str, Any]:
    """Measure post-release XAUUSD movement; never infer it from a headline.

    The first completed pre-event M1 close is the baseline.  The move is scaled
    by the median recent M1 range and square-root time.  This is confirmation of
    the market's observed reaction, not proof that the release caused the move.
    """
    empty = {
        "name": component_name, "score": 0.0, "quality": 0.0,
        "cadence": "EVENT_MARKET_REACTION",
        "summary": "No fresh official release with measurable XAUUSD reaction.",
    }
    if snapshot is None:
        return empty
    eligible: list[tuple[datetime, dict[str, Any]]] = []
    for event in list(news.get("relevant_events", []) or []):
        event_time = _time(event.get("event_time"))
        if (
            event_time is None
            or not bool(event.get("reaction_eligible", False))
            or str(event.get("calendar_confidence", "")).upper() != "VERIFIED"
        ):
            continue
        age_minutes = (now - event_time).total_seconds() / 60.0
        if 0.5 <= age_minutes <= maximum_age_minutes:
            eligible.append((event_time, event))
    if not eligible:
        return empty
    event_time, event = max(eligible, key=lambda item: item[0])

    candles = getattr(snapshot, "candles", {}) or {}
    m1 = candles.get("M1") if isinstance(candles, dict) else None
    if m1 is None:
        return empty
    if hasattr(m1, "to_dict"):
        try:
            records = list(m1.to_dict("records"))
        except Exception:
            records = []
    elif isinstance(m1, list):
        records = [dict(item) for item in m1 if isinstance(item, dict)]
    else:
        records = []
    if len(records) < 10:
        return empty

    clock_offset = _number(getattr(snapshot, "market_clock_offset_seconds", 0.0))
    event_clock = event_time.timestamp() + clock_offset
    baseline = None
    prior_ranges: list[float] = []
    for record in records:
        stamp = _candle_time(record.get("time"))
        if stamp is None:
            continue
        stamp_epoch = stamp.replace(tzinfo=timezone.utc).timestamp()
        if stamp_epoch + 60 <= event_clock and _has_number(record.get("close")):
            baseline = _number(record.get("close"))
        if stamp_epoch + 60 <= event_clock and _has_number(record.get("high")) and _has_number(record.get("low")):
            bar_range = abs(_number(record.get("high")) - _number(record.get("low")))
            if bar_range > 0:
                prior_ranges.append(bar_range)
    current = _number(getattr(snapshot, "mid", 0.0))
    if baseline is None or current <= 0 or not prior_ranges:
        return empty

    age_minutes = max(0.5, (now - event_time).total_seconds() / 60.0)
    typical_range = median(prior_ranges[-60:])
    spread = max(0.0, _number(getattr(snapshot, "spread", 0.0)))
    expected_range = max(typical_range * math.sqrt(age_minutes), spread * 2.0, 1e-6)
    move = current - baseline
    score = _scaled(move, expected_range * 1.5)
    magnitude_quality = min(1.0, abs(move) / expected_range)
    freshness = max(0.0, 1.0 - age_minutes / maximum_age_minutes)
    quality = freshness * (0.35 + 0.65 * magnitude_quality)
    return {
        "name": component_name,
        "score": _clamp(score),
        "quality": max(0.0, min(1.0, quality)),
        "cadence": "EVENT_MARKET_REACTION",
        "event_time": event_time.isoformat(),
        "observed_at": now.isoformat(),
        "source": "MT5 XAUUSD reaction after verified official release",
        "source_url": event.get("source_url", ""),
        "move_usd": round(move, 4),
        "expected_range_usd": round(expected_range, 4),
        "summary": (
            f"XAUUSD moved {move:+.2f} USD after {event.get('title', 'official release')}; "
            f"recent-range scale {expected_range:.2f} USD."
        ),
    }


def _institutional_observation(
    payload: dict[str, Any], name: str, legacy_field: str,
) -> dict[str, Any]:
    observations = payload.get("observations")
    if isinstance(observations, dict) and isinstance(observations.get(name), dict):
        return dict(observations[name])
    if legacy_field not in payload:
        return {}
    return {
        "available": True,
        "observed_at": payload.get("observed_at"),
        "published_at": payload.get("recorded_at") or payload.get("observed_at"),
        "source": payload.get("source", ""),
        "source_url": payload.get("source_url", ""),
        "source_quality": 0.75,
        "period": "UNSPECIFIED",
        legacy_field: payload.get(legacy_field),
    }


def _institutional_quality(
    observation: dict[str, Any], *, release_days: float, observation_days: float,
    now: datetime,
) -> float:
    """Quality reflects provenance plus both release and observation age.

    Publication age matters because that is when V6 could first have known the
    value. Observation age matters separately because WGC/IMF series arrive
    with a material reporting lag.
    """
    if not str(observation.get("source", "")).strip():
        return 0.0
    observed = _time(observation.get("observed_at") or observation.get("observation_time"))
    published = _time(
        observation.get("published_at")
        or observation.get("released_at")
        or observation.get("retrieved_at")
        or observation.get("observed_at")
    )
    if observed is None or published is None or observed > now or published > now:
        return 0.0
    release_age = max(0.0, (now - published).total_seconds() / 86400.0)
    observation_age = max(0.0, (now - observed).total_seconds() / 86400.0)
    release_quality = max(0.0, 1.0 - release_age / max(release_days, 1e-9))
    observation_quality = max(0.0, 1.0 - observation_age / max(observation_days, 1e-9))
    source_quality = max(0.0, min(1.0, _number(observation.get("source_quality"), 0.75)))
    # An older observation that has only just been published still carries
    # regime information, but never receives full-quality treatment.
    return _clamp(source_quality * release_quality * (0.65 + 0.35 * observation_quality))


def _tonnage_scale(period: Any, *, monthly: float, weekly: float, quarterly: float) -> float:
    value = str(period or "").upper()
    if "WEEK" in value:
        return weekly
    if "QUARTER" in value:
        return quarterly
    if "YEAR" in value or "YTD" in value:
        return quarterly * 2.5
    return monthly


def build_gold_economic_advisor_v5(
    news: dict[str, Any] | None,
    macro: dict[str, Any] | None,
    *,
    snapshot: Any | None = None,
    institutional_path: str | Path = "data/context/gold_institutional_context.json",
    now: datetime | None = None,
) -> dict[str, Any]:
    generated = now or datetime.now(timezone.utc)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    news, macro = news or {}, macro or {}
    institutional = _load_institutional(institutional_path)
    observations = macro.get("observations", {}) if isinstance(macro.get("observations"), dict) else {}

    components: list[dict[str, Any]] = []
    consensus_count = int(_number(news.get("consensus_event_count")))
    if consensus_count <= 0 and str(news.get("data_mode", "")).startswith("VERIFIED_SURPRISE"):
        consensus_count = int(_number(news.get("directional_event_count")))
    event_score = _clamp(_number(
        news.get("consensus_bias_value", news.get("directional_bias_value"))
    ))
    event_quality = (
        _clamp(_number(
            news.get("consensus_data_quality", news.get("directional_data_quality")), 0.75,
        ))
        if consensus_count > 0
        else 0.0
    )
    components.append({"name": "verified_release_surprise", "score": event_score, "quality": event_quality, "cadence": "EVENT"})

    official_change_count = int(_number(news.get("official_change_event_count")))
    components.append({
        "name": "official_release_change",
        "score": _clamp(_number(news.get("official_change_bias_value"))),
        "quality": (
            _clamp(_number(news.get("official_change_data_quality")))
            if official_change_count > 0 else 0.0
        ),
        "cadence": "EVENT",
        "summary": (
            "Official released value changed versus the prior release; this is not a market-consensus surprise."
        ),
    })
    components.append(_official_release_reaction(
        news, snapshot, now=generated, maximum_age_minutes=12.0,
        component_name="official_release_reaction_scalp",
    ))
    components.append(_official_release_reaction(
        news, snapshot, now=generated, maximum_age_minutes=60.0,
        component_name="official_release_reaction_intraday",
    ))

    usd = observations.get("usd_broad", {})
    real = observations.get("us10y_real", {})
    nominal = observations.get("us10y", {})
    vix = observations.get("vix", {})
    macro_parts = [
        {"name": "broad_usd_5d", "score": -_scaled(_number(usd.get("pct_change_5")), 0.50),
         "quality": _freshness_quality(usd, 7, generated), "weight": 0.35},
        {"name": "real_yield_5d", "score": -_scaled(_number(real.get("change_5")), 0.15),
         "quality": _freshness_quality(real, 7, generated), "weight": 0.35},
        {"name": "nominal_yield_5d", "score": -_scaled(_number(nominal.get("change_5")), 0.20),
         "quality": _freshness_quality(nominal, 7, generated), "weight": 0.15},
        {"name": "risk_aversion_5d", "score": _scaled(_number(vix.get("pct_change_5")), 10.0),
         "quality": _freshness_quality(vix, 7, generated), "weight": 0.15},
    ]
    macro_weight = sum(item["weight"] * item["quality"] for item in macro_parts)
    macro_numerator = sum(item["weight"] * item["quality"] * item["score"] for item in macro_parts)
    macro_score = macro_numerator / macro_weight if macro_weight else 0.0
    absolute_pressure = sum(
        item["weight"] * item["quality"] * abs(item["score"]) for item in macro_parts
    )
    coherence = abs(macro_numerator) / absolute_pressure if absolute_pressure > 1e-9 else 1.0
    availability_quality = macro_weight / sum(item["weight"] for item in macro_parts)
    macro_quality = availability_quality * (0.5 + 0.5 * coherence)
    components.append({"name": "usd_yields_risk_regime", "score": _clamp(macro_score),
                       "quality": _clamp(macro_quality), "cadence": "DAILY",
                       "coherence": round(coherence, 4), "inputs": macro_parts,
                       "observed_at": max(
                           str(item.get("observation_time", ""))
                           for item in (usd, real, nominal, vix)
                       ),
                       "source": "Federal Reserve and market series via FRED",
                       "source_url": "https://fred.stlouisfed.org/",
                       "summary": (
                           f"USD, real-yield, nominal-yield and VIX pressure is {macro_score:+.3f}; "
                           f"internal agreement {coherence * 100:.0f}%."
                       )})

    uncertainty = observations.get("global_policy_uncertainty", {})
    uncertainty_change = uncertainty.get("pct_change_5")
    uncertainty_quality = (
        # GEPU is monthly and normally arrives with a reporting lag.  A
        # 120-day horizon keeps the latest release usable while still fading
        # it to zero if publication stops for several months.
        _freshness_quality(uncertainty, 120.0, generated)
        if _has_number(uncertainty_change) else 0.0
    )
    uncertainty_score = (
        _scaled(_number(uncertainty_change), 25.0) if _has_number(uncertainty_change) else 0.0
    )
    components.append({
        "name": "global_policy_uncertainty", "score": _clamp(uncertainty_score),
        "quality": uncertainty_quality, "cadence": "MONTHLY",
        "value": _number(uncertainty_change) if _has_number(uncertainty_change) else None,
        "unit": "% change / 5 observations",
        "observed_at": uncertainty.get("observation_time", ""),
        "source": "FRED GEPUCURRENT",
        "source_url": "https://fred.stlouisfed.org/series/GEPUCURRENT",
        "summary": (
            f"Global economic-policy uncertainty changed {_number(uncertainty_change):+.1f}% over five observations."
            if _has_number(uncertainty_change) else "No fresh global economic-policy uncertainty trend."
        ),
    })

    # A daily newspaper-based EPU series provides a faster risk signal than
    # the monthly global index.  Five-day versus twenty-day means reduce the
    # impact of a single sensational headline or weekend spike.
    us_uncertainty = observations.get("us_policy_uncertainty", {})
    us_uncertainty_trend = us_uncertainty.get("mean_5_minus_20")
    us_uncertainty_quality = (
        _freshness_quality(us_uncertainty, 7.0, generated)
        if _has_number(us_uncertainty_trend) else 0.0
    )
    us_uncertainty_score = (
        _scaled(_number(us_uncertainty_trend), 75.0)
        if _has_number(us_uncertainty_trend) else 0.0
    )
    components.append({
        "name": "us_policy_uncertainty", "score": _clamp(us_uncertainty_score),
        "quality": us_uncertainty_quality, "cadence": "DAILY_7_DAY",
        "value": _number(us_uncertainty_trend) if _has_number(us_uncertainty_trend) else None,
        "unit": "index points: 5-day mean minus 20-day mean",
        "observed_at": us_uncertainty.get("observation_time", ""),
        "source": "FRED USEPUINDXD",
        "source_url": "https://fred.stlouisfed.org/series/USEPUINDXD",
        "summary": (
            f"US policy-uncertainty 5-day mean is {_number(us_uncertainty_trend):+.1f} "
            "points versus its 20-day mean."
            if _has_number(us_uncertainty_trend)
            else "No fresh daily US policy-uncertainty trend."
        ),
    })

    # Two official Federal Reserve indexes are treated as one source family,
    # not two independent votes.  Positive/tightening stress is gold-supportive
    # context; easing/below-normal stress is a headwind.  This relationship can
    # reverse during forced liquidation, hence the modest point allocation.
    stl_stress = observations.get("financial_stress_stl", {})
    chicago_conditions = observations.get("financial_conditions_chicago", {})
    stl_value = stl_stress.get("value")
    stl_trend = stl_stress.get("mean_5_minus_20")
    chicago_value = chicago_conditions.get("value")
    chicago_trend = chicago_conditions.get("mean_5_minus_20")
    stress_parts = [
        {
            "name": "st_louis_financial_stress",
            "score": _clamp(
                0.35 * _scaled(_number(stl_value), 1.0)
                + 0.65 * _scaled(_number(stl_trend), 0.25)
            ) if _has_number(stl_value) and _has_number(stl_trend) else 0.0,
            "quality": _freshness_quality(stl_stress, 14.0, generated)
            if _has_number(stl_value) and _has_number(stl_trend) else 0.0,
            "weight": 0.50,
        },
        {
            "name": "chicago_financial_conditions",
            "score": _clamp(
                0.35 * _scaled(_number(chicago_value), 0.75)
                + 0.65 * _scaled(_number(chicago_trend), 0.10)
            ) if _has_number(chicago_value) and _has_number(chicago_trend) else 0.0,
            "quality": _freshness_quality(chicago_conditions, 14.0, generated)
            if _has_number(chicago_value) and _has_number(chicago_trend) else 0.0,
            "weight": 0.50,
        },
    ]
    stress_score, stress_quality, stress_coherence = _combine_parts(stress_parts)
    components.append({
        "name": "systemic_financial_stress", "score": stress_score,
        "quality": stress_quality, "cadence": "WEEKLY",
        "coherence": round(stress_coherence, 4), "inputs": stress_parts,
        "observed_at": max(
            str(stl_stress.get("observation_time", "")),
            str(chicago_conditions.get("observation_time", "")),
        ),
        "source": "Federal Reserve Banks of St. Louis and Chicago via FRED",
        "source_url": "https://fred.stlouisfed.org/series/STLFSI4",
        "summary": (
            f"Systemic financial-stress family pressure is {stress_score:+.3f}; "
            f"internal agreement {stress_coherence * 100:.0f}%."
        ),
    })

    # Market-implied inflation is combined with a real-time recession flag.
    # Inflation alone is deliberately low weight because its effect depends on
    # the dollar and real yields, which are already represented separately.
    breakeven = observations.get("inflation_expectation_10y", {})
    recession = observations.get("recession_indicator", {})
    breakeven_trend = breakeven.get("mean_5_minus_20")
    recession_value = recession.get("value")
    recession_score = (
        max(0.0, _scaled(_number(recession_value) - 0.20, 0.30))
        if _has_number(recession_value) else 0.0
    )
    inflation_growth_parts = [
        {
            "name": "market_inflation_expectation",
            "score": _scaled(_number(breakeven_trend), 0.12)
            if _has_number(breakeven_trend) else 0.0,
            "quality": _freshness_quality(breakeven, 7.0, generated)
            if _has_number(breakeven_trend) else 0.0,
            "weight": 0.75,
        },
        {
            "name": "sahm_recession_risk",
            "score": recession_score,
            "quality": _freshness_quality(recession, 60.0, generated)
            if _has_number(recession_value) else 0.0,
            "weight": 0.25,
        },
    ]
    inflation_growth_score, inflation_growth_quality, inflation_growth_coherence = (
        _combine_parts(inflation_growth_parts)
    )
    components.append({
        "name": "inflation_recession_regime", "score": inflation_growth_score,
        "quality": inflation_growth_quality, "cadence": "DAILY_MONTHLY",
        "coherence": round(inflation_growth_coherence, 4),
        "inputs": inflation_growth_parts,
        "observed_at": max(
            str(breakeven.get("observation_time", "")),
            str(recession.get("observation_time", "")),
        ),
        "source": "FRED T10YIE and SAHMREALTIME",
        "source_url": "https://fred.stlouisfed.org/series/T10YIE",
        "summary": (
            f"Inflation-expectation/recession pressure is {inflation_growth_score:+.3f}; "
            f"internal agreement {inflation_growth_coherence * 100:.0f}%."
        ),
    })

    world_growth = observations.get("world_bank_global_growth", {})
    world_growth_change = world_growth.get("change_from_previous_year")
    world_growth_quality = (
        _freshness_quality(world_growth, 240.0, generated)
        * max(0.0, min(1.0, _number(world_growth.get("source_quality"), 0.98)))
        if _has_number(world_growth_change) else 0.0
    )
    # Slower projected world growth is modestly gold-supportive via defensive
    # demand/rate-cut expectations; acceleration applies the inverse pressure.
    world_growth_score = (
        -_scaled(_number(world_growth_change), 0.75)
        if _has_number(world_growth_change) else 0.0
    )
    components.append({
        "name": "world_bank_growth_outlook", "score": _clamp(world_growth_score),
        "quality": world_growth_quality, "cadence": "SEMI_ANNUAL",
        "value": _number(world_growth.get("value"))
        if _has_number(world_growth.get("value")) else None,
        "unit": "% world real GDP growth",
        "forecast_year": world_growth.get("forecast_year"),
        "change_from_previous_year": (
            _number(world_growth_change) if _has_number(world_growth_change) else None
        ),
        "observed_at": world_growth.get("observation_time", ""),
        "source": world_growth.get("source", "World Bank Global Economic Prospects"),
        "source_url": world_growth.get(
            "source_url", "https://databank.worldbank.org/source/global-economic-prospects"
        ),
        "summary": (
            f"World Bank forecasts {int(world_growth.get('forecast_year'))} world growth at "
            f"{_number(world_growth.get('value')):.1f}%, "
            f"{_number(world_growth_change):+.1f} points versus the prior year."
            if _has_number(world_growth.get("value"))
            and _has_number(world_growth_change)
            and _has_number(world_growth.get("forecast_year"))
            else "No fresh World Bank global-growth outlook."
        ),
    })

    # Every institutional series retains its own date and cadence.  Slow
    # official-sector data are regime context, never a short-horizon trigger.
    central_observation = _institutional_observation(
        institutional, "central_bank", "central_bank_net_tonnes_change",
    )
    central_value = (
        central_observation.get("net_tonnes")
        if "net_tonnes" in central_observation
        else central_observation.get("central_bank_net_tonnes_change")
    )
    central_quality = (
        _institutional_quality(
            central_observation, release_days=45.0, observation_days=120.0, now=generated,
        )
        if _has_number(central_value) else 0.0
    )
    central_scale = _tonnage_scale(
        central_observation.get("period"), monthly=30.0, weekly=12.0, quarterly=100.0,
    )
    central_score = _scaled(_number(central_value), central_scale) if _has_number(central_value) else 0.0
    central_component = {
        "name": "central_bank_gold_demand", "score": _clamp(central_score),
        "quality": central_quality, "cadence": str(central_observation.get("period", "MONTHLY")),
        "value": _number(central_value) if _has_number(central_value) else None, "unit": "tonnes net",
        "observed_at": central_observation.get("observed_at", ""),
        "published_at": central_observation.get("published_at", ""),
        "source": central_observation.get("source", ""),
        "source_url": central_observation.get("source_url", ""),
        "summary": (
            f"Central banks reported {_number(central_value):+.1f} net tonnes "
            f"({str(central_observation.get('period', 'period unspecified')).lower()})."
            if _has_number(central_value) else "No verified central-bank net-purchase observation."
        ),
    }
    components.append(central_component)

    etf_observation = _institutional_observation(institutional, "gold_etf", "etf_tonnes_change")
    etf_value = (
        etf_observation.get("net_tonnes")
        if "net_tonnes" in etf_observation else etf_observation.get("etf_tonnes_change")
    )
    etf_quality = (
        _institutional_quality(etf_observation, release_days=45.0, observation_days=75.0, now=generated)
        if _has_number(etf_value) else 0.0
    )
    etf_scale = _tonnage_scale(etf_observation.get("period"), monthly=25.0, weekly=10.0, quarterly=75.0)
    etf_score = _scaled(_number(etf_value), etf_scale) if _has_number(etf_value) else 0.0
    etf_component = {
        "name": "gold_etf_physical_flows", "score": _clamp(etf_score), "quality": etf_quality,
        "cadence": str(etf_observation.get("period", "WEEKLY_MONTHLY")),
        "value": _number(etf_value) if _has_number(etf_value) else None, "unit": "tonnes net",
        "observed_at": etf_observation.get("observed_at", ""),
        "published_at": etf_observation.get("published_at", ""),
        "source": etf_observation.get("source", ""), "source_url": etf_observation.get("source_url", ""),
        "summary": (
            f"Physically backed gold ETFs changed by {_number(etf_value):+.1f} net tonnes."
            if _has_number(etf_value) else "No verified gold-ETF tonnage observation."
        ),
    }
    components.append(etf_component)

    cftc_observation = _institutional_observation(
        institutional, "managed_money", "managed_money_net_change_4w",
    )
    managed_change = cftc_observation.get("managed_money_net_change_4w")
    open_interest = _number(cftc_observation.get("open_interest"))
    managed_scale = max(25_000.0, abs(open_interest) * 0.08)
    managed_score = _scaled(_number(managed_change), managed_scale) if _has_number(managed_change) else 0.0
    managed_quality = (
        _institutional_quality(cftc_observation, release_days=14.0, observation_days=21.0, now=generated)
        if _has_number(managed_change) else 0.0
    )
    percentile = cftc_observation.get("managed_money_percentile_52w")
    if _has_number(percentile):
        extremity = max(0.0, abs(_number(percentile) - 0.5) - 0.35) / 0.15
        managed_quality *= 1.0 - 0.40 * min(1.0, extremity)
    cftc_component = {
        "name": "cftc_managed_money_flow", "score": _clamp(managed_score), "quality": _clamp(managed_quality),
        "cadence": "WEEKLY", "value": _number(managed_change) if _has_number(managed_change) else None,
        "unit": "contracts / 4 weeks", "open_interest": open_interest or None,
        "percentile_52w": _number(percentile) if _has_number(percentile) else None,
        "observed_at": cftc_observation.get("observed_at", ""),
        "published_at": cftc_observation.get("published_at", ""),
        "source": cftc_observation.get("source", ""), "source_url": cftc_observation.get("source_url", ""),
        "summary": (
            f"CFTC managed-money net positioning changed {_number(managed_change):+.0f} contracts over 4 weeks."
            if _has_number(managed_change) else "No verified CFTC managed-money observation."
        ),
    }
    components.append(cftc_component)

    institutional_inputs = (
        (central_component, 0.50), (etf_component, 0.30), (cftc_component, 0.20),
    )
    institutional_total = sum(weight * item["quality"] for item, weight in institutional_inputs)
    institutional_numerator = sum(
        weight * item["quality"] * item["score"] for item, weight in institutional_inputs
    )
    institutional_score = institutional_numerator / institutional_total if institutional_total else 0.0
    institutional_absolute = sum(
        weight * item["quality"] * abs(item["score"]) for item, weight in institutional_inputs
    )
    institutional_coherence = (
        abs(institutional_numerator) / institutional_absolute if institutional_absolute > 1e-9 else 1.0
    )
    institutional_availability = institutional_total / sum(weight for _, weight in institutional_inputs)
    institutional_quality = institutional_availability * (0.5 + 0.5 * institutional_coherence)
    components.append({
        "name": "institutional_demand_positioning", "score": _clamp(institutional_score),
        "quality": _clamp(institutional_quality), "cadence": "WEEKLY_MONTHLY",
        "coherence": round(institutional_coherence, 4),
        "source": institutional.get("source", ""),
        "summary": (
            "Quality-weighted central-bank, gold-ETF and CFTC institutional demand regime."
        ),
        "inputs": [item[0]["name"] for item in institutional_inputs if item[0]["quality"] > 0],
    })

    horizon_weights = {
        "SCALP": {
            "verified_release_surprise": 0.70,
            "official_release_reaction_scalp": 0.30,
        },
        "INTRADAY": {
            "verified_release_surprise": 0.35,
            "official_release_change": 0.10,
            "official_release_reaction_intraday": 0.20,
            "usd_yields_risk_regime": 0.25,
            "us_policy_uncertainty": 0.05,
            "systemic_financial_stress": 0.05,
        },
        "SWING": {
            "verified_release_surprise": 0.10,
            "usd_yields_risk_regime": 0.20,
            "us_policy_uncertainty": 0.05,
            "global_policy_uncertainty": 0.05,
            "systemic_financial_stress": 0.10,
            "inflation_recession_regime": 0.075,
            "world_bank_growth_outlook": 0.05,
            "institutional_demand_positioning": 0.375,
        },
    }
    by_name = {item["name"]: item for item in components}
    confidence_point_weights = {
        "SCALP": {
            "verified_release_surprise": 70.0,
            "official_release_reaction_scalp": 30.0,
        },
        "INTRADAY": {
            "verified_release_surprise": 35.0,
            "official_release_change": 10.0,
            "official_release_reaction_intraday": 20.0,
            "usd_yields_risk_regime": 25.0,
            "us_policy_uncertainty": 5.0,
            "systemic_financial_stress": 5.0,
        },
        # The 37.5 institutional points mirror the SWING model allocation and
        # remain split across physical official demand, ETF demand and CFTC.
        "SWING": {
            "verified_release_surprise": 10.0,
            "usd_yields_risk_regime": 20.0,
            "us_policy_uncertainty": 5.0,
            "global_policy_uncertainty": 5.0,
            "systemic_financial_stress": 10.0,
            "inflation_recession_regime": 7.5,
            "world_bank_growth_outlook": 5.0,
            "central_bank_gold_demand": 20.0,
            "gold_etf_physical_flows": 10.0,
            "cftc_managed_money_flow": 7.5,
        },
    }
    horizons: dict[str, Any] = {}
    for horizon, weights in horizon_weights.items():
        usable = [(by_name[name], weight) for name, weight in weights.items() if by_name[name]["quality"] > 0]
        total = sum(weight * item["quality"] for item, weight in usable)
        score = sum(weight * item["quality"] * item["score"] for item, weight in usable) / total if total else 0.0
        quality = sum(weight * item["quality"] for item, weight in usable) / sum(weights.values()) if usable else 0.0
        bias = "BUY" if score >= 0.20 else "SELL" if score <= -0.20 else "NEUTRAL"
        score_sign = 1.0 if score > 0 else -1.0 if score < 0 else 0.0
        point_breakdown: list[dict[str, Any]] = []
        for component_name, maximum_points in confidence_point_weights[horizon].items():
            item = by_name[component_name]
            source_score = float(item.get("score", 0.0) or 0.0)
            source_quality = float(item.get("quality", 0.0) or 0.0)
            coherence_factor = (
                0.5 + 0.5 * institutional_coherence
                if horizon == "SWING" and component_name in {
                    "central_bank_gold_demand", "gold_etf_physical_flows", "cftc_managed_money_flow",
                }
                else 1.0
            )
            magnitude = maximum_points * abs(source_score) * source_quality * coherence_factor
            aligned = score_sign != 0 and source_score * score_sign > 0
            opposed = score_sign != 0 and source_score * score_sign < 0
            signed_points = magnitude if aligned else -magnitude if opposed else 0.0
            point_breakdown.append({
                "component": component_name,
                "maximum_points": maximum_points,
                "points": round(signed_points, 2),
                "absolute_points": round(magnitude, 2),
                "relationship": "CONFIRMS" if aligned else "CONTRADICTS" if opposed else "NEUTRAL",
                "source_direction": "BUY" if source_score > 0 else "SELL" if source_score < 0 else "NEUTRAL",
                "source_score": round(source_score, 4),
                "source_quality": round(source_quality, 4),
            })
        confirming_points = sum(max(0.0, item["points"]) for item in point_breakdown)
        contradiction_points = sum(max(0.0, -item["points"]) for item in point_breakdown)
        confidence_points = max(0.0, min(100.0, confirming_points - contradiction_points))
        coverage_points = sum(
            float(item["maximum_points"]) * float(item["source_quality"])
            for item in point_breakdown
        )
        active_source_count = sum(float(item["source_quality"]) > 0 for item in point_breakdown)
        horizons[horizon] = {"bias": bias, "score": round(_clamp(score), 4), "quality": round(_clamp(quality), 4),
                             "role": "CONTEXT_AND_VETO_ONLY", "components": [item[0]["name"] for item in usable],
                             "confidence_points": round(confidence_points, 2),
                             "confirming_points": round(confirming_points, 2),
                             "contradiction_points": round(contradiction_points, 2),
                             "data_coverage": round(max(0.0, min(100.0, coverage_points)), 2),
                             "active_source_count": active_source_count,
                             "available_source_count": len(point_breakdown),
                             "confidence_breakdown": point_breakdown,
                             "confidence_method": (
                                 "quality-adjusted directional points; confirming sources add, "
                                 "contradicting sources subtract"
                             )}

    return {"advisor_name": "GOLD ECONOMIC ADVISOR V5", "version": "5.4",
            "generated_at": generated.astimezone(timezone.utc).isoformat(), "horizons": horizons,
            "components": components,
            "macro_context": {
                "source": macro.get("source", ""),
                "providers": list(macro.get("providers", []) or []),
                "generated_at": macro.get("generated_at", ""),
                "errors": dict(macro.get("errors", {}) or {}),
                "warnings": dict(macro.get("warnings", {}) or {}),
                "observation_count": len(observations),
            },
            "institutional_context_available": institutional_total > 0,
            "institutional_context": {
                "refresh_status": institutional.get("refresh_status", "MANUAL_OR_LEGACY" if institutional else "UNAVAILABLE"),
                "refresh_errors": institutional.get("refresh_errors", {}),
                "last_attempt_at": institutional.get("last_attempt_at", ""),
                "observations": institutional.get("observations", {}),
            },
            "execution_enabled": False, "orders_sent": False,
            "warning": "Scores are economic context, not calibrated probabilities or standalone trade signals."}
