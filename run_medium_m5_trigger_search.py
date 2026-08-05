from __future__ import annotations

import argparse
import json

from services.research.medium_m5_trigger_lab import search_m5_triggers, write_m5_trigger_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Search M5 triggers inside completed HTF regimes.")
    parser.add_argument("dataset_folder")
    parser.add_argument("--development-end", default="2026-04-09")
    parser.add_argument("--spread", type=float, default=0.26)
    parser.add_argument("--output", default="data/research/medium_horizon/m5_trigger_search.json")
    args = parser.parse_args()
    report = search_m5_triggers(
        args.dataset_folder, development_end=args.development_end, spread=args.spread
    )
    write_m5_trigger_report(report, args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
