from __future__ import annotations

import argparse
import json

from services.research.medium_m5_pattern_lab import search_m5_patterns, write_pattern_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Search transparent M5-path XAUUSD patterns.")
    parser.add_argument("dataset_folder")
    parser.add_argument("--fine-bars", required=True)
    parser.add_argument("--spread", type=float, default=0.26)
    parser.add_argument("--data-end", default="2026-04-09")
    parser.add_argument("--output", default="data/research/medium_horizon/m5_pattern_search.json")
    args = parser.parse_args()
    report = search_m5_patterns(
        args.dataset_folder, args.fine_bars, spread=args.spread, data_end=args.data_end
    )
    write_pattern_report(report, args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
