from config.settings import MAGIC_NUMBER, MAX_OPEN_POSITIONS
from services.execution.mt5_connector import get_open_positions


def _get(position, key, default=None):
    if position is None:
        return default

    if isinstance(position, dict):
        return position.get(key, default)

    return getattr(position, key, default)


def get_bot_open_positions(symbol):
    """
    Returns open positions for this bot only.

    It filters by:
    - symbol
    - MAGIC_NUMBER
    """

    positions = get_open_positions()

    if positions is None:
        return []

    bot_positions = []

    for position in positions:
        position_symbol = _get(position, "symbol")
        position_magic = _get(position, "magic")

        if position_symbol == symbol and position_magic == MAGIC_NUMBER:
            bot_positions.append(position)

    return bot_positions


def count_bot_open_positions(symbol):
    return len(get_bot_open_positions(symbol))


def is_position_limit_safe(symbol):
    open_count = count_bot_open_positions(symbol)

    if open_count >= MAX_OPEN_POSITIONS:
        return False, f"Position limit reached: {open_count}/{MAX_OPEN_POSITIONS}"

    return True, f"Position limit safe: {open_count}/{MAX_OPEN_POSITIONS}"