from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from config import scalping_settings
from services.bot.scalping_instance_lock import ScalpingInstanceAlreadyRunning, ScalpingInstanceLock
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.research.gold_advisory import build_gold_advisory
from services.utils.atomic_json import atomic_write_json


def _print(report: dict) -> None:
    width = 118
    overall = str(report["overall"])
    instruction = (
        "BUY SETUP AVAILABLE"
        if overall == "BUY"
        else "SELL SETUP AVAILABLE"
        if overall == "SELL"
        else "WAIT - NO ENTRY"
    )
    print("\n" + "=" * width)
    print("GOLD MARKET ADVISOR".center(width))
    print("=" * width)
    analyzed_at = str(report["generated_at"])
    analyzed_clock = analyzed_at[11:19]
    print(f"Analysis completed (UTC) : {analyzed_at}")
    print(
        f"Market     : {report['symbol']} | Bid {report['bid']:.2f} | "
        f"Ask {report['ask']:.2f} | Spread ${report['spread']:.2f} | "
        f"Session {report['session']}"
    )
    print(f"DECISION   : {instruction}")
    print("-" * width)
    print(
        f"{'HORIZON':<12}{'ACTION':<12}{'BIAS':<10}{'EVIDENCE':<14}"
        f"{'VALID FOR':<12}{'VALID WINDOW (UTC)':<25}{'NEXT REVIEW (UTC)'}"
    )
    print("-" * width)
    for name in ("SCALP", "INTRADAY", "SWING"):
        item = report["horizons"][name]
        review = str(item["review_at"])[11:19]
        expires = str(item["valid_until"])[11:19]
        valid_window = f"{analyzed_clock} -> {expires}"
        print(
            f"{name:<12}{item['action']:<12}{item['bias']:<10}"
            f"{item['directional_score']:>6.1f}/100   "
            f"{str(item['valid_for_minutes']) + ' min':<12}{valid_window:<25}{review}"
        )

    actionable = [
        (name, report["horizons"][name])
        for name in ("SCALP", "INTRADAY", "SWING")
        if report["horizons"][name]["action"] in {"BUY", "SELL"}
    ]
    if actionable:
        print("-" * width)
        print("ACTIONABLE LEVELS")
        for name, item in actionable:
            levels = item["levels"]
            zone = levels["entry_zone"]
            print(f"\n{name} {item['action']} (expires {str(item['valid_until'])[11:19]} UTC)")
            print(f"  Entry zone : {zone[0]:.2f} - {zone[1]:.2f}")
            print(f"  Stop loss  : {levels['sl']:.2f}")
            print(
                f"  Targets    : TP1 {levels['tp1']:.2f} | "
                f"TP2 {levels['tp2']:.2f} | TP3 {levels['tp3']:.2f}"
            )
    else:
        shared_blocks: list[str] = []
        for name in ("SCALP", "INTRADAY", "SWING"):
            for reason in report["horizons"][name]["blocks"]:
                if reason not in shared_blocks:
                    shared_blocks.append(reason)
        print("-" * width)
        print("WHY THERE IS NO ENTRY")
        for reason in shared_blocks:
            print(f"  - {reason}")
        biases = {report["horizons"][name]["bias"] for name in ("SCALP", "INTRADAY", "SWING")}
        if len(biases) == 1 and "WAIT" not in biases:
            bias = next(iter(biases))
            print(f"\n  Trend bias is {bias}, but entry conditions are unsafe. Do not chase the move.")
    print("-" * width)
    print("After the VALID WINDOW expiry, the position advisory is no longer valid and must be recalculated.")
    print("Evidence is directional strength, not a calibrated win probability. No order is sent.")
    print("=" * width)


def main() -> int:
    parser=argparse.ArgumentParser(description="Run read-only multi-horizon XAUUSD advisory AI.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=15.0)
    args=parser.parse_args()
    lock=ScalpingInstanceLock("data/runtime/gold_advisor.lock")
    try: lock.acquire()
    except ScalpingInstanceAlreadyRunning as error: print(f"Advisor startup blocked: {error}"); return 1
    latest_path=Path("data/runtime/gold_advisory.json")
    history_path=Path("data/research/gold_advisory_history.jsonl")
    last_signature=""
    try:
        if not connect_mt5(): return 1
        while True:
            report=build_gold_advisory(get_scalping_snapshot(scalping_settings.SCALPING_SYMBOL))
            atomic_write_json(str(latest_path), report, indent=2)
            signature=json.dumps({name:(item["action"],item["directional_score"]) for name,item in report["horizons"].items()},sort_keys=True)
            if signature != last_signature:
                history_path.parent.mkdir(parents=True,exist_ok=True)
                with history_path.open("a",encoding="utf-8") as handle:
                    handle.write(json.dumps(report,sort_keys=True,default=str)+"\n");handle.flush();os.fsync(handle.fileno())
                _print(report);last_signature=signature
            if args.once: break
            time.sleep(max(5.0,args.interval_seconds))
        return 0
    except KeyboardInterrupt:
        print("Gold advisor stopped with CTRL+C.");return 0
    finally:
        disconnect_mt5();lock.release()


if __name__=="__main__": raise SystemExit(main())
