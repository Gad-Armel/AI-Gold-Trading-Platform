from __future__ import annotations

from datetime import datetime, timezone

import MetaTrader5 as mt5


def get_current_price(symbol):
    """Return the current quote plus the MT5 market clock when available.

    MT5 candle timestamps and the terminal tick clock can differ from the
    computer clock by a broker/server offset. Carrying the tick timestamp lets
    candle-age diagnostics and candle-boundary caching use one coherent clock.
    """
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return None

    tick_epoch = int(getattr(tick, "time", 0) or 0)
    tick_time = (
        datetime.fromtimestamp(tick_epoch, tz=timezone.utc)
        if tick_epoch > 0
        else None
    )

    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": tick.ask - tick.bid,
        "tick_time_epoch": tick_epoch,
        "tick_time": tick_time,
        "time_msc": int(getattr(tick, "time_msc", 0) or 0),
        "last": float(getattr(tick, "last", 0.0) or 0.0),
        "volume": float(getattr(tick, "volume", 0.0) or 0.0),
        "volume_real": float(getattr(tick, "volume_real", 0.0) or 0.0),
        "flags": int(getattr(tick, "flags", 0) or 0),
    }
