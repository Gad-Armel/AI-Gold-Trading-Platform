from __future__ import annotations

import argparse

from config import scalping_settings
from services.bot.scalping_instance_lock import ScalpingInstanceAlreadyRunning, ScalpingInstanceLock
from services.bot.v6_shadow_loop_runner import run_v6_shadow_loop
from services.execution.mt5_connector import connect_mt5, disconnect_mt5


def main() -> int:
    parser=argparse.ArgumentParser(description="Run V6 MT5-feed shadow calibration without broker orders.")
    parser.add_argument("--max-minutes",type=float,default=0.0)
    args=parser.parse_args()
    lock=ScalpingInstanceLock()
    try: lock.acquire()
    except ScalpingInstanceAlreadyRunning as exc:
        print(f"Shadow startup blocked: {exc}"); return 1
    try:
        if not connect_mt5(): return 1
        try:
            import MetaTrader5 as mt5
            run_v6_shadow_loop(scalping_settings.SCALPING_SYMBOL,max_minutes=args.max_minutes,mt5_module=mt5)
            return 0
        finally: disconnect_mt5()
    finally: lock.release()

if __name__=="__main__":
    raise SystemExit(main())
