from __future__ import annotations

"""Point-in-time institutional gold-demand collection for Economic Advisor V6.

Only small, attributable observations are retained.  The collector does not
turn headlines into trades: it extracts the World Gold Council's latest
reported aggregate central-bank net purchase figure and the CFTC's official
weekly COMEX gold managed-money positioning.  Each source can fail
independently; the last valid observation remains available for the advisor's
own freshness checks.
"""

import html as html_module
import json
import math
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from services.utils.atomic_json import atomic_write_json


WGC_GOLD_FOCUS_URL = "https://www.gold.org/goldhub/gold-focus"
WGC_GOLD_ETF_URL = "https://www.gold.org/goldhub/data/global-gold-backed-etf-holdings-and-flows"
WGC_CENTRAL_BANK_URL_PATTERN = re.compile(
    r"/goldhub/gold-focus/(?P<year>20\d{2})/(?P<month>\d{2})/central-bank-gold-statistics[^\"'#?\s<]*",
    re.I,
)
CFTC_GOLD_DATASET_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CFTC_GOLD_CONTRACT_CODE = "088691"
DEFAULT_CACHE_PATH = "data/context/gold_institutional_context.json"

_MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ),
        start=1,
    )
}
_NUMBER = r"([-+]?\d+(?:\.\d+)?)"


class InstitutionalDataError(RuntimeError):
    pass


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): value or "" for key, value in attrs}
        if tag.lower() == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag.lower() == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content", "").strip()


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _fetch_text(url: str, timeout: float, headers: dict[str, str] | None = None) -> str:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; XAUUSD-AI-Research/2.0; point-in-time context)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    request_headers.update(headers or {})
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=max(1.0, float(timeout))) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def _plain_text(document: str) -> str:
    document = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", document, flags=re.I | re.S)
    document = re.sub(r"<[^>]+>", " ", document)
    return re.sub(r"\s+", " ", html_module.unescape(document)).strip()


def _human_date(day: str, month: str, year: str) -> datetime:
    month_number = _MONTHS.get(month.lower())
    if not month_number:
        raise InstitutionalDataError(f"Unrecognized WGC month: {month}")
    return datetime(int(year), month_number, int(day), tzinfo=timezone.utc)


def discover_latest_wgc_central_bank_url(archive_html: str) -> str:
    parser = _PageMetadataParser()
    parser.feed(archive_html)
    candidates: set[str] = set()
    for link in parser.links:
        match = WGC_CENTRAL_BANK_URL_PATTERN.search(link)
        if match:
            candidates.add(urljoin(WGC_GOLD_FOCUS_URL, match.group(0)))
    if not candidates:
        # This fallback also copes with malformed anchors that HTMLParser omits.
        candidates.update(urljoin(WGC_GOLD_FOCUS_URL, match.group(0))
                          for match in WGC_CENTRAL_BANK_URL_PATTERN.finditer(archive_html))
    if not candidates:
        raise InstitutionalDataError("No central-bank statistics article was found on Goldhub.")

    def published_bucket(url: str) -> tuple[int, int, str]:
        match = WGC_CENTRAL_BANK_URL_PATTERN.search(url)
        return (int(match.group("year")), int(match.group("month")), url) if match else (0, 0, url)

    return max(candidates, key=published_bucket)


def parse_wgc_central_bank_article(article_html: str, source_url: str) -> dict[str, Any]:
    parser = _PageMetadataParser()
    parser.feed(article_html)
    article_text = _plain_text(article_html)
    search_text = " ".join(part for part in (parser.description, article_text) if part)

    positive_patterns = (
        rf"net buying(?:\s+was)?(?:\s+reported)?\s+(?:at|of)\s*(?:around\s+|approximately\s+|~\s*)?{_NUMBER}\s*(?:t\b|tonnes?\b)",
        rf"net purchases?\s+(?:were\s+|was\s+)?(?:reported\s+)?(?:at|of|totalled|totaled|reached)\s*(?:around\s+|approximately\s+|~\s*)?{_NUMBER}\s*(?:t\b|tonnes?\b)",
        rf"central banks?\s+(?:globally\s+)?(?:added|bought|purchased)\s+(?:a\s+)?net\s*(?:of\s+)?{_NUMBER}\s*(?:t\b|tonnes?\b)",
        rf"{_NUMBER}\s*(?:t\b|tonnes?\b)\s+of\s+net\s+(?:gold\s+)?purchases?",
    )
    negative_patterns = (
        rf"net (?:gold\s+)?sales?\s+(?:were\s+|was\s+)?(?:reported\s+)?(?:at|of|totalled|totaled|reached)\s*(?:around\s+|approximately\s+|~\s*)?{_NUMBER}\s*(?:t\b|tonnes?\b)",
        rf"central banks?\s+(?:globally\s+)?(?:sold|offloaded)\s+(?:a\s+)?net\s*(?:of\s+)?{_NUMBER}\s*(?:t\b|tonnes?\b)",
    )
    net_candidates: list[tuple[int, float]] = []
    for sign, patterns in ((1.0, positive_patterns), (-1.0, negative_patterns)):
        for pattern in patterns:
            match = re.search(pattern, search_text, flags=re.I)
            if match:
                net_candidates.append((match.start(), sign * abs(float(match.group(1)))))
    if not net_candidates:
        raise InstitutionalDataError("The WGC article did not expose a recognizable aggregate net-tonnage figure.")
    # The lead/description states the current reporting month's aggregate.
    # Later article text can contain prior-period or year-to-date comparisons.
    net_tonnes = min(net_candidates, key=lambda item: item[0])[1]

    observed_match = re.search(
        r"Data\s+(?:to|as of)\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})",
        search_text,
        flags=re.I,
    )
    if not observed_match:
        raise InstitutionalDataError("The WGC observation date could not be verified.")
    observed = _human_date(*observed_match.groups())

    url_bucket = WGC_CENTRAL_BANK_URL_PATTERN.search(source_url)
    published: datetime | None = None
    date_matches = re.findall(r"\b(\d{1,2})\s+([A-Za-z]+),?\s+(20\d{2})\b", article_text)
    for parts in date_matches:
        try:
            candidate = _human_date(*parts)
        except InstitutionalDataError:
            continue
        if url_bucket and candidate.year == int(url_bucket.group("year")) and candidate.month == int(url_bucket.group("month")):
            published = candidate
            break
    if published is None:
        raise InstitutionalDataError("The WGC publication date could not be verified.")
    if published < observed:
        raise InstitutionalDataError("The WGC publication date precedes its observation date.")

    ytd_match = re.search(
        rf"(?:y[- ]t[- ]d|year[- ]to[- ]date)[^.]{{0,100}}?(?:totalled|totaled|reached|of|at)\s*"
        rf"(?:around\s+|approximately\s+|~\s*)?{_NUMBER}\s*(?:t\b|tonnes?\b)",
        search_text,
        flags=re.I,
    )
    result: dict[str, Any] = {
        "available": True,
        "metric": "REPORTED_MONTHLY_NET_PURCHASES_TONNES",
        "period": "MONTHLY",
        "net_tonnes": net_tonnes,
        "observed_at": observed.isoformat(),
        "published_at": published.isoformat(),
        "source": "World Gold Council central-bank statistics",
        "source_url": source_url,
        "source_quality": 0.90,
        "revision_risk": "HIGH",
    }
    if ytd_match:
        result["year_to_date_net_tonnes"] = float(ytd_match.group(1))
    return result


def fetch_wgc_central_bank_observation(
    *, timeout: float = 12.0, fetcher: Callable[[str, float], str] | None = None,
) -> dict[str, Any]:
    get = fetcher or (lambda url, seconds: _fetch_text(url, seconds))
    archive = get(WGC_GOLD_FOCUS_URL, timeout)
    article_url = discover_latest_wgc_central_bank_url(archive)
    return parse_wgc_central_bank_article(get(article_url, timeout), article_url)


def parse_wgc_gold_etf_article(article_html: str, source_url: str = WGC_GOLD_ETF_URL) -> dict[str, Any]:
    text = _plain_text(article_html)
    flow_candidates: list[tuple[int, float]] = []
    positive_patterns = (
        rf"(?:collective\s+)?holdings\s+(?:rebounded|rose|increased|grew)\s+by\s+{_NUMBER}\s*(?:t\b|tonnes?\b)",
        rf"global gold(?: backed)? ETFs?\s+(?:added|gained)\s+{_NUMBER}\s*(?:t\b|tonnes?\b)",
    )
    negative_patterns = (
        rf"(?:collective\s+)?holdings\s+(?:fell|declined|dropped|decreased|contracted)\s+by\s+{_NUMBER}\s*(?:t\b|tonnes?\b)",
        rf"global gold(?: backed)? ETFs?\s+(?:shed|lost)\s+{_NUMBER}\s*(?:t\b|tonnes?\b)",
    )
    for sign, patterns in ((1.0, positive_patterns), (-1.0, negative_patterns)):
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                flow_candidates.append((match.start(), sign * abs(float(match.group(1)))))
    if not flow_candidates:
        raise InstitutionalDataError("The WGC ETF article did not expose a recognizable monthly tonnage change.")
    net_tonnes = min(flow_candidates, key=lambda item: item[0])[1]

    observed_match = re.search(
        r"(?:Data\s+)?As of\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})",
        text,
        flags=re.I,
    )
    if not observed_match:
        raise InstitutionalDataError("The WGC ETF observation date could not be verified.")
    observed = _human_date(*observed_match.groups())
    published_match = re.search(r'"datePublished"\s*:\s*"([^"\\]+)', article_html, flags=re.I)
    published = _utc(published_match.group(1)) if published_match else None
    if published is None:
        raise InstitutionalDataError("The WGC ETF publication date could not be verified.")
    if published < observed:
        raise InstitutionalDataError("The WGC ETF publication date precedes its observation date.")
    return {
        "available": True,
        "metric": "GLOBAL_PHYSICALLY_BACKED_GOLD_ETF_NET_FLOW_TONNES",
        "period": "MONTHLY",
        "net_tonnes": net_tonnes,
        "observed_at": observed.isoformat(),
        "published_at": published.isoformat(),
        "source": "World Gold Council gold ETF holdings and flows",
        "source_url": source_url,
        "source_quality": 0.90,
        "revision_risk": "MEDIUM",
    }


def fetch_wgc_gold_etf_observation(
    *, timeout: float = 12.0, fetcher: Callable[[str, float], str] | None = None,
) -> dict[str, Any]:
    get = fetcher or (lambda url, seconds: _fetch_text(url, seconds))
    return parse_wgc_gold_etf_article(get(WGC_GOLD_ETF_URL, timeout), WGC_GOLD_ETF_URL)


def parse_cftc_gold_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for row in records:
        market = str(row.get("market_and_exchange_names", "")).upper()
        if not market.startswith("GOLD - COMMODITY EXCHANGE"):
            continue
        observed = _utc(row.get("report_date_as_yyyy_mm_dd"))
        long_positions = _finite(row.get("m_money_positions_long_all"))
        short_positions = _finite(row.get("m_money_positions_short_all"))
        open_interest = _finite(row.get("open_interest_all"))
        if observed is None or long_positions is None or short_positions is None:
            continue
        normalized.append({
            "observed": observed,
            "net": long_positions - short_positions,
            "long": long_positions,
            "short": short_positions,
            "open_interest": open_interest,
        })
    normalized.sort(key=lambda item: item["observed"], reverse=True)
    if len(normalized) < 5:
        raise InstitutionalDataError("CFTC returned fewer than five usable weekly COMEX gold records.")

    latest = normalized[0]
    change_4w = latest["net"] - normalized[4]["net"]
    history = [item["net"] for item in normalized[:52]]
    percentile = sum(value <= latest["net"] for value in history) / len(history)
    # The CFTC report reflects Tuesday positions and is normally published on
    # Friday.  20:30 UTC is only a conservative availability timestamp; the
    # retrieved_at field below is the definitive locally-known time.
    published = (latest["observed"] + timedelta(days=3)).replace(hour=20, minute=30)
    return {
        "available": True,
        "metric": "COMEX_GOLD_MANAGED_MONEY_FUTURES_ONLY",
        "period": "WEEKLY",
        "managed_money_net": latest["net"],
        "managed_money_net_change_4w": change_4w,
        "managed_money_percentile_52w": percentile,
        "open_interest": latest["open_interest"],
        "observed_at": latest["observed"].isoformat(),
        "published_at": published.isoformat(),
        "source": "U.S. CFTC Disaggregated Futures Only",
        "source_url": CFTC_GOLD_DATASET_URL,
        "source_quality": 0.98,
        "revision_risk": "MEDIUM",
    }


def fetch_cftc_gold_observation(
    *, timeout: float = 12.0, app_token: str = "",
    fetcher: Callable[[str, float, dict[str, str]], str] | None = None,
) -> dict[str, Any]:
    query = {
        "$select": (
            "market_and_exchange_names,report_date_as_yyyy_mm_dd,"
            "m_money_positions_long_all,m_money_positions_short_all,open_interest_all"
        ),
        "$where": f"cftc_contract_market_code='{CFTC_GOLD_CONTRACT_CODE}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "60",
    }
    url = f"{CFTC_GOLD_DATASET_URL}?{urlencode(query)}"
    headers = {"Accept": "application/json"}
    if str(app_token).strip():
        headers["X-App-Token"] = str(app_token).strip()
    get = fetcher or (lambda target, seconds, custom_headers: _fetch_text(target, seconds, custom_headers))
    try:
        payload = json.loads(get(url, timeout, headers))
    except json.JSONDecodeError as error:
        raise InstitutionalDataError("CFTC returned invalid JSON.") from error
    if not isinstance(payload, list):
        raise InstitutionalDataError("CFTC returned an unexpected response schema.")
    return parse_cftc_gold_records(payload)


def _load_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _legacy_observations(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    existing = payload.get("observations")
    if isinstance(existing, dict):
        return deepcopy({str(key): value for key, value in existing.items() if isinstance(value, dict)})
    source = str(payload.get("source", "")).strip()
    observed_at = payload.get("observed_at")
    if not source or _utc(observed_at) is None:
        return {}
    common = {
        "observed_at": str(observed_at),
        "published_at": str(payload.get("recorded_at") or observed_at),
        "source": source,
        "source_url": str(payload.get("source_url", "")),
        "source_quality": 0.75,
        "revision_risk": "UNKNOWN",
    }
    observations: dict[str, dict[str, Any]] = {}
    if "central_bank_net_tonnes_change" in payload:
        observations["central_bank"] = {
            **common, "available": True, "period": "UNSPECIFIED",
            "metric": "NET_PURCHASES_TONNES", "net_tonnes": payload["central_bank_net_tonnes_change"],
        }
    if "etf_tonnes_change" in payload:
        observations["gold_etf"] = {
            **common, "available": True, "period": "UNSPECIFIED",
            "metric": "GOLD_ETF_NET_FLOW_TONNES", "net_tonnes": payload["etf_tonnes_change"],
        }
    if "managed_money_net_change_4w" in payload:
        observations["managed_money"] = {
            **common, "available": True, "period": "WEEKLY",
            "metric": "COMEX_GOLD_MANAGED_MONEY",
            "managed_money_net_change_4w": payload["managed_money_net_change_4w"],
            "managed_money_percentile_52w": payload.get("managed_money_percentile_52w"),
        }
    return observations


def _latest_observation_time(observations: dict[str, dict[str, Any]]) -> str:
    dates = [_utc(item.get("observed_at")) for item in observations.values()]
    usable = [item for item in dates if item is not None]
    return max(usable).isoformat() if usable else ""


def _legacy_projection(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    projection: dict[str, Any] = {}
    central = observations.get("central_bank", {})
    etf = observations.get("gold_etf", {})
    cftc = observations.get("managed_money", {})
    if _finite(central.get("net_tonnes")) is not None:
        projection["central_bank_net_tonnes_change"] = float(central["net_tonnes"])
    if _finite(etf.get("net_tonnes")) is not None:
        projection["etf_tonnes_change"] = float(etf["net_tonnes"])
    if _finite(cftc.get("managed_money_net_change_4w")) is not None:
        projection["managed_money_net_change_4w"] = float(cftc["managed_money_net_change_4w"])
    if _finite(cftc.get("managed_money_percentile_52w")) is not None:
        projection["managed_money_percentile_52w"] = float(cftc["managed_money_percentile_52w"])
    return projection


def sync_gold_institutional_context_if_needed(
    *,
    cache_path: str | Path = DEFAULT_CACHE_PATH,
    timeout: float = 12.0,
    max_cache_age_seconds: float = 21_600.0,
    force: bool = False,
    cftc_app_token: str = "",
    now: datetime | None = None,
    wgc_fetch: Callable[[], dict[str, Any]] | None = None,
    etf_fetch: Callable[[], dict[str, Any]] | None = None,
    cftc_fetch: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Refresh independent sources and atomically persist a normalized cache."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    path = Path(cache_path)
    cached = _load_cache(path)
    last_attempt = _utc(cached.get("last_attempt_at") or cached.get("generated_at") or cached.get("recorded_at"))
    if not force and last_attempt is not None:
        age = (current - last_attempt).total_seconds()
        if 0 <= age <= max(0.0, float(max_cache_age_seconds)):
            return cached

    observations = _legacy_observations(cached)
    errors: dict[str, str] = {}
    refreshed: list[str] = []
    try:
        observations["central_bank"] = (
            wgc_fetch() if wgc_fetch else fetch_wgc_central_bank_observation(timeout=timeout)
        )
        observations["central_bank"]["retrieved_at"] = current.isoformat()
        refreshed.append("central_bank")
    except Exception as error:
        errors["central_bank"] = f"{type(error).__name__}: {error}"

    try:
        observations["gold_etf"] = (
            etf_fetch() if etf_fetch else fetch_wgc_gold_etf_observation(timeout=timeout)
        )
        observations["gold_etf"]["retrieved_at"] = current.isoformat()
        refreshed.append("gold_etf")
    except Exception as error:
        errors["gold_etf"] = f"{type(error).__name__}: {error}"

    try:
        observations["managed_money"] = (
            cftc_fetch() if cftc_fetch else fetch_cftc_gold_observation(
                timeout=timeout, app_token=cftc_app_token,
            )
        )
        observations["managed_money"]["retrieved_at"] = current.isoformat()
        refreshed.append("managed_money")
    except Exception as error:
        errors["managed_money"] = f"{type(error).__name__}: {error}"

    sources = sorted({str(item.get("source", "")).strip() for item in observations.values()
                      if str(item.get("source", "")).strip()})
    if refreshed and not errors:
        status = "LIVE_REFRESH"
    elif refreshed:
        status = "PARTIAL_REFRESH"
    elif observations:
        status = "CACHE_ONLY"
    else:
        status = "UNAVAILABLE"
    result: dict[str, Any] = {
        "schema_version": 2,
        "generated_at": current.isoformat(),
        "last_attempt_at": current.isoformat(),
        "last_success_at": current.isoformat() if refreshed else cached.get("last_success_at", ""),
        "refresh_status": status,
        "refreshed_sources": refreshed,
        "refresh_errors": errors,
        "observed_at": _latest_observation_time(observations),
        "source": " | ".join(sources),
        "observations": observations,
        **_legacy_projection(observations),
        "usage": "SWING_REGIME_CONTEXT_ONLY",
        "warning": (
            "Delayed and revisable institutional observations. They can adjust SWING economic context, "
            "but cannot authorize a trade or affect SCALP entries."
        ),
    }
    atomic_write_json(path, result, indent=2)
    return result
