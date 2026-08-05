from __future__ import annotations

"""Health updater for free official economic-data sources.

This updater intentionally runs outside the trading loop.  It confirms whether
providers are reachable and records their intended market/session role.  A
healthy record is not a directional signal; actual-versus-forecast values must
still exist in the normalized event store before news can change confidence.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from config import scalping_settings

PROVIDERS = {
    "BLS_US": {
        "url": "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0",
        "currencies": ["USD"], "sessions": ["London", "New York"],
        "capability": "US labor and inflation source health",
    },
    "ECB_EU": {
        "url": "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?lastNObservations=1&format=csvdata",
        "currencies": ["EUR", "USD"], "sessions": ["London"],
        "capability": "Euro-area data source health",
    },
    "FED_US": {
        "url": "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "currencies": ["USD"], "sessions": ["London", "New York", "Asian"],
        "capability": "Federal Reserve release-feed health",
    },
    "BOE_UK": {
        "url": "https://www.bankofengland.co.uk/rss",
        "currencies": ["GBP"], "sessions": ["London"],
        "capability": "Bank of England source health",
    },
    "BOJ_JP": {
        "url": "https://www.boj.or.jp/en/whatsnew/index.htm",
        "currencies": ["JPY"], "sessions": ["Asian"],
        "capability": "Bank of Japan source health",
    },
    "RBA_AU": {
        "url": "https://www.rba.gov.au/updates/rss-feeds.html",
        "currencies": ["AUD"], "sessions": ["Asian"],
        "capability": "Reserve Bank of Australia source health",
    },
    "BEA_US": {
        "url": "https://apps.bea.gov/api/data/?UserID=samplekey&method=GETDATASETLIST&ResultFormat=JSON",
        "currencies": ["USD"], "sessions": ["London", "New York"],
        "capability": "US national-accounts source health",
    },
}


def _fetch(url: str, timeout: float = 8.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "XAUUSD-Unified-Research/1.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096)
            status = int(getattr(response, "status", 200) or 200)
            return {
                "healthy": 200 <= status < 300,
                "status": status,
                "sample_bytes": len(body),
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "message": "Official source reachable.",
            }
    except Exception as error:
        return {
            "healthy": False,
            "status": None,
            "sample_bytes": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "message": f"{type(error).__name__}: {error}",
        }


def update_official_provider_cache() -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for name, configuration in PROVIDERS.items():
        url = str(configuration["url"])
        providers[name] = {**configuration, **_fetch(url)}

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "providers": providers,
        "data_scope": "HEALTH_AND_CAPABILITY_ONLY",
        "directional_signal_available": False,
        "note": (
            "Reachability never authorizes a trade. Directional news requires "
            "normalized actual and forecast values in the economic-event store."
        ),
    }
    cache_path = str(scalping_settings.SCALPING_UNIFIED_PROVIDER_CACHE_FILE)
    directory = os.path.dirname(cache_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary = f"{cache_path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temporary, cache_path)
    return payload
