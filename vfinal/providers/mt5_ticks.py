from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pandas as pd


def collect_ticks(symbol: str, start: datetime, end: datetime, output: str | Path) -> dict:
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        return {"success": False, "error": f"MetaTrader5 package unavailable: {exc}"}
    if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
    if not mt5.initialize():
        return {"success": False, "error": f"MT5 initialize failed: {mt5.last_error()}"}
    try:
        rows = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
        if rows is None:
            return {"success": False, "error": f"MT5 tick query failed: {mt5.last_error()}"}
        frame = pd.DataFrame(rows)
        if frame.empty:
            return {"success": False, "error": "No ticks returned."}
        if "time_msc" in frame.columns:
            # time_msc is the authoritative clock.  Keep broker-native columns
            # untouched and emit one deterministic UTC representation.
            ts = pd.to_datetime(pd.to_numeric(frame["time_msc"], errors="coerce"), unit="ms", utc=True)
        else:
            ts = pd.to_datetime(pd.to_numeric(frame["time"], errors="coerce"), unit="s", utc=True)
        frame["timestamp"] = ts.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        target = Path(output); target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        return {"success": True, "rows": len(frame), "path": str(target), "symbol": symbol}
    finally:
        mt5.shutdown()
