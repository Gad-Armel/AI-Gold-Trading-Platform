from __future__ import annotations

"""Twelve Data XAU/USD OHLC adapter. No broker or execution dependency."""

import json
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from models.scalping_state import ScalpingSnapshotState

INTERVALS = {"M1": "1min", "M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h"}


class TwelveDataError(RuntimeError):
    pass


def _default_get(url: str, timeout: float) -> dict:
    with urlopen(url, timeout=timeout) as response:  # nosec B310 - fixed HTTPS host
        return json.loads(response.read().decode("utf-8"))


def _frame(payload: dict, timeframe: str) -> pd.DataFrame:
    if payload.get("status") == "error" or not isinstance(payload.get("values"), list):
        raise TwelveDataError(str(payload.get("message") or f"invalid {timeframe} response"))
    frame = pd.DataFrame(payload["values"])
    required = {"datetime", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise TwelveDataError(f"{timeframe} response is missing OHLC fields")
    frame = frame.rename(columns={"datetime": "time", "volume": "tick_volume"})
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "tick_volume" not in frame:
        frame["tick_volume"] = 1.0
    frame["tick_volume"] = pd.to_numeric(frame["tick_volume"], errors="coerce").fillna(1.0)
    frame = frame.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)
    if len(frame) < 56:
        raise TwelveDataError(f"{timeframe} has only {len(frame)}/56 required bars")
    return frame


def fetch_twelve_data_snapshot(api_key: str, *, symbol: str = "XAU/USD", outputsize: int = 150,
                               timeout: float = 8.0, getter: Callable[[str, float], dict] = _default_get) -> ScalpingSnapshotState:
    if not api_key.strip():
        raise TwelveDataError("TWELVE_DATA_API_KEY is missing. Add it to the project .env file.")
    frames: dict[str, pd.DataFrame] = {}
    for timeframe, interval in INTERVALS.items():
        query = urlencode({"symbol": symbol, "interval": interval, "outputsize": max(56, outputsize), "timezone": "UTC", "apikey": api_key})
        try:
            payload = getter(f"https://api.twelvedata.com/time_series?{query}", timeout)
        except TwelveDataError:
            raise
        except Exception as error:
            raise TwelveDataError(f"{timeframe} request failed: {type(error).__name__}: {error}") from error
        frames[timeframe] = _frame(payload, timeframe)
    now = datetime.now(timezone.utc)
    last = float(frames["M1"].iloc[-1]["close"])
    hour = now.hour
    session = "Asian" if hour < 7 else "London" if hour < 13 else "New York" if hour < 21 else "Asian"
    return ScalpingSnapshotState(symbol=symbol, timestamp=now, bid=last, ask=last, spread=0.0, mid=last,
        session=session, active_sessions=[session], candles=frames, point=0.01, quote_age_seconds=0.0,
        system_timestamp=now, market_clock_source="TWELVE_DATA_UTC")
