"""Read-only historical bid/ask probe for assessing tick-level research coverage."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import MetaTrader5 as mt5
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time


def main():
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)-timedelta(days=1)
    start = end-timedelta(hours=1)
    output = PROJECT/'data/research/entry_efficiency/tick_probe'
    output.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        rates = mt5.copy_ticks_range('XAUUSD', to_broker_time(start), to_broker_time(end), mt5.COPY_TICKS_ALL)
        if rates is None or not len(rates):
            raise RuntimeError(f'Historical quote probe unavailable: {mt5.last_error()}')
        utc_msc = rates['time_msc']-int(settings.MT5_SERVER_UTC_OFFSET_SECONDS*1000)
        valid = (np.isfinite(rates['bid']) & np.isfinite(rates['ask']) & (rates['bid']>0)
                 & (rates['ask']>=rates['bid']) & (utc_msc>=start.timestamp()*1000)
                 & (utc_msc<=end.timestamp()*1000))
        name = start.strftime('%Y%m%dT%H%M%SZ')
        np.savez_compressed(output/(name+'.npz'), utc_time_msc=utc_msc[valid],
                            bid=rates['bid'][valid], ask=rates['ask'][valid])
        times = np.sort(utc_msc[valid])
        report = dict(start_utc=start.isoformat(), end_utc=end.isoformat(),
            received_ticks=len(rates), usable_ticks=int(valid.sum()),
            broker_utc_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS,
            maximum_gap_seconds=float(np.diff(times).max()/1000) if len(times)>1 else None,
            median_spread=float(np.median(rates['ask'][valid]-rates['bid'][valid])) if valid.any() else None,
            artifact=str(output/(name+'.npz')),
            note='Historical executable quotes, no inferred aggressors, order book or institutional order flow.')
        (output/'manifest.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
