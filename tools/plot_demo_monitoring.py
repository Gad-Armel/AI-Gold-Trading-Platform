"""Export main-bot live P/L evidence as a standalone PNG."""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from summarize_demo_monitoring import fresh_status


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    rows = []
    for line in (args.folder/'observations.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
            if row.get('status', {}).get('pnl', {}).get('available') and fresh_status(row):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    lagos = timezone(timedelta(hours=1))
    if not rows:
        parser.error('No fresh monitoring status with available P/L in this folder.')
    times = [datetime.fromisoformat(row['observed_at']).astimezone(lagos) for row in rows]
    baseline = rows[0]['status']['pnl']
    realized = [row['status']['pnl']['realized']-baseline['realized'] for row in rows]
    total = [row['status']['pnl']['total']-baseline['total'] for row in rows]
    fig, (ax, market_ax) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
    ax.plot(times, total, label='Realized + floating change', color='#2874a6', linewidth=1.5)
    ax.step(times, realized, label='Realized change', color='#d35400', linewidth=1.6, where='post')
    ax.axhline(0, color='#777777', linewidth=.8)
    ax.set(title='Main demo bot — observed P/L change', ylabel='USD since monitoring baseline')
    bids, asks = [], []
    for row in rows:
        age = row.get('status', {}).get('market_health', {}).get('quote_age_seconds')
        tick = row.get('tick') or {}
        fresh = isinstance(age, (int, float)) and 0 <= age <= 2
        bids.append(tick.get('bid', float('nan')) if fresh else float('nan'))
        asks.append(tick.get('ask', float('nan')) if fresh else float('nan'))
    market_ax.plot(times, bids, label='Fresh bid', color='#2874a6', linewidth=1)
    market_ax.plot(times, asks, label='Fresh ask', color='#d35400', linewidth=1, alpha=.7)
    if not any(math.isfinite(price) for price in bids + asks):
        market_ax.text(.5, .5, 'No fresh executable quotes observed',
                       transform=market_ax.transAxes, ha='center', va='center')
        market_ax.set_yticks([])
    market_ax.set(ylabel='XAUUSD price', xlabel=f'{times[0]:%B %d, %Y} · Lagos time (UTC+1)',
                  title='Observed quotes; stale or missing data leave gaps')
    market_ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=lagos))
    market_ax.grid(alpha=.2)
    market_ax.legend(loc='best')
    ax.grid(alpha=.2)
    ax.legend(loc='best')
    fig.savefig(args.folder/'performance.png', dpi=160)
    plt.close(fig)
    print(args.folder/'performance.png')
