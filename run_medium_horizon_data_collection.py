from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from config import scalping_settings
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.research.medium_horizon_dataset import collect_medium_horizon_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect broker-native candles for medium-horizon research.")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--symbol", default=scalping_settings.SCALPING_SYMBOL)
    args = parser.parse_args()
    if args.days < 30:
        parser.error("--days must be at least 30")
    if not connect_mt5():
        return 1
    try:
        end = datetime.now(timezone.utc)
        report = collect_medium_horizon_dataset(
            args.symbol,
            end - timedelta(days=args.days),
            end,
        )
        print(json.dumps(report, indent=2))
        return 0 if all(item["status"] == "OK" for item in report["files"].values()) else 1
    finally:
        disconnect_mt5()


if __name__ == "__main__":
    raise SystemExit(main())
