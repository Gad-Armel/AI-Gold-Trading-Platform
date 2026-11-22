import MetaTrader5 as mt5
import pandas as pd

from services.market_data.timeframe_service import get_timeframe


def get_candles(symbol, timeframe_name="M1", count=100):
    timeframe = get_timeframe(timeframe_name)

    if timeframe is None:
        print("Invalid timeframe:", timeframe_name)
        return None

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)

    if rates is None:
        return None

    df = pd.DataFrame(rates)

    if df.empty:
        return df

    df["time"] = pd.to_datetime(df["time"], unit="s")

    return df