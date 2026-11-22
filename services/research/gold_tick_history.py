"""Bounded incremental MT5 quote history, with explicit failure and freshness."""
from datetime import timedelta
import time
import pandas as pd
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time


class TickHistoryBuffer:
    def __init__(self):
        self.frame = pd.DataFrame()

    def refresh(self, mt5, symbol, now):
        from services.research.gold_advisory_v3 import _tick_frame
        start = now-timedelta(seconds=920)
        if not self.frame.empty:
            latest = float(self.frame.timestamp.iloc[-1])
            cursor = min(latest, now.timestamp())-1
            start = max(start, now.fromtimestamp(cursor, now.tzinfo))
        before = time.perf_counter()
        error = ''
        try:
            rows = mt5.copy_ticks_range(symbol, to_broker_time(start),
                                       to_broker_time(now+timedelta(seconds=settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS)),
                                       int(getattr(mt5, 'COPY_TICKS_ALL', -1)))
            if rows is None:
                raise RuntimeError(f'MT5 history request failed: {mt5.last_error()}')
            fresh = _tick_frame(rows)
            if fresh.empty:
                error = 'MT5 returned no usable ticks'
            else:
                fresh['timestamp'] -= float(settings.MT5_SERVER_UTC_OFFSET_SECONDS)
                if (fresh.timestamp > now.timestamp()+settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS).any():
                    error = 'Tick history contains future timestamps; verify configured broker clock'
                fresh = fresh[(fresh.timestamp >= now.timestamp()-920) & (fresh.timestamp <= now.timestamp()+settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS)]
                self.frame = pd.concat([self.frame,fresh], ignore_index=True) if not self.frame.empty else fresh
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        if not self.frame.empty:
            self.frame = (self.frame[(self.frame.timestamp >= now.timestamp()-920) & (self.frame.timestamp <= now.timestamp()+settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS)]
                          .sort_values('timestamp').drop_duplicates(['timestamp','bid','ask'])
                          .tail(100_000).reset_index(drop=True))
        age = now.timestamp()-float(self.frame.timestamp.iloc[-1]) if not self.frame.empty else None
        available = not error and age is not None and -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS <= age <= 3
        if not available and not error:
            error = 'MT5 tick history is stale' if age is not None else 'MT5 tick history is empty'
        status = dict(available=available,error=error,request_seconds=(now-start).total_seconds(),
                      fetch_ms=round((time.perf_counter()-before)*1000,2),cached_ticks=len(self.frame),
                      latest_tick_age_seconds=age)
        return self.frame.copy(), status
