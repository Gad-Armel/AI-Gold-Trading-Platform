from __future__ import annotations

"""Download reproducible broker-native candles for medium-model research."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import MetaTrader5 as mt5
import pandas as pd

from config import scalping_settings

_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
}


def collect_medium_horizon_dataset(
    symbol: str,
    date_from: datetime,
    date_to: datetime,
    *,
    output_root: str | None = None,
) -> dict[str, Any]:
    if date_from.tzinfo is None or date_to.tzinfo is None:
        raise ValueError("date_from and date_to must be timezone-aware UTC datetimes.")
    start = date_from.astimezone(timezone.utc)
    end = date_to.astimezone(timezone.utc)
    if start >= end:
        raise ValueError("date_from must precede date_to.")

    root = Path(output_root or scalping_settings.SCALPING_MEDIUM_DATA_ROOT)
    stamp = f"{start:%Y%m%d}_{end:%Y%m%d}"
    folder = root / symbol / stamp
    folder.mkdir(parents=True, exist_ok=True)
    files: dict[str, Any] = {}
    for name, timeframe in _TIMEFRAMES.items():
        missing_chunks: list[dict[str, Any]] = []
        if name in {"M1", "M5"}:
            chunks = []
            cursor = start
            while cursor < end:
                chunk_days = 30 if name == "M1" else 90
                chunk_end = min(cursor + timedelta(days=chunk_days), end)
                item = mt5.copy_rates_range(symbol, timeframe, cursor, chunk_end)
                if item is None or len(item) == 0:
                    missing_chunks.append({
                        "from_utc": cursor.isoformat(),
                        "to_utc": chunk_end.isoformat(),
                        "mt5_error": list(mt5.last_error()),
                    })
                else:
                    chunks.append(pd.DataFrame(item))
                cursor = chunk_end
            rates = pd.concat(chunks, ignore_index=True).to_records(index=False) if chunks else None
        else:
            rates = mt5.copy_rates_range(symbol, timeframe, start, end)
        if rates is None or len(rates) == 0:
            files[name] = {"status": "EMPTY", "rows": 0, "mt5_error": list(mt5.last_error())}
            continue
        frame = pd.DataFrame(rates)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        frame = frame.drop_duplicates("time").sort_values("time")
        path = folder / f"{symbol}_{name}.csv"
        frame.to_csv(path, index=False)
        files[name] = {
            "status": "OK",
            "rows": int(len(frame)),
            "path": str(path),
            "first_utc": frame.iloc[0]["time"].isoformat(),
            "last_utc": frame.iloc[-1]["time"].isoformat(),
            "missing_chunks": missing_chunks,
        }

    metadata = {
        "schema_version": 1,
        "symbol": symbol,
        "requested_from_utc": start.isoformat(),
        "requested_to_utc": end.isoformat(),
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "MetaTrader5.copy_rates_range",
        "strategy_id": scalping_settings.SCALPING_MEDIUM_STRATEGY_ID,
        "files": files,
        "warning": "Broker bars do not contain historical executable bid/ask spread; do not report cost-free results.",
    }
    metadata_path = folder / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata
