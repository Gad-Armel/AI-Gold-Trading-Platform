"""Read-only live evidence capture; never places or modifies orders."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.utils.atomic_json import atomic_write_json


def write_observation(output, record):
    line = json.dumps(record, default=str, separators=(',', ':'))
    with (output/'observations.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(line+'\n')
    atomic_write_json(output/'latest.json', record, indent=0)


def read_status(path):
    for attempt in range(5):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(.04 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--minutes', type=float, default=120)
    parser.add_argument('--interval', type=float, default=15)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'data' / 'monitoring' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True, exist_ok=True)
    print(str(output), flush=True)
    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialization failed: {mt5.last_error()}')
    start = time.monotonic()
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Monitor requires connected demo account')
        while True:
            now = datetime.now(timezone.utc)
            record = {'observed_at': now.isoformat()}
            try:
                record['status'] = read_status(root/'data/runtime/gold_consensus_status.json')
                tick = mt5.symbol_info_tick('XAUUSD')
                record['tick'] = tick._asdict() if tick else None
                account = mt5.account_info()
                record['account'] = {key: getattr(account, key) for key in
                                     ('balance', 'equity', 'profit', 'margin_free', 'currency', 'trade_mode')}
                positions = mt5.positions_get(symbol='XAUUSD')
                record['positions'] = [p._asdict() for p in positions] if positions is not None else None
                record['candles'] = {}
                for name, frame in [('M1', mt5.TIMEFRAME_M1), ('M5', mt5.TIMEFRAME_M5), ('M15', mt5.TIMEFRAME_M15)]:
                    bars = mt5.copy_rates_from_pos('XAUUSD', frame, 0, 40)
                    record['candles'][name] = [{key: row[key].item() for key in bars.dtype.names} for row in bars] if bars is not None else []
                deals = mt5.history_deals_get(now-timedelta(hours=24), now+timedelta(hours=4))
                record['deals'] = [deal._asdict() for deal in deals if deal.symbol == 'XAUUSD'] if deals is not None else None
            except Exception as exc:
                record['error'] = f'{type(exc).__name__}: {exc}'
            write_observation(output, record)
            if args.once or time.monotonic()-start >= args.minutes*60:
                break
            time.sleep(max(1, args.interval))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
