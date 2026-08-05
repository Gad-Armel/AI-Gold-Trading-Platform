from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from config import scalping_settings
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.research.medium_forward_dataset import collect_forward_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Append closed M1 bars and quote costs to untouched forward data.")
    parser.add_argument("--symbol", default=scalping_settings.SCALPING_SYMBOL)
    parser.add_argument(
        "--anchor",
        help="UTC cohort start. Only valid when initializing; defaults to the current time.",
    )
    parser.add_argument("--root", default="data/research/medium_horizon/forward")
    args = parser.parse_args()
    cohort_path = Path(args.root) / args.symbol / "cohort.json"
    cohort_path.parent.mkdir(parents=True, exist_ok=True)
    requested = datetime.fromisoformat(args.anchor.replace("Z", "+00:00")) if args.anchor else None
    if requested is not None and requested.tzinfo is None:
        parser.error("--anchor must contain a UTC offset.")
    if cohort_path.exists():
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        anchor = datetime.fromisoformat(cohort["anchor_utc"])
        if requested is not None and requested.astimezone(timezone.utc) != anchor.astimezone(timezone.utc):
            parser.error("This forward cohort already has a different immutable anchor.")
    else:
        anchor = (requested or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cohort_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "anchor_utc": anchor.isoformat(),
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "rule": "No observations before this timestamp may enter this forward cohort.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    if not connect_mt5():
        return 1
    try:
        report = collect_forward_batch(
            args.symbol,
            root=args.root,
            anchor_utc=anchor.astimezone(timezone.utc),
        )
        print(json.dumps(report, indent=2))
        return 0
    finally:
        disconnect_mt5()


if __name__ == "__main__":
    raise SystemExit(main())
