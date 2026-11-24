"""Export existing, immutable Advisor 1 reports for causal native MT5 replay.

No advisor logic is imported or modified; only transport fields are retained.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fields(report: dict) -> list[str]:
    scalp = report["horizons"]["SCALP"]
    generated = datetime.fromisoformat(report["generated_at"])
    valid = datetime.fromisoformat(scalp["valid_until"])
    if generated.tzinfo is None or valid.tzinfo is None:
        raise ValueError("naive report timestamp")
    symbol, action, bias = report["symbol"], scalp["action"], scalp["bias"]
    score, bid, ask = (float(scalp["directional_score"]), float(report["bid"]), float(report["ask"]))
    if (not symbol.startswith("XAUUSD") or any(c in symbol for c in ';\r\n')
            or action not in {"BUY", "SELL", "WAIT"} or bias not in {"BUY", "SELL", "WAIT"}
            or not all(math.isfinite(v) for v in (score, bid, ask))
            or not 0 <= score <= 100 or bid <= 0 or ask < bid or valid <= generated):
        raise ValueError("invalid report fields")
    return ["GOLD_ADVISOR1_V1", str(int(generated.timestamp())), str(int(valid.timestamp())),
            symbol, action, bias, str(score), str(bid), str(ask), "SCALP", "END"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/research/gold_advisory_history.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "mql5/validation/advisor1_replay.csv")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise SystemExit("Input history must never be overwritten")
    rows: list[list[str]] = []
    rejected = 0
    with args.input.open(encoding="utf-8-sig") as source:
        for line in source:
            try:
                rows.append(fields(json.loads(line)))
            except (ValueError, KeyError, TypeError, OverflowError):
                rejected += 1
    rows.sort(key=lambda row: int(row[1]))  # stable ordering for reports sharing a timestamp
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as destination:
        csv.writer(destination, delimiter=";", lineterminator="\r\n").writerows(rows)
    temporary.replace(args.output)
    print(json.dumps({"reports": len(rows), "rejected": rejected, "output": str(args.output),
                      "first_utc_epoch": rows[0][1] if rows else None,
                      "last_utc_epoch": rows[-1][1] if rows else None}))


if __name__ == "__main__":
    main()
