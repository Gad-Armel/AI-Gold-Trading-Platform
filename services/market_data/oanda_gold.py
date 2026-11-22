from __future__ import annotations

"""Read-only OANDA XAU/USD candle adapter with automatic account discovery."""

import json
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from models.scalping_state import ScalpingSnapshotState

GRANULARITIES = {"M1": "M1", "M5": "M5", "M15": "M15", "H1": "H1", "H4": "H4"}


class OandaDataError(RuntimeError):
    pass


def _base_url(environment: str) -> str:
    return "https://api-fxtrade.oanda.com" if environment.strip().lower() in {"live", "fxtrade"} else "https://api-fxpractice.oanda.com"


def _candidate_base_urls(environment: str) -> list[str]:
    preferred = _base_url(environment)
    alternate = "https://api-fxpractice.oanda.com" if "fxtrade.oanda.com" in preferred else "https://api-fxtrade.oanda.com"
    return [preferred, alternate]


def _default_get(url: str, token: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed official HTTPS hosts
        return json.loads(response.read().decode("utf-8"))


def _account_id(base: str, token: str, timeout: float, getter: Callable[[str, str, float], dict[str, Any]]) -> str:
    payload = getter(f"{base}/v3/accounts", token, timeout)
    accounts = payload.get("accounts", [])
    if not accounts or not str(accounts[0].get("id", "")).strip():
        raise OandaDataError("OANDA token returned no accessible accounts.")
    return str(accounts[0]["id"]).strip()


def _frame(payload: dict[str, Any], timeframe: str) -> pd.DataFrame:
    rows = []
    for candle in payload.get("candles", []) if isinstance(payload.get("candles"), list) else []:
        mid = candle.get("mid", {})
        rows.append({"time": candle.get("time"), "open": mid.get("o"), "high": mid.get("h"),
                     "low": mid.get("l"), "close": mid.get("c"), "tick_volume": candle.get("volume", 1)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise OandaDataError(f"OANDA {timeframe} returned no candles.")
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close", "tick_volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)
    if len(frame) < 56:
        raise OandaDataError(f"OANDA {timeframe} has only {len(frame)}/56 required candles.")
    return frame


def fetch_oanda_gold_snapshot(token: str, *, environment: str = "practice", timeout: float = 8.0,
                              getter: Callable[[str, str, float], dict[str, Any]] = _default_get) -> ScalpingSnapshotState:
    if not token.strip():
        raise OandaDataError("OANDA_API_TOKEN is missing.")
    try:
        base = ""
        account = ""
        authentication_errors: list[str] = []
        for candidate in _candidate_base_urls(environment):
            try:
                account = _account_id(candidate, token, timeout, getter)
                base = candidate
                break
            except Exception as error:
                authentication_errors.append(f"{candidate.split('//', 1)[-1]}: {type(error).__name__}")
        if not base or not account:
            raise OandaDataError(
                "OANDA token was rejected by both practice and live environments ("
                + ", ".join(authentication_errors) + ")."
            )
        frames = {}
        for timeframe, granularity in GRANULARITIES.items():
            query = urlencode({"price": "M", "granularity": granularity, "count": 150})
            payload = getter(f"{base}/v3/accounts/{account}/instruments/XAU_USD/candles?{query}", token, timeout)
            frames[timeframe] = _frame(payload, timeframe)
    except OandaDataError:
        raise
    except Exception as error:
        raise OandaDataError(f"OANDA candle refresh failed: {type(error).__name__}: {error}") from error
    now = datetime.now(timezone.utc)
    last = float(frames["M1"].iloc[-1]["close"])
    hour = now.hour
    session = "Asian" if hour < 7 else "London" if hour < 13 else "New York" if hour < 21 else "Asian"
    return ScalpingSnapshotState(symbol="XAU/USD", timestamp=now, bid=last, ask=last, spread=0.0, mid=last,
        session=session, active_sessions=[session], candles=frames, point=0.01, quote_age_seconds=0.0,
        system_timestamp=now, market_clock_source="OANDA_V20")
