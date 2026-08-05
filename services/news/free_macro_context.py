from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import free_data_settings
from services.utils.atomic_json import atomic_write_json


def _get_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {"User-Agent": "AI-Gold-Trading-V6/1.0"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=free_data_settings.HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _result(name: str, *, enabled: bool, success: bool, message: str, data: Any = None) -> dict[str, Any]:
    return {"provider": name, "enabled": enabled, "success": success, "message": message, "data": data}


def check_bls() -> dict[str, Any]:
    # CPI-U and unemployment rate. Public v1 works without a key.
    try:
        payload = {"seriesid": ["CUUR0000SA0", "LNS14000000"], "latest": True}
        if free_data_settings.BLS_API_KEY:
            payload["registrationkey"] = free_data_settings.BLS_API_KEY
        data = _get_json(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            method="POST",
            payload=payload,
        )
        ok = str(data.get("status", "")).upper() == "REQUEST_SUCCEEDED"
        return _result("BLS", enabled=True, success=ok, message="Official BLS public API reachable." if ok else str(data.get("message")), data=data)
    except Exception as exc:
        return _result("BLS", enabled=True, success=False, message=f"BLS check failed: {exc}")


def check_fred() -> dict[str, Any]:
    key = free_data_settings.FRED_API_KEY
    if not key:
        return _result("FRED", enabled=False, success=False, message="Optional FRED_API_KEY is not configured.")
    query = urllib.parse.urlencode({"series_id": "DGS10", "api_key": key, "file_type": "json", "limit": 1, "sort_order": "desc"})
    try:
        data = _get_json("https://api.stlouisfed.org/fred/series/observations?" + query)
        ok = bool(data.get("observations"))
        return _result("FRED", enabled=True, success=ok, message="FRED API reachable." if ok else "FRED returned no observations.", data=data)
    except Exception as exc:
        return _result("FRED", enabled=True, success=False, message=f"FRED check failed: {exc}")


def check_bea() -> dict[str, Any]:
    key = free_data_settings.BEA_API_KEY
    if not key:
        return _result("BEA", enabled=False, success=False, message="Optional BEA_API_KEY is not configured.")
    query = urllib.parse.urlencode({"UserID": key, "method": "GETDATASETLIST", "ResultFormat": "JSON"})
    try:
        data = _get_json("https://apps.bea.gov/api/data/?" + query)
        ok = bool(data.get("BEAAPI"))
        return _result("BEA", enabled=True, success=ok, message="BEA API reachable." if ok else "BEA response unavailable.", data=data)
    except Exception as exc:
        return _result("BEA", enabled=True, success=False, message=f"BEA check failed: {exc}")


def check_finnhub() -> dict[str, Any]:
    key = free_data_settings.FINNHUB_API_KEY
    if not key:
        return _result("Finnhub", enabled=False, success=False, message="Optional FINNHUB_API_KEY is not configured.")
    try:
        data = _get_json("https://finnhub.io/api/v1/calendar/economic?token=" + urllib.parse.quote(key))
        ok = isinstance(data, dict)
        return _result("Finnhub", enabled=True, success=ok, message="Finnhub economic-calendar API reachable." if ok else "Unexpected Finnhub response.", data=data)
    except Exception as exc:
        return _result("Finnhub", enabled=True, success=False, message=f"Finnhub check failed: {exc}")


def check_alpha_vantage() -> dict[str, Any]:
    key = free_data_settings.ALPHA_VANTAGE_API_KEY
    if not key:
        return _result("AlphaVantage", enabled=False, success=False, message="Optional ALPHA_VANTAGE_API_KEY is not configured.")
    query = urllib.parse.urlencode({"function": "TREASURY_YIELD", "interval": "daily", "maturity": "10year", "apikey": key})
    try:
        data = _get_json("https://www.alphavantage.co/query?" + query)
        ok = bool(data.get("data"))
        return _result("AlphaVantage", enabled=True, success=ok, message="Alpha Vantage macro API reachable." if ok else "Alpha Vantage returned no data.", data=data)
    except Exception as exc:
        return _result("AlphaVantage", enabled=True, success=False, message=f"Alpha Vantage check failed: {exc}")


def check_twelve_data() -> dict[str, Any]:
    key = free_data_settings.TWELVE_DATA_API_KEY
    if not key:
        return _result("TwelveData", enabled=False, success=False, message="Optional TWELVE_DATA_API_KEY is not configured.")
    query = urllib.parse.urlencode({"symbol": "XAU/USD", "apikey": key})
    try:
        data = _get_json("https://api.twelvedata.com/quote?" + query)
        ok = isinstance(data, dict) and not bool(data.get("code")) and bool(data.get("close") or data.get("price"))
        return _result(
            "TwelveData",
            enabled=True,
            success=ok,
            message="Twelve Data XAU/USD context quote reachable." if ok else str(data.get("message", "Twelve Data returned no quote.")),
            data=data,
        )
    except Exception as exc:
        return _result("TwelveData", enabled=True, success=False, message=f"Twelve Data check failed: {exc}")


def build_free_macro_health() -> dict[str, Any]:
    providers = [check_bls(), check_fred(), check_bea(), check_finnhub(), check_alpha_vantage(), check_twelve_data()]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "providers": providers,
        "enabled_count": sum(1 for item in providers if item["enabled"]),
        "success_count": sum(1 for item in providers if item["success"]),
        "note": "Context-only feeds. MT5 remains authoritative for executable prices.",
    }
    path = Path(free_data_settings.CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(path), payload, indent=2)
    return payload


def load_free_macro_cache() -> dict[str, Any]:
    """Load the optional cached macro context without making a network call."""
    path = Path(free_data_settings.CACHE_PATH)
    if not path.exists():
        return {
            "available": False,
            "path": str(path),
            "reason": "No free macro cache exists; run run_free_data_health_check.py.",
            "execution_price_authority": False,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "path": str(path),
            "reason": f"Free macro cache is unreadable: {exc}",
            "execution_price_authority": False,
        }
    return {
        "available": True,
        "path": str(path),
        "generated_at": payload.get("generated_at"),
        "enabled_count": payload.get("enabled_count", 0),
        "success_count": payload.get("success_count", 0),
        "providers": payload.get("providers", []),
        "execution_price_authority": False,
    }
