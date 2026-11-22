"""Cache candle-only exit statistics while rechecking completion and freshness."""
from copy import deepcopy
import pandas as pd
from config import gold_consensus_settings as settings
from services.research.gold_adaptive_exit import exit_frame, market_exit_context


class ExitContextCache:
    def __init__(self):
        self.entries = {}
        self.hits = self.misses = 0

    def get(self, snapshot, horizon, *, now_utc=None):
        name, seconds = exit_frame(horizon)
        frame = pd.DataFrame(snapshot.candles.get(name))
        columns = ['time', 'open', 'high', 'low', 'close']
        if len(frame)<30 or not set(columns).issubset(frame.columns):
            return market_exit_context(snapshot, horizon, now_utc=now_utc)
        # Use precisely the canonical function's clock conventions. Hash raw
        # completed data, including corrections and duplicates; forming prices
        # cannot change candle statistics. The canonical function validates and
        # normalizes values on every miss.
        stamps = (pd.to_datetime(frame.time, unit='s', utc=True)
                  if pd.api.types.is_numeric_dtype(frame.time)
                  else pd.to_datetime(frame.time, utc=True))
        now = (pd.Timestamp(now_utc)+pd.Timedelta(seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
               if now_utc is not None else pd.Timestamp(snapshot.timestamp))
        now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
        completed = stamps+pd.Timedelta(seconds=seconds)<=now
        latest = stamps[completed].max()
        stale = pd.isna(latest) or (now-latest).total_seconds()>seconds*3
        try:
            fingerprint = pd.util.hash_pandas_object(frame.loc[completed, columns], index=False).values.tobytes()
        except (TypeError, ValueError):
            return market_exit_context(snapshot, horizon, now_utc=now_utc)
        key = (name, seconds, len(frame), settings.MT5_SERVER_UTC_OFFSET_SECONDS, bool(stale), fingerprint)
        cached = self.entries.get(horizon)
        if cached is not None and cached[0] == key:
            self.hits += 1
            return deepcopy(cached[1])
        result = market_exit_context(snapshot, horizon, now_utc=now_utc)
        self.entries[horizon] = (key, deepcopy(result))
        self.misses += 1
        return result
