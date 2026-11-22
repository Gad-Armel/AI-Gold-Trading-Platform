from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from ..config import CACHE, FRED_API_KEY, FRED_BASE_URL, FRED_GRAPH_URL, FRED_SERIES, FRED_TIMEOUT, ensure_dirs


def _utc_timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "XAUUSD-VFINAL/1.1"})
    with urlopen(request, timeout=FRED_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_series(
    series_id: str,
    *,
    observation_start: str | None = None,
    observation_end: str | None = None,
    as_of: str | None = None,
) -> pd.DataFrame:
    """Fetch observations.

    When ``as_of`` is supplied, FRED's realtime_start/realtime_end filters are
    used. This is the critical distinction between a current revised series
    and a point-in-time vintage suitable for historical research.
    """
    if FRED_API_KEY:
        params: dict[str, str] = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
        }
        if observation_start:
            params["observation_start"] = observation_start
        if observation_end:
            params["observation_end"] = observation_end
        if as_of:
            day = _utc_timestamp(as_of).strftime("%Y-%m-%d")
            params["realtime_start"] = day
            params["realtime_end"] = day
        payload = _get_json(f"{FRED_BASE_URL}/series/observations?{urlencode(params)}")
        rows = payload.get("observations", [])
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        if "realtime_start" in frame:
            frame["realtime_start"] = pd.to_datetime(frame["realtime_start"], utc=True, errors="coerce")
        if "realtime_end" in frame:
            frame["realtime_end"] = pd.to_datetime(frame["realtime_end"], utc=True, errors="coerce")
        return frame.dropna(subset=["date", "value"])

    # Public fredgraph fallback has no authenticated vintage endpoint. It is
    # fine for current context, but explicitly marked unsafe for historical ML.
    params = {"id": series_id}
    if observation_start:
        params["cosd"] = observation_start
    if observation_end:
        params["coed"] = observation_end
    request = Request(f"{FRED_GRAPH_URL}?{urlencode(params)}", headers={"User-Agent": "XAUUSD-VFINAL/1.1"})
    with urlopen(request, timeout=FRED_TIMEOUT) as response:
        frame = pd.read_csv(response)
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame.date, utc=True, errors="coerce")
    frame["value"] = pd.to_numeric(frame.value, errors="coerce")
    return frame.dropna(subset=["date", "value"])


def fetch_vintage_snapshot(as_of: str) -> dict[str, dict]:
    """Return the latest known value for every configured series as of a date."""
    if not FRED_API_KEY:
        return {"_meta": {"available": False, "historical_training_safe": False, "reason": "FRED_API_KEY missing"}}
    result: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for name, sid in FRED_SERIES.items():
        try:
            frame = fetch_series(sid, as_of=as_of)
            if frame.empty:
                continue
            row = frame.sort_values("date").iloc[-1]
            item = {
                "series_id": sid,
                "observation_time": row["date"].isoformat(),
                "value": float(row["value"]),
                "vintage_as_of": _utc_timestamp(as_of).isoformat(),
            }
            result[name] = item
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
    result["_meta"] = {
        "available": bool(result and "_meta" not in result),
        "historical_training_safe": True,
        "as_of": _utc_timestamp(as_of).isoformat(),
        "errors": errors,
    }
    return result


def build_current_context() -> dict:
    observations = {}
    errors = {}
    for name, sid in FRED_SERIES.items():
        try:
            frame = fetch_series(sid).tail(30)
            if frame.empty:
                continue
            latest = frame.iloc[-1]
            value = float(latest.value)
            item = {"series_id": sid, "value": value, "observation_time": latest.date.isoformat()}
            for n in (1, 5, 20):
                if len(frame) > n:
                    item[f"change_{n}"] = value - float(frame.iloc[-1 - n].value)
            observations[name] = item
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
    usd = float(observations.get("usd_broad", {}).get("change_5", 0.0))
    real = float(observations.get("us10y_real", {}).get("change_5", 0.0))
    nominal = float(observations.get("us10y", {}).get("change_5", 0.0))
    vix = float(observations.get("vix", {}).get("change_5", 0.0))
    pressure = (-1 if usd > 0 else 1 if usd < 0 else 0) + (1 if real < 0 else -1 if real > 0 else 0) + (-0.25 if nominal > 0 else 0.25 if nominal < 0 else 0) + (0.15 if vix > 0 else -0.15 if vix < 0 else 0)
    result = {
        "available": bool(observations),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "FRED",
        "historical_training_safe": False,
        "historical_training_note": "Current values are revised data. Use fetch_vintage_snapshot(as_of=...) for point-in-time historical ML.",
        "observations": observations,
        "errors": errors,
        "gold_bias": "BUY" if pressure >= 1 else "SELL" if pressure <= -1 else "NEUTRAL",
        "gold_pressure_raw": pressure,
    }
    ensure_dirs()
    (CACHE / "fred_context.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result
