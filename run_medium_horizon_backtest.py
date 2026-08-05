from __future__ import annotations

import argparse
import json

from services.research.medium_horizon_backtest import run_medium_horizon_backtest, save_backtest_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a conservative medium-horizon historical screen.")
    parser.add_argument("dataset_folder")
    parser.add_argument("--spread", type=float, default=0.30)
    parser.add_argument("--output", default="data/research/medium_horizon/latest_backtest.json")
    args = parser.parse_args()
    if args.spread <= 0:
        parser.error("--spread must be positive")
    report = run_medium_horizon_backtest(args.dataset_folder, assumed_spread_usd=args.spread)
    save_backtest_report(report, args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
