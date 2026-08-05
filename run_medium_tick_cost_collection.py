from __future__ import annotations

"""Collect recent broker tick spread/liquidity profiles in bounded chunks."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

from config import scalping_settings
from services.execution.mt5_connector import connect_mt5, disconnect_mt5


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect XAUUSD 15-minute tick cost profiles.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--symbol", default=scalping_settings.SCALPING_SYMBOL)
    parser.add_argument("--output-root", default=scalping_settings.SCALPING_MEDIUM_DATA_ROOT)
    args = parser.parse_args()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    rows = []
    daily = []
    if not connect_mt5():
        return 1
    try:
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=1), end)
            ticks = mt5.copy_ticks_range(args.symbol, cursor, chunk_end, mt5.COPY_TICKS_INFO)
            if ticks is None or len(ticks) == 0:
                daily.append({"date": cursor.date().isoformat(), "ticks": 0, "error": list(mt5.last_error())})
                cursor = chunk_end
                continue
            frame = pd.DataFrame(ticks)
            frame["time"] = pd.to_datetime(frame["time_msc"], unit="ms", utc=True)
            frame["spread"] = frame["ask"].astype(float) - frame["bid"].astype(float)
            frame = frame[(frame["bid"] > 0) & (frame["ask"] >= frame["bid"]) & (frame["spread"] < 10)]
            frame["bucket"] = frame["time"].dt.floor("15min")
            grouped = frame.groupby("bucket")["spread"]
            stats = grouped.agg(tick_count="count", spread_mean="mean", spread_median="median", spread_min="min", spread_max="max")
            stats["spread_p75"] = grouped.quantile(0.75)
            stats["spread_p90"] = grouped.quantile(0.90)
            rows.append(stats.reset_index())
            daily.append({"date": cursor.date().isoformat(), "ticks": int(len(frame)), "buckets": int(len(stats))})
            cursor = chunk_end
    finally:
        disconnect_mt5()

    if not rows:
        print(json.dumps({"status": "EMPTY", "daily": daily}, indent=2))
        return 1
    result = pd.concat(rows, ignore_index=True).drop_duplicates("bucket").sort_values("bucket")
    root = Path(args.output_root) / "tick_costs"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{args.symbol}_{start:%Y%m%d}_{end:%Y%m%d}_M15_costs.csv"
    result.to_csv(path, index=False)
    report = {
        "status": "OK", "symbol": args.symbol, "source": "MT5.copy_ticks_range(COPY_TICKS_INFO)",
        "from_utc": start.isoformat(), "to_utc": end.isoformat(),
        "buckets": int(len(result)), "ticks": int(sum(item.get("ticks", 0) for item in daily)),
        "spread_median_usd": round(float(result["spread_median"].median()), 6),
        "spread_p75_usd": round(float(result["spread_p75"].median()), 6),
        "spread_p90_usd": round(float(result["spread_p90"].median()), 6),
        "path": str(path), "daily": daily,
    }
    metadata = path.with_suffix(".json")
    metadata.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
