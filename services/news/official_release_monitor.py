from __future__ import annotations

"""Low-frequency network monitor for fresh official US economic releases.

This module deliberately separates *publication detection* from prediction.
Census and Federal Reserve RSS items carry authoritative publication times.
BEA observations are emitted only when a running cache observes a new period
or a changed published value.  Previous values are not market consensus, so
events produced here carry a conservative directional-quality cap.
"""

import json
import math
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from services.utils.atomic_json import atomic_write_json


_USER_AGENT = "XAUUSD-Economic-Advisor/6.4 (local research; official public data)"
_EVENT_RETENTION = timedelta(hours=6)
_CENSUS_EVENT_RULES = (
    ("advance monthly sales for retail", "US Retail Sales", "HIGH"),
    ("retail and food services", "US Retail Sales", "HIGH"),
    ("advance report on durable goods", "US Durable Goods Orders", "HIGH"),
    ("new residential construction", "US Housing Starts", "MEDIUM"),
    ("international trade in goods and services", "US International Trade", "MEDIUM"),
)


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_fetch(url: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, application/rss+xml, application/xml, text/xml, text/html, */*",
        },
    )
    with urlopen(request, timeout=max(1.0, float(timeout))) as response:
        return response.read()


def _load_cache(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _plain_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(without_tags).replace("\xa0", " ").split())


def _rss_items(payload: bytes) -> list[dict[str, str]]:
    root = ElementTree.fromstring(payload.decode("utf-8-sig", errors="replace"))
    result: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        record: dict[str, str] = {}
        for name in ("title", "link", "guid", "description", "pubDate"):
            node = item.find(name)
            record[name] = "" if node is None or node.text is None else str(node.text).strip()
        result.append(record)
    return result


def _recent(event_time: datetime | None, now: datetime) -> bool:
    return bool(event_time and timedelta(seconds=-60) <= now - event_time <= _EVENT_RETENTION)


def _census_changes(description: str) -> list[float]:
    text = _plain_html(description)
    values = re.findall(
        r":\s*([+-]?\d+(?:\.\d+)?)\s*[^%\d]{0,10}%\s*(?:Change)?",
        text,
        flags=re.IGNORECASE,
    )
    result: list[float] = []
    for value in values:
        try:
            number = float(value)
        except ValueError:
            continue
        if math.isfinite(number):
            result.append(number)
    return result


def parse_census_release_events(payload: bytes, *, now: datetime) -> list[dict[str, Any]]:
    """Normalize recent market-relevant Census RSS publications."""
    events: list[dict[str, Any]] = []
    for item in _rss_items(payload):
        published = _utc(item.get("pubDate"))
        if not _recent(published, now):
            continue
        original_title = item.get("title", "")
        rule = next(
            (candidate for candidate in _CENSUS_EVENT_RULES if candidate[0] in original_title.lower()),
            None,
        )
        if rule is None:
            continue
        _, title, impact = rule
        values = _census_changes(item.get("description", ""))
        events.append({
            "title": title,
            "currency": "USD",
            "impact": impact,
            "event_time": published.isoformat(),
            "enabled": True,
            "source": "OFFICIAL_CENSUS_RSS",
            "provider": "U.S. Census Bureau",
            "external_id": f"CENSUS:{item.get('guid') or item.get('link')}:{published.isoformat()}",
            "calendar_confidence": "VERIFIED",
            "actual": values[0] if values else None,
            "forecast": None,
            "previous": values[1] if len(values) > 1 else None,
            "comparison_basis": "PREVIOUS_RELEASE" if len(values) > 1 else "NONE",
            "directional_quality": 0.30 if len(values) > 1 else 0.0,
            "reaction_eligible": True,
            "source_url": item.get("link", ""),
            "source_title": original_title,
        })
    return events


def _mixed_number(value: str) -> float | None:
    text = value.strip().replace("−", "-")
    mixed = re.fullmatch(r"(\d+)-(\d+)/(\d+)", text)
    fraction = re.fullmatch(r"(\d+)/(\d+)", text)
    try:
        if mixed:
            whole, numerator, denominator = (float(part) for part in mixed.groups())
            return whole + numerator / denominator if denominator else None
        if fraction:
            numerator, denominator = (float(part) for part in fraction.groups())
            return numerator / denominator if denominator else None
        result = float(text)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def parse_fed_target_midpoint(statement_html: bytes) -> float | None:
    text = _plain_html(statement_html.decode("utf-8-sig", errors="replace"))
    match = re.search(
        r"target range for the federal funds rate\s+(?:at|to)\s+"
        r"(\d+(?:\.\d+)?(?:-\d+/\d+)?|\d+/\d+)\s+to\s+"
        r"(\d+(?:\.\d+)?(?:-\d+/\d+)?|\d+/\d+)\s+percent",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    lower, upper = _mixed_number(match.group(1)), _mixed_number(match.group(2))
    return (lower + upper) / 2.0 if lower is not None and upper is not None else None


def parse_fed_release_events(
    payload: bytes,
    *,
    now: datetime,
    fetch: Callable[[str, float], bytes],
    timeout: float,
) -> list[dict[str, Any]]:
    """Normalize recent FOMC statements/minutes from the official Fed feed."""
    items = _rss_items(payload)
    statement_items = [
        item for item in items
        if "issues fomc statement" in item.get("title", "").lower()
    ]
    events: list[dict[str, Any]] = []
    for item in items:
        published = _utc(item.get("pubDate"))
        if not _recent(published, now):
            continue
        raw_title = item.get("title", "")
        lower_title = raw_title.lower()
        is_statement = "issues fomc statement" in lower_title
        is_minutes = "minutes of the federal open market committee" in lower_title
        if not (is_statement or is_minutes):
            continue

        actual = previous = None
        comparison_basis = "NONE"
        directional_quality = 0.0
        if is_statement and item.get("link"):
            try:
                current_index = statement_items.index(item)
            except ValueError:
                current_index = -1
            current_midpoint = parse_fed_target_midpoint(fetch(item["link"], timeout))
            previous_midpoint = None
            if current_index >= 0 and current_index + 1 < len(statement_items):
                prior_link = statement_items[current_index + 1].get("link", "")
                if prior_link:
                    previous_midpoint = parse_fed_target_midpoint(fetch(prior_link, timeout))
            actual, previous = current_midpoint, previous_midpoint
            if actual is not None and previous is not None:
                comparison_basis = "PREVIOUS_RELEASE"
                directional_quality = 0.35

        events.append({
            "title": "Fed Funds Rate Decision" if is_statement else "FOMC Minutes",
            "currency": "USD",
            "impact": "HIGH",
            "event_time": published.isoformat(),
            "enabled": True,
            "source": "OFFICIAL_FED_RSS",
            "provider": "Federal Reserve Board",
            "external_id": f"FED:{item.get('guid') or item.get('link')}:{published.isoformat()}",
            "calendar_confidence": "VERIFIED",
            "actual": actual,
            "forecast": None,
            "previous": previous,
            "comparison_basis": comparison_basis,
            "directional_quality": directional_quality,
            "reaction_eligible": True,
            "source_url": item.get("link", ""),
            "source_title": raw_title,
        })
    return events


def _bea_rows(payload: bytes, *, line_number: str) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8-sig"))
    results = data.get("BEAAPI", {}).get("Results", {})
    if results.get("Error"):
        raise RuntimeError(str(results["Error"].get("APIErrorDescription", "BEA API error")))
    rows = [
        dict(item) for item in results.get("Data", [])
        if str(item.get("LineNumber")) == str(line_number)
    ]
    return sorted(rows, key=lambda item: str(item.get("TimePeriod", "")))


def _bea_url(api_key: str, *, table: str, frequency: str, now: datetime) -> str:
    return "https://apps.bea.gov/api/data/?" + urlencode({
        "UserID": api_key,
        "method": "GetData",
        "DataSetName": "NIPA",
        "TableName": table,
        "Frequency": frequency,
        "Year": f"{now.year - 1},{now.year}",
        "ResultFormat": "JSON",
    })


def _float_value(row: dict[str, Any]) -> float | None:
    try:
        raw = row.get("DataValue") if "DataValue" in row else row.get("value", "")
        result = float(str(raw).replace(",", ""))
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def _update_bea_observation(
    *,
    name: str,
    title: str,
    rows: list[dict[str, Any]],
    previous_state: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not rows:
        return previous_state, None
    latest = rows[-1]
    latest_value = _float_value(latest)
    if latest_value is None:
        return previous_state, None
    prior_row = rows[-2] if len(rows) > 1 else {}
    period = str(latest.get("TimePeriod", ""))
    fingerprint = f"{period}:{latest_value:.10g}"
    new_state = {
        "fingerprint": fingerprint,
        "period": period,
        "value": latest_value,
        "observed_at": now.isoformat(),
    }
    old_fingerprint = str(previous_state.get("fingerprint", ""))
    if not old_fingerprint or old_fingerprint == fingerprint:
        return new_state, None

    period_changed = str(previous_state.get("period", "")) != period
    comparison_value = (
        _float_value(prior_row) if period_changed else _float_value(previous_state)
    )
    if comparison_value is None:
        return new_state, None
    quality = 0.35 if period_changed else 0.15
    event = {
        "title": title if period_changed else f"{title} Revision",
        "currency": "USD",
        "impact": "HIGH" if period_changed else "MEDIUM",
        "event_time": now.isoformat(),
        "enabled": True,
        "source": "OFFICIAL_BEA_API",
        "provider": "U.S. Bureau of Economic Analysis",
        "external_id": f"BEA:{name}:{fingerprint}:{now.isoformat()}",
        "calendar_confidence": "VERIFIED",
        "actual": latest_value,
        "forecast": None,
        "previous": comparison_value,
        "comparison_basis": "PREVIOUS_RELEASE",
        "directional_quality": quality,
        "reaction_eligible": True,
        "source_url": "https://apps.bea.gov/api/",
        "source_title": str(latest.get("LineDescription", title)),
        "reference_period": period,
    }
    return new_state, event


def _deduplicate(events: list[dict[str, Any]], *, now: datetime) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        event_time = _utc(event.get("event_time"))
        if not _recent(event_time, now):
            continue
        key = str(event.get("external_id") or f"{event.get('title')}:{event.get('event_time')}")
        unique[key] = event
    return sorted(unique.values(), key=lambda item: str(item.get("event_time", "")))


def build_official_release_context(
    *,
    cache_path: str | Path,
    refresh_seconds: float,
    timeout: float,
    bea_api_key: str = "",
    census_rss_url: str = "https://www.census.gov/economic-indicators/indicator.xml",
    fed_rss_url: str = "https://www.federalreserve.gov/feeds/press_monetary.xml",
    now: datetime | None = None,
    fetch: Callable[[str, float], bytes] | None = None,
) -> dict[str, Any]:
    generated = _utc(now or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    cached = _load_cache(cache_path)
    cached_at = _utc(cached.get("generated_at"))
    if cached_at and 0 <= (generated - cached_at).total_seconds() < max(1.0, refresh_seconds):
        return {**cached, "cache_status": "HIT"}

    fetcher = fetch or _default_fetch
    errors: dict[str, str] = {}
    statuses: dict[str, str] = {}
    events: list[dict[str, Any]] = list(cached.get("events", []) or [])
    bea_state = dict(cached.get("bea_state", {}) or {})

    try:
        census_payload = fetcher(census_rss_url, timeout)
        events.extend(parse_census_release_events(census_payload, now=generated))
        statuses["census_rss"] = "LIVE"
    except Exception as error:
        errors["census_rss"] = f"{type(error).__name__}: {error}"
        statuses["census_rss"] = "STALE_CACHE_FALLBACK"

    try:
        fed_payload = fetcher(fed_rss_url, timeout)
        events.extend(parse_fed_release_events(
            fed_payload, now=generated, fetch=fetcher, timeout=timeout,
        ))
        statuses["federal_reserve_rss"] = "LIVE"
    except Exception as error:
        errors["federal_reserve_rss"] = f"{type(error).__name__}: {error}"
        statuses["federal_reserve_rss"] = "STALE_CACHE_FALLBACK"

    if bea_api_key:
        try:
            gdp_rows = _bea_rows(
                fetcher(_bea_url(bea_api_key, table="T10101", frequency="Q", now=generated), timeout),
                line_number="1",
            )
            core_pce_rows = _bea_rows(
                fetcher(_bea_url(bea_api_key, table="T20807", frequency="M", now=generated), timeout),
                line_number="25",
            )
            gdp_state, gdp_event = _update_bea_observation(
                name="real_gdp", title="US GDP", rows=gdp_rows,
                previous_state=dict(bea_state.get("real_gdp", {}) or {}), now=generated,
            )
            pce_state, pce_event = _update_bea_observation(
                name="core_pce", title="US Core PCE Inflation", rows=core_pce_rows,
                previous_state=dict(bea_state.get("core_pce", {}) or {}), now=generated,
            )
            bea_state = {"real_gdp": gdp_state, "core_pce": pce_state}
            events.extend(event for event in (gdp_event, pce_event) if event is not None)
            statuses["bea_api"] = "LIVE"
        except Exception as error:
            errors["bea_api"] = f"{type(error).__name__}: {error}"
            statuses["bea_api"] = "STALE_CACHE_FALLBACK"
    else:
        statuses["bea_api"] = "NOT_CONFIGURED"

    result = {
        "schema_version": 1,
        "generated_at": generated.isoformat(),
        "cache_status": "REFRESHED",
        "providers": statuses,
        "errors": errors,
        "events": _deduplicate(events, now=generated),
        "bea_state": bea_state,
    }
    atomic_write_json(cache_path, result, indent=2)
    return result
