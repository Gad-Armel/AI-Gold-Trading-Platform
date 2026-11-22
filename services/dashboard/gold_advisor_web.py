"""Read-only presentation of the protected Advisor 1 report. No signal calculation."""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import time

REPORT = Path(__file__).resolve().parents[2] / "data/runtime/gold_advisory.json"
HORIZONS = ("SCALP", "INTRADAY", "SWING")


def epoch(value: object) -> float:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Report timestamps must include a timezone")
    return parsed.timestamp()


def number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Invalid report number")
    return float(value)


def read_advisor(path: Path = REPORT, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    result = dict(state="waiting", message="Waiting for Advisor 1. Keep MT5 and the dashboard with --with-advisor running.",
                  report=None, age_seconds=None, server_time=now)
    try:
        with path.open("rb") as handle:
            data = handle.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("Advisor report exceeds the size limit")
        report = json.loads(data.decode("utf-8-sig"))
        # Also rejects non-finite numbers in optional context fields.
        json.dumps(report, allow_nan=False)
        if not isinstance(report, dict) or report.get("overall") not in ("BUY", "SELL", "WAIT"):
            raise ValueError("Invalid Advisor 1 decision")
        if not isinstance(report.get("symbol"), str) or not report["symbol"].startswith("XAUUSD"):
            raise ValueError("Expected an XAUUSD report")
        generated = epoch(report["generated_at"])
        if number(report["bid"]) <= 0 or number(report["ask"]) < report["bid"] or number(report["spread"]) < 0:
            raise ValueError("Invalid market quote")
        for name in HORIZONS:
            item = report["horizons"][name]
            if item["action"] not in ("BUY", "SELL", "WAIT") or item["bias"] not in ("BUY", "SELL", "WAIT"):
                raise ValueError("Invalid horizon action or bias")
            if not 0 <= number(item["directional_score"]) <= 100 or number(item["valid_for_minutes"]) <= 0:
                raise ValueError("Invalid horizon evidence or duration")
            if not generated < epoch(item["review_at"]) <= epoch(item["valid_until"]):
                raise ValueError("Invalid horizon timestamps")
            for key in ("reasons", "blocks"):
                if not isinstance(item[key], list) or any(not isinstance(x, str) for x in item[key]):
                    raise ValueError("Invalid horizon explanations")
            if item["action"] in ("BUY", "SELL"):
                levels = item["levels"]
                if len(levels["entry_zone"]) != 2:
                    raise ValueError("Invalid entry zone")
                for value in [*levels["entry_zone"], levels["sl"], levels["tp1"], levels["tp2"], levels["tp3"]]:
                    if number(value) <= 0:
                        raise ValueError("Invalid advisory price level")
        age = now - generated
        result.update(report=report, age_seconds=round(max(age, 0), 1))
        if age < -5:
            result.update(state="stale", message="Report is future-dated. Check the computer clock; this is not a current signal.")
        elif age > 90:
            result.update(state="stale", message="Advisor 1 has not refreshed for over 90 seconds. Last analysis only; do not treat it as a live entry signal.")
        else:
            result.update(state="live", message="Advisor 1 report is fresh. Analysis only; the main bot applies its own entry and risk checks.")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        result.update(state="error", message=f"Cannot read Advisor 1 report: {error}")
    return result
