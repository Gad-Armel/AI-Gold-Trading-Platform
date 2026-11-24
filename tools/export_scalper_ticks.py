"""Read-only broker tick capture for native flow diagnostics; never sends orders."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics


def main():
    import MetaTrader5 as mt5
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours', type=int, default=24)
    parser.add_argument('--output', type=Path, default=Path('data/research/scalper_expert3'))
    args = parser.parse_args()
    if not 1 <= args.hours <= 72:
        parser.error('--hours must be between 1 and 72')
    if not mt5.initialize(path=r'C:\Program Files\MetaTrader\terminal64.exe'):
        raise RuntimeError(mt5.last_error())
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Diagnostic expects the existing demo account')
        tick = mt5.symbol_info_tick('XAUUSD')
        if tick is None:
            raise RuntimeError('No XAUUSD tick')
        # Use broker tick epochs as returned, not the workstation wall clock.
        start = tick.time - args.hours * 3600
        rows = mt5.copy_ticks_range('XAUUSD', datetime.fromtimestamp(start, timezone.utc),
                                   datetime.fromtimestamp(tick.time, timezone.utc), mt5.COPY_TICKS_INFO)
        if rows is None or len(rows) == 0:
            raise RuntimeError(f'No broker ticks: {mt5.last_error()}')
        args.output.mkdir(parents=True, exist_ok=True)
        spreads = []; previous = 0; kept = 0
        path = args.output / 'scalp_ticks.csv'
        with path.open('w', encoding='ascii', newline='') as stream:
            for row in rows:
                stamp, bid, ask = int(row['time_msc']), float(row['bid']), float(row['ask'])
                if stamp-previous < 100 or bid <= 0 or ask < bid:
                    continue
                stream.write(f'{stamp};{bid:.5f};{ask:.5f}\n')
                previous = stamp; kept += 1; spreads.append(ask-bid)
        summary = dict(hours_requested=args.hours, broker_ticks=len(rows), sampled_ticks=kept,
                       mean_spread=statistics.mean(spreads), median_spread=statistics.median(spreads),
                       fraction_above_old_030=sum(s > .300001 for s in spreads)/kept,
                       fraction_above_new_060=sum(s > .600001 for s in spreads)/kept,
                       orders_sent=0, purpose='Real broker tick diagnostic, not a profitability backtest')
        (args.output/'tick_capture.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
