"""Read-only, retrospective filtering of actual SCALP trades by M1 confirmation."""
import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.research.gold_entry_momentum import entry_momentum_blocks
from tools.review_demo_losses import metrics


def preceding_bars(bars, opened_at, offset):
    parsed = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Trade opening time requires an explicit timezone')
    opened = parsed.timestamp()
    stamps = [float(row['time'])-offset for row in bars]
    stop = bisect_right(stamps, opened-60)
    return bars[max(0, stop-3):stop], opened


def compare(bars, trades, offset):
    ordered = sorted(bars, key=lambda row: float(row['time']))
    if len({row['time'] for row in ordered}) != len(ordered):
        raise ValueError('Duplicate historical M1 timestamps')
    eligible = []
    excluded = 0
    for trade in sorted(trades, key=lambda row: row['opened_at']):
        recent, opened = preceding_bars(ordered, trade['opened_at'], offset)
        if (len(recent) < 3 or opened-(float(recent[-1]['time'])-offset+60) >= 60
                or any(abs(float(current['time'])-float(previous['time'])-60) >= .01
                       for previous, current in zip(recent, recent[1:]))):
            excluded += 1
            continue
        decision = dict(allowed=True, direction=trade['direction'])
        with_offset = [dict(row, time=float(row['time'])-offset+settings.MT5_SERVER_UTC_OFFSET_SECONDS)
                       for row in recent]
        accepted = [count for count in (1, 2, 3) if not entry_momentum_blocks(
            decision, with_offset, now=opened, required_bars=count)]
        eligible.append(dict(trade, accepted_counts=accepted))
    days = sorted({trade['opened_at'][:10] for trade in eligible})
    split = days[max(0, len(days)*2//3)] if days else None
    groups = {'all': eligible,
              'earlier_dates': [trade for trade in eligible if trade['opened_at'][:10] < split],
              'later_dates': [trade for trade in eligible if trade['opened_at'][:10] >= split]}
    return dict(excluded_missing_or_stale_history=excluded, comparable_trades=len(eligible),
                later_segment_starts=split,
                segments={name: dict(baseline=metrics(group), by_required_bars={str(count): metrics(
                    [trade for trade in group if count in trade['accepted_counts']]) for count in (1, 2, 3)})
                          for name, group in groups.items()},
                by_day={day: {str(count): metrics([trade for trade in eligible
                    if trade['opened_at'].startswith(day) and count in trade['accepted_counts']])
                              for count in (1, 2, 3)} for day in days},
                trades=eligible)


def fetch_demo(output):
    import MetaTrader5 as mt5
    from services.execution.gold_consensus_demo_broker import recent_closed_consensus_trades
    if not mt5.initialize(timeout=10000):
        raise RuntimeError(str(mt5.last_error()))
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Connected demo account required')
        rates = mt5.copy_rates_from_pos(settings.SYMBOL, mt5.TIMEFRAME_M1, 0, 30000)
        if rates is None or len(rates) < 3:
            raise RuntimeError(f'Insufficient M1 history: {mt5.last_error()}')
        bars = [{key: row[key].item() for key in rates.dtype.names} for row in rates]
        trades = recent_closed_consensus_trades(mt5, limit=10000, lookback_days=30,
            magic_number=int(settings.HORIZON_LANES['SCALP']['magic']), strict=True)
        payload = dict(as_of=datetime.now(timezone.utc).isoformat(), demo_verified=True,
                       broker_utc_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                       bars=bars, trades=trades)
        (output/'input.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    finally:
        mt5.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fetch-demo', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.fetch_demo:
        fetch_demo(args.output)
    payload = json.loads((args.output/'input.json').read_text(encoding='utf-8'))
    result = compare(payload['bars'], payload['trades'], payload['broker_utc_offset_seconds'])
    result.update(as_of=payload['as_of'], deployed=False, limitations=[
        'Retrospective subset of actual closed trades, not a replay of delayed or additional entries.',
        'Actual broker trade P/L includes recovered fees; rejected trades are not simulated at a new time.',
        'Later dates are a descriptive chronological check, not untouched out-of-sample data.',
        'No neutral/doji candle, forming candle or missing minute can confirm a consecutive sequence.',
        'Results depend on configured broker clock offset and recoverable historical opening deals.',
        'Existing exits, correlated positions and historical strategy versions remain mixed.'])
    (args.output/'comparison.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in ('trades', 'by_day')}, indent=2))


if __name__ == '__main__':
    main()
