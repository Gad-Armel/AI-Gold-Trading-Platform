"""Describe short-term direction and spread cost of recorded entries; no orders."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import numpy as np


def reaction(times, bids, asks, opened, entry, direction, seconds):
    start = int(np.searchsorted(times, opened, side='left'))
    end = int(np.searchsorted(times, opened + seconds, side='right')) - 1
    if (start >= len(times) or end < start or times[start] - opened > 2
            or opened + seconds > times[-1] or opened + seconds - times[end] > 2):
        return None
    gaps = np.diff(times[start:end + 1])
    if len(gaps) and gaps.max() > 10:
        return None
    sign = 1 if direction == 'BUY' else -1
    mid_start = (bids[start] + asks[start]) / 2
    mid_end = (bids[end] + asks[end]) / 2
    exit_price = bids[end] if sign == 1 else asks[end]
    return dict(signed_mid_move=round(float(sign * (mid_end - mid_start)), 4),
                executable_move=round(float(sign * (exit_price - entry)), 4),
                starting_spread=round(float(asks[start] - bids[start]), 4))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    report = json.loads((args.capture / 'report.json').read_text())
    with np.load(args.capture / 'ticks.npz') as ticks:
        times, bids, asks = (ticks[key] for key in ('utc_time', 'bid', 'ask'))
    # Original report preserves actual fills and outcomes but not direction/price;
    # recover these from captured histories, matched by broker position ticket.
    root = Path(__file__).resolve().parents[1]
    tickets = {row['ticket']: row for row in report['rows']}
    trades = {}
    for path in sorted((root / 'data/monitoring').glob('*/observations.jsonl')):
        for line in path.open(encoding='utf-8'):
            try:
                obs = json.loads(line)
            except json.JSONDecodeError:
                continue
            for lane in obs.get('status', {}).get('lanes', {}).values():
                for trade in lane.get('closed_trades', []):
                    if str(trade['position_id']) in tickets:
                        trades[str(trade['position_id'])] = trade
    rows = []
    for ticket, label in tickets.items():
        trade = trades.get(ticket)
        if trade is None:
            continue
        opened = datetime.fromisoformat(trade['opened_at']).timestamp()
        rows.append(dict(ticket=ticket, lane=label['lane'], period=label['period'],
                         actual_profit=trade['profit'], reaction={str(s): reaction(
                             times, bids, asks, opened, trade['entry_price'], trade['direction'], s)
                             for s in (30, 60, 180)}))
    groups = []
    for lane in ('SCALP', 'INTRADAY', 'SWING', 'ALL'):
        for result in ('LOSS', 'WIN', 'ALL'):
            for seconds in ('30', '60', '180'):
                sample = [row['reaction'][seconds] for row in rows
                          if (lane == 'ALL' or row['lane'] == lane)
                          and (result == 'ALL' or (row['actual_profit'] < 0 if result == 'LOSS'
                                                  else row['actual_profit'] > 0))
                          and row['reaction'][seconds] is not None]
                groups.append(dict(lane=lane, actual_result=result, seconds=int(seconds),
                    entries=len(sample), favorable_mid=sum(r['signed_mid_move'] > 0 for r in sample),
                    favorable_executable=sum(r['executable_move'] > 0 for r in sample),
                    median_signed_mid_move=float(np.median([r['signed_mid_move'] for r in sample])) if sample else None,
                    median_executable_move=float(np.median([r['executable_move'] for r in sample])) if sample else None))
    output = dict(source_capture=str(args.capture), rows=rows, groups=groups, limitations=[
        'Descriptive actual-entry selection, not blind prediction validation or a strategy backtest.',
        'Mid-price movement isolates direction; executable marks include spread and original fill displacement.',
        'Endpoint marks can occur after actual exits; no changed entry, exit, capacity or portfolio is simulated.',
        'Positive movement does not imply stop survival, attainable profit, or independent observations.',
        'No additional fees, financing or assumed exit slippage; timestamps normalized by original tick capture.',
        'Missing endpoint coverage or internal quote gaps over ten seconds are excluded per horizon.'])
    (args.capture / 'entry_reaction.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(dict(groups=groups), indent=2))


if __name__ == '__main__':
    main()
