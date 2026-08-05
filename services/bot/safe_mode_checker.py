from config.settings import (
    ENABLE_LIVE_TRADING,
    LIVE_TRADING_CONFIRMATION,
    REQUIRED_LIVE_TRADING_CONFIRMATION,
)


def get_safe_mode_status():
    """
    Checks whether live trading is safely unlocked.

    Live trading requires:
    - ENABLE_LIVE_TRADING=True
    - LIVE_TRADING_CONFIRMATION matching REQUIRED_LIVE_TRADING_CONFIRMATION
    """

    if not ENABLE_LIVE_TRADING:
        return {
            "live_trading_requested": False,
            "live_trading_unlocked": False,
            "safe_mode": True,
            "reason": "Live trading disabled. Bot is in safe mode.",
        }

    if LIVE_TRADING_CONFIRMATION != REQUIRED_LIVE_TRADING_CONFIRMATION:
        return {
            "live_trading_requested": True,
            "live_trading_unlocked": False,
            "safe_mode": True,
            "reason": (
                "Live trading requested, but confirmation text is missing or incorrect."
            ),
        }

    return {
        "live_trading_requested": True,
        "live_trading_unlocked": True,
        "safe_mode": False,
        "reason": "Live trading unlocked by explicit confirmation.",
    }


def is_live_trading_unlocked():
    status = get_safe_mode_status()
    return status["live_trading_unlocked"]