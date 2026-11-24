"""Run a read-only, two-model XAUUSD scalp advisor for manual review."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from typing import Any

from config import gold_consensus_settings as settings
from config import scalping_settings
from services.bot.scalping_instance_lock import ScalpingInstanceAlreadyRunning, ScalpingInstanceLock
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.research.gold_advisory import build_gold_advisory
from services.research.gold_advisory_v3 import build_gold_advisory_v3
from services.research.gold_manual_scalp_advisor import build_manual_scalp_advisory
from services.research.gold_tick_history import TickHistoryBuffer
from services.utils.atomic_json import atomic_write_json


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Generate one read-only report and exit.")
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--max-minutes", type=float, default=0.0, help="0 runs until CTRL+C.")
    parser.add_argument("--output", type=Path, default=Path("data/runtime/gold_manual_scalp_advisory.json"))
    parser.add_argument(
        "--history",
        type=Path,
        default=Path("data/research/gold_manual_scalp_advisory_history.jsonl"),
    )
    args = parser.parse_args()
    if not math.isfinite(args.interval_seconds) or args.interval_seconds < 0.5:
        parser.error("--interval-seconds must be at least 0.5.")
    if not math.isfinite(args.max_minutes) or args.max_minutes < 0:
        parser.error("--max-minutes cannot be negative.")
    return args


def _print_report(report: dict[str, Any]) -> None:
    quote = report["quote"]
    print(
        f"{report['generated_at']} | {report['symbol']} | {report['action']} "
        f"| score {report['directional_evidence_score']:.1f}/100 "
        f"| bid {quote['bid']:.2f} ask {quote['ask']:.2f} spread {quote['spread']:.3f}"
    )
    print(f"Valid until: {report['valid_until']} | orders sent: {report['orders_sent']}")
    if report["action"] in {"BUY", "SELL"}:
        levels = report["scenario_levels"]
        zone = levels["entry_zone"]
        print(
            f"Scenario only: entry zone {zone[0]:.2f}-{zone[1]:.2f} | "
            f"SL {levels['sl']:.2f} | TP1 {levels['tp1']:.2f} "
            f"TP2 {levels['tp2']:.2f} TP3 {levels['tp3']:.2f} "
            f"| R:R to TP1 {report['scenario_reward_to_risk']:.2f}"
        )
    for reason in report["blocks"]:
        print(f"WAIT: {reason}")
    print(report["disclaimer"])


def _append_history(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    args = _arguments()
    lock = ScalpingInstanceLock("data/runtime/gold_manual_scalp_advisor.lock")
    try:
        lock.acquire()
    except ScalpingInstanceAlreadyRunning as error:
        print(f"Manual scalp advisor startup blocked: {error}")
        return 1

    try:
        if not connect_mt5():
            raise RuntimeError("MT5 initialization failed; cannot produce a current scalp advisory.")
        import MetaTrader5 as mt5

        history = TickHistoryBuffer()
        started = time.monotonic()
        last_signature = ""
        last_history_at = 0.0
        while args.max_minutes <= 0 or time.monotonic() - started < args.max_minutes * 60:
            cycle_started = time.monotonic()
            snapshot = get_scalping_snapshot(scalping_settings.SCALPING_SYMBOL)
            candle_report = build_gold_advisory(snapshot)
            tick_now = datetime.now(timezone.utc)
            tick_report = build_gold_advisory_v3(
                mt5,
                settings.SYMBOL,
                now=tick_now,
                history=history,
            )
            now = datetime.now(timezone.utc)
            report = build_manual_scalp_advisory(candle_report, tick_report, now=now)
            atomic_write_json(str(args.output), report, indent=2)
            signature = json.dumps(
                {
                    "action": report["action"],
                    "bias": report["bias"],
                    "blocks": report["blocks"],
                },
                sort_keys=True,
            )
            if signature != last_signature or time.monotonic() - last_history_at >= 15.0:
                _append_history(args.history, report)
                _print_report(report)
                last_signature = signature
                last_history_at = time.monotonic()
            if args.once:
                break
            time.sleep(max(0.0, args.interval_seconds - (time.monotonic() - cycle_started)))
        return 0
    except KeyboardInterrupt:
        print("Manual scalp advisor stopped with CTRL+C.")
        return 0
    finally:
        disconnect_mt5()
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
