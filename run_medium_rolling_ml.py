from __future__ import annotations

import argparse
import json

from services.research.medium_rolling_ml import run_rolling_ml, write_rolling_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run monthly rolling medium ML validation.")
    parser.add_argument("dataset_folder")
    parser.add_argument("--spread", type=float, default=0.30)
    parser.add_argument("--stop", type=float, default=3.0)
    parser.add_argument("--max-bars", type=int, default=32)
    parser.add_argument("--intermarket-folder", default="")
    parser.add_argument("--macro-folder", default="")
    parser.add_argument("--fine-bars", default="")
    parser.add_argument("--calibration-days", type=int, default=30)
    parser.add_argument("--training-days", type=int, default=240)
    parser.add_argument("--data-end", default="")
    parser.add_argument("--development-only", action="store_true")
    parser.add_argument("--output", default="data/research/medium_horizon/rolling_ml.json")
    args = parser.parse_args()
    report = run_rolling_ml(
        args.dataset_folder, spread=args.spread, stop=args.stop, max_bars=args.max_bars,
        intermarket_folder=args.intermarket_folder or None,
        macro_folder=args.macro_folder or None,
        fine_bars_path=args.fine_bars or None,
        calibration_days=args.calibration_days,
        training_days=args.training_days,
        data_end=args.data_end or None,
        development_only=args.development_only,
    )
    write_rolling_report(report, args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
