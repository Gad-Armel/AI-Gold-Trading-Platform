"""Summarize recorded MT5 observations without modifying trading state."""
import argparse
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def fresh_status(row):
    try:
        observed = datetime.fromisoformat(row['observed_at'])
        updated = datetime.fromisoformat(row['status']['updated_at'])
        observed = observed.replace(tzinfo=timezone.utc) if observed.tzinfo is None else observed
        updated = updated.replace(tzinfo=timezone.utc) if updated.tzinfo is None else updated
        return -5 <= (observed-updated).total_seconds() <= 30
    except (KeyError, TypeError, ValueError):
        return False


def summarize(folder):
    rows = []
    with (folder/'observations.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    raw_count = len(rows)
    rows = [row for row in rows if 'account' in row and 'status' in row and fresh_status(row)]
    if not rows:
        raise RuntimeError('No observations')
    first, last = rows[0], rows[-1]
    start = datetime.fromisoformat(first['observed_at'])
    elapsed = (datetime.fromisoformat(last['observed_at'])-start).total_seconds()
    trades = {}
    blocks = Counter()
    excursions = {}
    latencies = []
    errors = Counter()
    for row in rows:
        status = row['status']
        latency = status.get('loop_elapsed_ms')
        if isinstance(latency, (int, float)):
            latencies.append(latency)
        for name, lane in status.get('lanes', {}).items():
            for block in lane.get('entry_timing_blocks', [])+lane.get('decision', {}).get('blocks', []):
                blocks[name+': '+block.split(':')[0]] += 1
            for trade in lane.get('closed_trades', []):
                if datetime.fromisoformat(trade['closed_at']) >= start:
                    trades[str(trade['position_id'])] = dict(trade, horizon=name)
            for position in lane.get('positions', []):
                key = str(position['ticket'])
                prior = excursions.setdefault(key, {'peak_floating': position['profit'], 'trough_floating': position['profit']})
                prior['peak_floating'] = max(prior['peak_floating'], position['profit'])
                prior['trough_floating'] = min(prior['trough_floating'], position['profit'])
        errors.update(status.get('advisor_errors', {}).keys())
    closed = list(trades.values())
    gains = sum(max(0, trade['profit']) for trade in closed)
    losses = -sum(min(0, trade['profit']) for trade in closed)
    equity_peak = first['account']['equity']
    maximum_drawdown = 0.0
    maximum_status_lag = 0.0
    for row in rows:
        equity = row['account']['equity']
        equity_peak = max(equity_peak, equity)
        maximum_drawdown = max(maximum_drawdown, equity_peak-equity)
        stamp = row['status'].get('updated_at')
        if stamp:
            maximum_status_lag = max(maximum_status_lag,
                (datetime.fromisoformat(row['observed_at'])-datetime.fromisoformat(stamp)).total_seconds())
    summary = dict(started_at=first['observed_at'], latest_at=last['observed_at'],
        minutes=round(elapsed/60, 2), observations=len(rows), raw_observations=raw_count,
        excluded_stale_or_incomplete_observations=raw_count-len(rows),
        equity_change=round(last['account']['equity']-first['account']['equity'], 2),
        balance_change=round(last['account']['balance']-first['account']['balance'], 2),
        maximum_equity_drawdown=round(maximum_drawdown, 2),
        maximum_status_lag_seconds=round(maximum_status_lag, 2),
        main_realized_change=round(last['status']['pnl']['realized']-first['status']['pnl']['realized'], 2),
        main_total_change=round(last['status']['pnl']['total']-first['status']['pnl']['total'], 2),
        wins=sum(trade['profit'] > 0 for trade in closed), losses=sum(trade['profit'] < 0 for trade in closed),
        gross_gains=round(gains, 2), gross_losses=round(losses, 2),
        profit_factor=round(gains/losses, 3) if losses else None,
        open_positions=last['positions'],
        latency_median_ms=statistics.median(latencies) if latencies else None,
        latency_p95_ms=sorted(latencies)[min(len(latencies)-1, int(len(latencies)*.95))] if latencies else None,
        common_entry_blocks=blocks.most_common(8), advisor_error_samples=dict(errors),
        closed_trades=closed, observed_excursions=excursions)
    (folder/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    result = summarize(args.folder)
    print(json.dumps({key: value for key, value in result.items() if key not in
                      ('open_positions', 'closed_trades', 'observed_excursions', 'common_entry_blocks')}, indent=2))
