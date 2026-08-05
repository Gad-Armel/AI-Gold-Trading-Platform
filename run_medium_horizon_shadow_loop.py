from __future__ import annotations

import argparse

from config import scalping_settings
from services.bot.medium_horizon_shadow_loop import run_medium_horizon_shadow_loop
from services.bot.scalping_instance_lock import ScalpingInstanceAlreadyRunning, ScalpingInstanceLock
from services.execution.mt5_connector import connect_mt5, disconnect_mt5


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated medium-horizon XAUUSD shadow model.")
    parser.add_argument("--max-minutes", type=float, default=0.0)
    args = parser.parse_args()
    lock = ScalpingInstanceLock()
    try:
        lock.acquire()
    except ScalpingInstanceAlreadyRunning as error:
        print(f"Medium-horizon startup blocked: {error}")
        return 1
    try:
        if not connect_mt5():
            return 1
        run_medium_horizon_shadow_loop(scalping_settings.SCALPING_SYMBOL, max_minutes=args.max_minutes)
        return 0
    finally:
        disconnect_mt5()
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
