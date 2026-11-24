"""Read-only broker candle export for chronological research; never sends orders."""
import json
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5
import pandas as pd


def main():
    root = Path(__file__).resolve().parents[1]/'data/research/entry_efficiency/broker_bars'
    root.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        manifest = dict(exported_at=datetime.now(timezone.utc).isoformat(), frames={})
        for name, timeframe, count in [('M1', mt5.TIMEFRAME_M1, 90000),
                                        ('M5', mt5.TIMEFRAME_M5, 30000),
                                        ('M15', mt5.TIMEFRAME_M15, 15000)]:
            rates = mt5.copy_rates_from_pos('XAUUSD', timeframe, 1, count)
            if rates is None or len(rates) < 1000:
                raise RuntimeError(f'{name}: insufficient broker history: {mt5.last_error()}')
            frame = pd.DataFrame(rates).sort_values('time').drop_duplicates('time')
            frame.to_csv(root/(name+'.csv'), index=False)
            manifest['frames'][name] = dict(rows=len(frame), first=int(frame.time.iloc[0]),
                                          last=int(frame.time.iloc[-1]))
        (root/'manifest.json').write_text(json.dumps(manifest, indent=2))
        print(json.dumps(manifest, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
