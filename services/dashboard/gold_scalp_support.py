"""Transport the protected Advisor 1 report; optionally supervise its unchanged runner."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "data/runtime/gold_advisory.json"


def advisor_line(report: dict) -> tuple[str, float]:
    scalp = report["horizons"]["SCALP"]
    generated = datetime.fromisoformat(report["generated_at"])
    valid = datetime.fromisoformat(scalp["valid_until"])
    if generated.tzinfo is None or valid.tzinfo is None or valid <= generated:
        raise ValueError("Advisor timestamps must be timezone-aware and ordered")
    symbol, action, bias = report["symbol"], scalp["action"], scalp["bias"]
    if not re.fullmatch(r"XAUUSD[A-Za-z0-9_.-]*", symbol) or action not in {"BUY", "SELL", "WAIT"} or bias not in {"BUY", "SELL", "WAIT"}:
        raise ValueError("Unexpected Advisor 1 report schema")
    score, bid, ask = (float(scalp["directional_score"]), float(report["bid"]), float(report["ask"]))
    if not all(math.isfinite(x) for x in (score, bid, ask)) or not 0 <= score <= 100 or bid <= 0 or ask < bid:
        raise ValueError("Invalid Advisor 1 numbers")
    fields = ["GOLD_ADVISOR1_V1", str(int(generated.timestamp())), str(int(valid.timestamp())), symbol, action, bias,
              repr(score), repr(bid), repr(ask), "SCALP", "END"]
    return ";".join(fields) + "\r\n", generated.timestamp()


def publish_advisor(report_path: Path, directory: Path) -> float:
    """Keep the original generated/expiry timestamps, even when the report is old."""
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    line, generated = advisor_line(report)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "advisor1.csv"
    try:
        if target.read_bytes() == line.encode("utf-8"):
            return generated
    except FileNotFoundError:
        pass
    temporary = directory / f"advisor1.dashboard.{os.getpid()}.tmp"
    try:
        temporary.write_bytes(line.encode("utf-8"))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return generated


class AdvisorSupport:
    def __init__(self, directory: Path, with_advisor: bool = False):
        self.directory = directory
        self.with_advisor = with_advisor
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="advisor-report-bridge", daemon=True)
        self.child: subprocess.Popen | None = None
        self.log = None
        self.next_start = 0.0
        self.health = {"advisor": "Starting report bridge", "report_age_seconds": None}

    def start(self) -> None:
        self.thread.start()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                generated = publish_advisor(REPORT, self.directory)
                age = time.time() - generated
                self.health = {"advisor": "Report bridge OK" if -2 <= age <= 90 else "Advisor report is stale or future-dated",
                               "report_age_seconds": round(age, 1)}
            except (OSError, ValueError, KeyError, TypeError) as error:
                age = math.inf
                self.health = {"advisor": f"Report bridge: {error}", "report_age_seconds": None}
            if self.with_advisor and age > 45 and time.monotonic() >= self.next_start and (self.child is None or self.child.poll() is not None):
                # Do not cause mt5.initialize() to reopen a terminal the user closed.
                from .gold_scalp_web import read_status
                state = read_status(self.directory)
                if state["state"] == "live":
                    self.next_start = time.monotonic() + 60
                    try:
                        if self.log is None:
                            log_path = ROOT / "data/runtime/advisor1-dashboard.log"
                            log_path.parent.mkdir(parents=True, exist_ok=True)
                            self.log = log_path.open("ab", buffering=0)
                        # Advisor 1's existing lock prevents a duplicate runner. No protected code is changed.
                        self.child = subprocess.Popen([sys.executable, "-B", "-u", str(ROOT / "run_gold_advisor.py")],
                                                      cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT,
                                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    except OSError as error:
                        self.health = {"advisor": f"Advisor launch failed: {error}", "report_age_seconds": None}
            self.stop_event.wait(2)

    def stop(self) -> None:
        self.stop_event.set(); self.thread.join(timeout=5)
        # Only the read-only child created by this dashboard is ours to stop.
        if self.child is not None and self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.child.kill(); self.child.wait(timeout=5)
        if self.log is not None:
            self.log.close()
