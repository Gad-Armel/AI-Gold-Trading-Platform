from __future__ import annotations

import argparse
import json

from services.research.medium_ml_challenger import run_ml_challenger, write_ml_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the sealed-holdout medium ML challenger.")
    parser.add_argument("dataset_folder")
    parser.add_argument("--spread", type=float, default=0.30)
    parser.add_argument("--stop", type=float, default=1.80)
    parser.add_argument("--max-bars", type=int, default=16)
    parser.add_argument("--intermarket-folder", default="")
    parser.add_argument("--macro-folder", default="")
    parser.add_argument("--fine-bars", default="")
    parser.add_argument("--output", default="data/research/medium_horizon/ml_challenger.json")
    args = parser.parse_args()
    report = run_ml_challenger(
        args.dataset_folder,
        spread=args.spread,
        stop=args.stop,
        max_bars=args.max_bars,
        intermarket_folder=args.intermarket_folder or None,
        macro_folder=args.macro_folder or None,
        fine_bars_path=args.fine_bars or None,
    )
    write_ml_report(report, args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
