from config.settings import (
    SYMBOL,
    LOT_SIZE,
    MAGIC_NUMBER,
    MAX_SPREAD,
    PROFIT_TARGET_USD,
    ENABLE_LIVE_TRADING,
    MIN_AI_CONFIDENCE,
    MAX_OPEN_POSITIONS,
    RUN_INTERVAL_SECONDS,
    MAX_BOT_CYCLES,
    LOG_FILE_PATH,
    SIGNAL_LOG_FOLDER,
    SAVE_SIGNAL_TEXT_LOGS,
    EMERGENCY_STOP,
)


def print_startup_report():
    print("")
    print("=" * 70)
    print("AI GOLD TRADING PLATFORM STARTUP REPORT")
    print("=" * 70)

    print(f"Symbol: {SYMBOL}")
    print(f"Lot Size: {LOT_SIZE}")
    print(f"Magic Number: {MAGIC_NUMBER}")

    print("-" * 70)
    print(f"Emergency Stop: {EMERGENCY_STOP}")

    if EMERGENCY_STOP:
        print("BOT BLOCKED: Emergency stop is enabled.")
    else:
        print("Emergency Stop Status: Clear.")

    print("-" * 70)
    print(f"Live Trading Enabled: {ENABLE_LIVE_TRADING}")

    if ENABLE_LIVE_TRADING:
        print("WARNING: LIVE TRADING IS ENABLED.")
    else:
        print("Safety Mode: Live trading is disabled.")

    print("-" * 70)
    print(f"Max Spread Allowed: {MAX_SPREAD}")
    print(f"Profit Target USD: {PROFIT_TARGET_USD}")
    print(f"Minimum AI Confidence: {MIN_AI_CONFIDENCE}")
    print(f"Max Open Positions: {MAX_OPEN_POSITIONS}")

    print("-" * 70)
    print(f"Run Interval Seconds: {RUN_INTERVAL_SECONDS}")
    print(f"Max Bot Cycles: {MAX_BOT_CYCLES}")

    print("-" * 70)
    print(f"Cycle Log File: {LOG_FILE_PATH}")
    print(f"Signal Log Folder: {SIGNAL_LOG_FOLDER}")
    print(f"Save Signal Text Logs: {SAVE_SIGNAL_TEXT_LOGS}")

    print("=" * 70)
    print("")