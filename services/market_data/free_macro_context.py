from __future__ import annotations

"""Free macro context for XAUUSD.

Primary source:
    Official FRED observations API when a key is configured; FRED graph CSV
    remains the no-key fallback (Federal Reserve Bank of St. Louis).

The module is intentionally slow/contextual. It must never replace MT5
executable quotes, spreads, fills, or account state.

Important research rule:
    current FRED observations may contain later revisions. Therefore the
    live context is suitable for live/demo context, but must NOT be used as
    historical ML training data unless point-in-time/vintage observations are
    collected separately.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


DEFAULT_SERIES = {
    "us10y": "DGS10",
    "us10y_real": "DFII10",
    "us2y": "DGS2",
    "usd_broad": "DTWEXBGS",
    "fed_funds": "DFF",
    "vix": "VIXCLS",
    "cpi": "CPIAUCSL",
    "pce": "PCEPI",
    "unemployment": "UNRATE",
    "payrolls": "PAYEMS",
    "global_policy_uncertainty": "GEPUCURRENT",
    "us_policy_uncertainty": "USEPUINDXD",
    "financial_stress_stl": "STLFSI4",
    "financial_conditions_chicago": "NFCI",
    "inflation_expectation_10y": "T10YIE",
    "recession_indicator": "SAHMREALTIME",
}

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
WORLD_BANK_GEP_URL = (
    "https://api.worldbank.org/v2/sources/27/country/WLT/series/"
    "NYGDPMKTPKDZ/time/all/data"
)


class FreeMacroDataError(RuntimeError):
    pass


def _fetch_csv(series_id: str, timeout: float = 8.0) -> pd.DataFrame:
    query = urlencode({"id": series_id})
    request = Request(
        f"{FRED_URL}?{query}",
        headers={"User-Agent": "XAUUSD-AI-Research/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        frame = pd.read_csv(response)

    if frame.empty or len(frame.columns) < 2:
        raise FreeMacroDataError(f"FRED returned no usable data for {series_id}.")

    frame = frame.iloc[:, :2].copy()
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["date", "value"]).sort_values("date")
    if frame.empty:
        raise FreeMacroDataError(f"FRED returned no numeric observations for {series_id}.")
    return frame


def _fetch_api(series_id: str, api_key: str, timeout: float = 8.0) -> pd.DataFrame:
    """Fetch only recent observations through the official keyed FRED API."""
    query = urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 120,
    })
    request = Request(
        f"{FRED_API_URL}?{query}",
        headers={"User-Agent": "XAUUSD-AI-Research/2.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    rows = payload.get("observations", []) if isinstance(payload, dict) else []
    frame = pd.DataFrame(rows)
    if frame.empty or not {"date", "value"}.issubset(frame.columns):
        raise FreeMacroDataError(f"FRED API returned no usable data for {series_id}.")
    frame = frame.loc[:, ["date", "value"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["date", "value"]).sort_values("date")
    if frame.empty:
        raise FreeMacroDataError(f"FRED API returned no numeric observations for {series_id}.")
    return frame


def _latest_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    latest = frame.iloc[-1]
    value = float(latest["value"])
    date = latest["date"].to_pydatetime().astimezone(timezone.utc)

    result: dict[str, Any] = {
        "value": value,
        "observation_time": date.isoformat(),
        "age_days": round(max(0.0, (datetime.now(timezone.utc) - date).total_seconds() / 86400.0), 3),
    }

    for periods, key in ((1, "change_1"), (5, "change_5"), (20, "change_20")):
        if len(frame) > periods:
            previous = float(frame.iloc[-1 - periods]["value"])
            result[key] = round(value - previous, 8)
            if previous != 0:
                result[f"pct_change_{periods}"] = round((value / previous - 1.0) * 100.0, 6)

    if len(frame) >= 20:
        mean_5 = float(frame["value"].iloc[-5:].mean())
        mean_20 = float(frame["value"].iloc[-20:].mean())
        result["mean_5"] = round(mean_5, 8)
        result["mean_20"] = round(mean_20, 8)
        result["mean_5_minus_20"] = round(mean_5 - mean_20, 8)

    return result


def _fetch_world_bank_global_growth(
    timeout: float = 8.0, now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch the World Bank GEP world-growth path from source 27.

    This is semi-annual structural context.  It is not a release surprise and
    is never allowed to become a short-horizon trigger.
    """
    query = urlencode({"format": "json", "per_page": 100})
    request = Request(
        f"{WORLD_BANK_GEP_URL}?{query}",
        headers={"User-Agent": "XAUUSD-AI-Research/3.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict) or not isinstance(payload.get("source"), dict):
        raise FreeMacroDataError("World Bank GEP returned no usable payload.")

    values: dict[int, float] = {}
    for row in payload["source"].get("data", []):
        if not isinstance(row, dict):
            continue
        year = None
        for variable in row.get("variable", []):
            if isinstance(variable, dict) and str(variable.get("concept", "")).lower() == "time":
                try:
                    year = int(variable.get("value") or variable.get("id"))
                except (TypeError, ValueError):
                    year = None
                break
        try:
            number = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        if year is not None:
            values[year] = number
    if not values:
        raise FreeMacroDataError("World Bank GEP returned no numeric world-growth values.")

    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)
    current_year = reference.year
    selected_year = current_year if current_year in values else max(
        (year for year in values if year <= current_year), default=max(values)
    )
    updated_text = str(payload.get("lastupdated", "")).strip()
    try:
        updated = datetime.fromisoformat(updated_text).replace(tzinfo=timezone.utc)
    except ValueError:
        updated = reference
    current_growth = values[selected_year]
    previous_growth = values.get(selected_year - 1)
    next_growth = values.get(selected_year + 1)
    return {
        "value": current_growth,
        "unit": "% real GDP growth",
        "forecast_year": selected_year,
        "previous_year_growth": previous_growth,
        "next_year_growth": next_growth,
        "change_from_previous_year": (
            round(current_growth - previous_growth, 6) if previous_growth is not None else None
        ),
        "change_to_next_year": (
            round(next_growth - current_growth, 6) if next_growth is not None else None
        ),
        "observation_time": updated.isoformat(),
        "age_days": round(
            max(0.0, (reference - updated).total_seconds() / 86400.0), 3
        ),
        "source": "World Bank Global Economic Prospects",
        "source_url": "https://databank.worldbank.org/source/global-economic-prospects",
        "source_quality": 0.98,
        "cadence": "SEMI_ANNUAL",
    }


def build_free_macro_context(
    *,
    series: dict[str, str] | None = None,
    cache_path: str = "data/context/free_macro_context.json",
    timeout: float = 8.0,
    max_cache_age_seconds: float = 3600.0,
    api_key: str | None = None,
    include_world_bank: bool = True,
) -> dict[str, Any]:
    mapping = dict(DEFAULT_SERIES)
    if series:
        mapping.update(series)

    path = Path(cache_path)
    now = datetime.now(timezone.utc)
    prior_cache: dict[str, Any] = {}

    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            prior_cache = cached if isinstance(cached, dict) else {}
            generated = datetime.fromisoformat(
                str(cached["generated_at"]).replace("Z", "+00:00")
            )
            if (now - generated).total_seconds() <= max_cache_age_seconds:
                return cached
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass

    observations: dict[str, Any] = {}
    errors: dict[str, str] = {}
    warnings: dict[str, str] = {}
    configured_api_key = str(api_key if api_key is not None else os.getenv("FRED_API_KEY", "")).strip()

    def fetch_one(name: str, series_id: str) -> tuple[str, str, dict[str, Any], str | None]:
        api_warning = None
        if configured_api_key:
            try:
                frame = _fetch_api(series_id, configured_api_key, timeout=timeout)
                method = "FRED_API"
            except Exception as exc:
                # One bounded fallback avoids losing a source during a transient
                # API timeout/502 while also avoiding repeated rate-limit loops.
                api_warning = f"{type(exc).__name__}: {exc}"
                frame = _fetch_csv(series_id, timeout=timeout)
                method = "FRED_GRAPH_CSV_FALLBACK"
        else:
            frame = _fetch_csv(series_id, timeout=timeout)
            method = "FRED_GRAPH_CSV"
        return name, series_id, {**_latest_metrics(frame), "retrieval_method": method}, api_warning

    # FRED series are independent. A small bounded pool keeps a first refresh
    # from taking N x timeout seconds while remaining conservative on API rate.
    provider_names = ["FRED"]
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(mapping) + int(include_world_bank)))) as executor:
        futures = {
            executor.submit(fetch_one, name, series_id): ("FRED", name, series_id)
            for name, series_id in mapping.items()
        }
        if include_world_bank:
            futures[executor.submit(_fetch_world_bank_global_growth, timeout, now)] = (
                "WORLD_BANK", "world_bank_global_growth", "NYGDPMKTPKDZ"
            )
            provider_names.append("World Bank Global Economic Prospects")
        for future in as_completed(futures):
            provider, name, series_id = futures[future]
            try:
                if provider == "WORLD_BANK":
                    observations[name] = future.result()
                else:
                    _, _, metrics, warning = future.result()
                    observations[name] = {"series_id": series_id, **metrics}
                    if warning:
                        warnings[name] = "Official API failed; CSV fallback succeeded: " + warning
            except Exception as exc:
                errors[name] = f"{type(exc).__name__}: {exc}"

    # Preserve the last valid point for an independently failed source. Its
    # original observation timestamp remains unchanged, so downstream quality
    # continues to decay rather than being reset by this refresh attempt.
    prior_observations = prior_cache.get("observations", {}) if isinstance(prior_cache, dict) else {}
    if isinstance(prior_observations, dict):
        for name in errors:
            previous = prior_observations.get(name)
            if isinstance(previous, dict) and previous:
                observations[name] = {
                    **previous,
                    "retrieval_method": "STALE_CACHE_FALLBACK",
                    "last_refresh_error": errors[name],
                }

    # Gold macro pressure is deliberately simple and transparent. It is a
    # contextual feature, not a trading rule and not a probability.
    usd_change = float(observations.get("usd_broad", {}).get("change_5", 0.0) or 0.0)
    real_yield_change = float(observations.get("us10y_real", {}).get("change_5", 0.0) or 0.0)
    nominal_yield_change = float(observations.get("us10y", {}).get("change_5", 0.0) or 0.0)
    vix_change = float(observations.get("vix", {}).get("change_5", 0.0) or 0.0)

    # Lower USD / lower real yields are generally gold-supportive; the sign is
    # used only as a feature. The ML/meta layer must learn its economic value.
    gold_pressure = 0.0
    # A stronger broad USD is normally a headwind for USD-denominated gold;
    # a weaker USD is supportive. The previous sign was reversed.
    gold_pressure += 1.0 if usd_change < 0 else -1.0 if usd_change > 0 else 0.0
    gold_pressure += -1.0 if real_yield_change > 0 else 1.0 if real_yield_change < 0 else 0.0
    gold_pressure += -0.25 if nominal_yield_change > 0 else 0.25 if nominal_yield_change < 0 else 0.0
    gold_pressure += 0.15 if vix_change > 0 else -0.15 if vix_change < 0 else 0.0

    gold_bias = (
        "BUY" if gold_pressure >= 1.0
        else "SELL" if gold_pressure <= -1.0
        else "NEUTRAL"
    )

    result = {
        "schema_version": 3,
        "available": bool(observations),
        "generated_at": now.isoformat(),
        "source": (
            "FRED official observations API" if configured_api_key
            else "FRED graph CSV current observations"
        ) + (" + World Bank Global Economic Prospects API" if include_world_bank else ""),
        "providers": provider_names,
        "historical_training_safe": False,
        "historical_training_note": (
            "Current FRED series can be revised. Use point-in-time/vintage "
            "snapshots for backtest training."
        ),
        "observations": observations,
        "errors": errors,
        "warnings": warnings,
        "gold_bias": gold_bias,
        "gold_pressure_raw": round(gold_pressure, 4),
    }

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass

    return result
