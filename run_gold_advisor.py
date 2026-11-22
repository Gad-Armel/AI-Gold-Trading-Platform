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
from services.research.gold_advisory_dashboard import print_gold_advisory
from services.utils.atomic_json import atomic_write_json


def _print(report: dict) -> None:
    print_gold_advisory(report)


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
