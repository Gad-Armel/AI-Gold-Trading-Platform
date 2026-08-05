from __future__ import annotations

"""Collect verified broker-native intermarket H1 histories."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

from config import scalping_settings
from services.execution.mt5_connector import connect_mt5, disconnect_mt5


SYMBOLS = {
    "silver": "XAGUSD",
    "eurusd": "EURUSD",
    "gbpusd": "GBPUSD",
    "usdjpy": "USDJPY",
    "usdchf": "USDCHF",
    "sp500": "US500",
    "nasdaq": "USTEC",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect verified H1 intermarket histories.")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--output-root", default=scalping_settings.SCALPING_MEDIUM_DATA_ROOT)
    args = parser.parse_args()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    root = Path(args.output_root) / "intermarket" / f"{start:%Y%m%d}_{end:%Y%m%d}"
    root.mkdir(parents=True, exist_ok=True)
    if not connect_mt5():
        return 1
    try:
        report = {"from_utc": start.isoformat(), "to_utc": end.isoformat(), "source": "MT5", "files": {}}
        for role, symbol in SYMBOLS.items():
            info = mt5.symbol_info(symbol)
            description = str(getattr(info, "description", "") or "") if info else ""
            path = str(getattr(info, "path", "") or "") if info else ""
            mt5.symbol_select(symbol, True)
            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start, end)
            if rates is None or len(rates) == 0:
                report["files"][role] = {"status": "EMPTY", "symbol": symbol, "error": list(mt5.last_error())}
                continue
            frame = pd.DataFrame(rates)
            frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
            frame = frame.drop_duplicates("time").sort_values("time")
            target = root / f"{role}_{symbol}_H1.csv"
            frame.to_csv(target, index=False)
            report["files"][role] = {
                "status": "OK", "symbol": symbol, "description": description, "broker_path": path,
                "rows": int(len(frame)), "path": str(target),
                "first_utc": frame.iloc[0]["time"].isoformat(), "last_utc": frame.iloc[-1]["time"].isoformat(),
            }
        metadata = root / "metadata.json"
        metadata.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["metadata_path"] = str(metadata)
        print(json.dumps(report, indent=2))
        return 0 if all(item["status"] == "OK" for item in report["files"].values()) else 1
    finally:
        disconnect_mt5()


if __name__ == "__main__":
    raise SystemExit(main())
