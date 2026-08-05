from __future__ import annotations

import argparse

from config import scalping_settings
from services.bot.candle_follow_shadow_loop import run_candle_follow_shadow_loop
from services.bot.scalping_instance_lock import ScalpingInstanceAlreadyRunning, ScalpingInstanceLock
from services.execution.mt5_connector import connect_mt5, disconnect_mt5


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the candle-colour M1 shadow benchmark.")
    parser.add_argument("--max-minutes", type=float, default=0.0)
    args = parser.parse_args()
    lock = ScalpingInstanceLock()
    try:
        lock.acquire()
    except ScalpingInstanceAlreadyRunning as exc:
        print(f"Candle benchmark startup blocked: {exc}")
        return 1
    try:
        if not connect_mt5():
            return 1
        run_candle_follow_shadow_loop(scalping_settings.SCALPING_SYMBOL, max_minutes=args.max_minutes)
        return 0
    finally:
        disconnect_mt5()
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
