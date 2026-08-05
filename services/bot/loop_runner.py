import time

from services.bot.cycle_runner import run_bot_cycle
from services.bot.emergency_stop import check_emergency_stop


def run_bot_loop(symbol, interval_seconds=5, max_cycles=None):
    """
    Runs repeated bot cycles.

    The loop stops if:
    - max_cycles is reached
    - EMERGENCY_STOP=True
    - user manually stops with CTRL+C
    """

    cycle_count = 0

    print("")
    print("=" * 70)
    print("BOT LOOP STARTED")
    print("=" * 70)
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval_seconds} second(s)")
    print(f"Max Cycles: {max_cycles}")
    print("=" * 70)
    print("")

    try:
        while True:
            emergency_active, emergency_reason = check_emergency_stop()

            if emergency_active:
                print("")
                print("=" * 70)
                print("BOT LOOP STOPPED")
                print("=" * 70)
                print(emergency_reason)
                print("=" * 70)
                print("")
                break

            cycle_count += 1

            print("")
            print(f"Running bot cycle {cycle_count}...")
            run_bot_cycle(symbol)

            if max_cycles is not None and cycle_count >= max_cycles:
                print("")
                print("=" * 70)
                print("BOT LOOP FINISHED")
                print("=" * 70)
                print(f"Completed {cycle_count} cycle(s).")
                print("=" * 70)
                print("")
                break

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print("")
        print("=" * 70)
        print("BOT LOOP MANUALLY STOPPED")
        print("=" * 70)
        print("User stopped the bot with CTRL+C.")
        print("=" * 70)
        print("")