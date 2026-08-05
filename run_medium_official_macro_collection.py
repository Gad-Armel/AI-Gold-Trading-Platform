from __future__ import annotations

"""Collect public daily macro series from official FRED graph CSV endpoints."""

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import scalping_settings


SERIES = {
    "dgs10": "DGS10",
    "broad_usd": "DTWEXBGS",
    "vix": "VIXCLS",
    "fed_funds": "DFF",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect official daily macro context from FRED.")
    parser.add_argument("--start", default="2024-07-01")
    parser.add_argument("--output-root", default=scalping_settings.SCALPING_MEDIUM_DATA_ROOT)
    args = parser.parse_args()
    root = Path(args.output_root) / "official_macro"
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "source": "Federal Reserve Bank of St. Louis FRED graph CSV",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "observation_start": args.start,
        "current_vintage_warning": "Values are current-vintage; model availability is lagged two calendar days and promotion still requires forward shadow validation.",
        "files": {},
    }
    for role, series_id in SERIES.items():
        query = urllib.parse.urlencode({"id": series_id, "cosd": args.start})
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}"
        target = root / f"{series_id}.csv"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read()
            target.write_bytes(content)
            frame = pd.read_csv(target)
            value_column = frame.columns[-1]
            values = pd.to_numeric(frame[value_column], errors="coerce")
            report["files"][role] = {
                "status": "OK", "series_id": series_id, "url": url, "path": str(target),
                "rows": int(len(frame)), "valid_values": int(values.notna().sum()),
                "first_date": str(frame.iloc[0, 0]), "last_date": str(frame.iloc[-1, 0]),
            }
        except Exception as error:
            report["files"][role] = {"status": "ERROR", "series_id": series_id, "url": url, "error": f"{type(error).__name__}: {error}"}
    metadata = root / "metadata.json"
    metadata.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(item["status"] == "OK" for item in report["files"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
