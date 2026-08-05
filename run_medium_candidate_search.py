from __future__ import annotations

import argparse
import json

from services.research.medium_candidate_lab import search_candidates, write_search_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Search medium candidates without opening the final holdout.")
    parser.add_argument("dataset_folder")
    parser.add_argument("--spread", type=float, default=0.30)
    parser.add_argument("--output", default="data/research/medium_horizon/candidate_search.json")
    args = parser.parse_args()
    report = search_candidates(args.dataset_folder, spread=args.spread)
    write_search_report(report, args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
