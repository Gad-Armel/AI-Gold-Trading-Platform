"""Read-only MT5 trade/quote audit, with executable-side MFE/MAE and fees."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path


def main():
    import MetaTrader5 as mt5
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not mt5.initialize(path=r'C:\Program Files\MetaTrader\terminal64.exe'):
        raise RuntimeError(mt5.last_error())
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Existing demo account required')
        quote = mt5.symbol_info_tick('XAUUSD')
        utc = lambda value: datetime.fromtimestamp(value, timezone.utc)
        deals = mt5.history_deals_get(utc(quote.time - 7*86400), utc(quote.time + 60))
        if deals is None:
            raise RuntimeError(mt5.last_error())
        grouped = defaultdict(list)
        owned = {d.position_id for d in deals if d.magic == 92563101 and d.entry == mt5.DEAL_ENTRY_IN}
        for d in deals:
            if d.position_id in owned:
                grouped[d.position_id].append(d)
        result = []
        args.output.mkdir(parents=True, exist_ok=True)
        for ident, fills in sorted(grouped.items()):
            entries = [d for d in fills if d.entry == mt5.DEAL_ENTRY_IN]
            exits = [d for d in fills if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)]
            if not entries or not exits or sum(d.volume for d in exits) + 1e-8 < sum(d.volume for d in entries):
                continue
            entry, close = entries[0], exits[-1]
            # Current EA uses one fixed-size entry. Do not invent a cost basis for partial fills.
            if len(entries) != 1:
                continue
            ticks = mt5.copy_ticks_range('XAUUSD', utc(entry.time-60), utc(close.time+60), mt5.COPY_TICKS_INFO)
            if ticks is None or not len(ticks):
                continue
            side = 1 if entry.type == mt5.DEAL_TYPE_BUY else -1
            money = mt5.order_calc_profit(entry.type, 'XAUUSD', entry.volume, entry.price, entry.price+side)
            if money is None:
                raise RuntimeError(mt5.last_error())
            fees = sum(d.commission + d.swap + d.fee for d in fills)
            active = [r for r in ticks if entry.time_msc <= int(r['time_msc']) <= close.time_msc]
            values = [side * (float(r['bid'] if side > 0 else r['ask']) - entry.price) * money + fees for r in active]
            before = [r for r in ticks if int(r['time_msc']) <= entry.time_msc]
            def pre_move(seconds):
                subset = [r for r in before if int(r['time_msc']) >= entry.time_msc-seconds*1000]
                if len(subset) < 2:
                    return None
                mids = [(float(r['bid'])+float(r['ask']))/2 for r in subset]
                path = sum(abs(b-a) for a,b in zip(mids, mids[1:]))
                return {'move': round(side*(mids[-1]-mids[0]),4),
                        'efficiency': round(abs(mids[-1]-mids[0])/path,4) if path else 0,
                        'aligned_location': round((mids[-1]-min(mids))/(max(mids)-min(mids)) if side>0 else (max(mids)-mids[-1])/(max(mids)-min(mids)),4) if max(mids)>min(mids) else .5}
            row = {'position': str(ident), 'comment': entry.comment, 'side': 'BUY' if side>0 else 'SELL',
                   'entry_server': utc(entry.time).strftime('%Y-%m-%d %H:%M:%S'), 'entry_msc': entry.time_msc,
                   'exit_msc': close.time_msc, 'entry_price': entry.price, 'exit_price': close.price,
                   'held_seconds': (close.time_msc-entry.time_msc)/1000, 'volume': entry.volume,
                   'net': round(sum(d.profit for d in fills)+fees,4), 'exit_reason': close.reason,
                   'mfe': round(max(values),4) if values else None, 'mae': round(min(values),4) if values else None,
                   'entry_spread': round(float(before[-1]['ask']-before[-1]['bid']),4) if before else None,
                   'pre_3s': pre_move(3), 'pre_8s': pre_move(8), 'pre_20s': pre_move(20), 'pre_60s': pre_move(60),
                   'quote_count': len(active)}
            result.append(row)
            with (args.output/f'trade_{ident}.csv').open('w',encoding='ascii') as stream:
                stream.write('time_msc,bid,ask\n')
                for tick in ticks:
                    stream.write(f"{int(tick['time_msc'])},{float(tick['bid'])},{float(tick['ask'])}\n")
        rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M1, 0, 240)
        candles = [] if rates is None else [{k: int(r[k]) if k in ('time','tick_volume','spread','real_volume') else float(r[k]) for k in rates.dtype.names} for r in rates]
        report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'quote': quote._asdict(),
                  'positions': [p._asdict() for p in mt5.positions_get() or ()], 'trades': result, 'm1': candles,
                  'orders_sent': 0, 'limitation': 'Historical attribution, not an out-of-sample strategy backtest. Broker timestamps kept unchanged.'}
        (args.output/'trade_review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'trades': result[-10:], 'total_closed': len(result), 'orders_sent': 0},indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
