"""Read-only, paired latency and parity check on current broker candles."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
import MetaTrader5 as mt5
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.research.gold_adaptive_exit import market_exit_context
from services.research.gold_exit_context_cache import ExitContextCache


def main():
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        frames = {}
        for name, timeframe, count in [('M1', mt5.TIMEFRAME_M1, 180),
                ('M15', mt5.TIMEFRAME_M15, 140), ('H1', mt5.TIMEFRAME_H1, 120)]:
            rates = mt5.copy_rates_from_pos('XAUUSD', timeframe, 0, count)
            if rates is None or len(rates)<100:
                raise RuntimeError(f'{name} broker candles unavailable')
            frames[name] = pd.DataFrame(rates)
        now = datetime.now(timezone.utc)
        snapshot = SimpleNamespace(candles=frames,
            timestamp=now+timedelta(seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS))
        cache = ExitContextCache()
        horizons = ('SCALP', 'INTRADAY', 'SWING')
        for lane in horizons:
            assert cache.get(snapshot, lane, now_utc=now)==market_exit_context(snapshot, lane, now_utc=now)
        timings = {'fresh': [], 'cached': []}
        for iteration in range(60):
            for method in (('fresh', 'cached') if iteration%2==0 else ('cached', 'fresh')):
                start = time.perf_counter()
                for lane in horizons:
                    result = (market_exit_context(snapshot, lane, now_utc=now) if method=='fresh'
                              else cache.get(snapshot, lane, now_utc=now))
                    assert result['available']
                timings[method].append((time.perf_counter()-start)*1000)
        report = dict(observed_at=now.isoformat(), batches_per_method=60, lanes_per_batch=3,
            median_ms={k: round(statistics.median(v), 3) for k,v in timings.items()},
            note='Paired isolated candle-context latency, not full trading-loop latency or profit evidence.',
            parity=True, cache_hits=cache.hits, cache_misses=cache.misses)
        report['median_reduction_fraction'] = round(1-report['median_ms']['cached']/report['median_ms']['fresh'], 4)
        (ROOT/'data/research/entry_efficiency/exit_context_latency.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
