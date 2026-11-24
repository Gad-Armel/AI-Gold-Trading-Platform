"""Offline grouping of overlapping tickets and hypothetical extra-cost stress."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.review_demo_losses import metrics


def epoch(stamp):
    parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Explicit timezone required')
    return parsed.timestamp()


def campaign_summary(trades, open_positions=()):
    intervals = []
    tickets = [trade['position_id'] for trade in trades]+[position['ticket'] for position in open_positions]
    if len(set(tickets)) != len(tickets):
        raise ValueError('Duplicate or unreconciled ticket identity')
    for trade in trades:
        start, end = epoch(trade['opened_at']), epoch(trade['closed_at'])
        profit = float(trade['profit'])
        if end < start or not math.isfinite(profit):
            raise ValueError('Invalid trade interval or profit')
        intervals.append(dict(start=start, end=end, profit=profit, ticket=trade['position_id'], live=False))
    for position in open_positions:
        start = float(position['opened_epoch'])
        if not math.isfinite(start):
            raise ValueError('Invalid live position time')
        intervals.append(dict(start=start, end=float('inf'), profit=0., ticket=position['ticket'], live=True))
    groups = []
    for item in sorted(intervals, key=lambda row: (row['start'], row['end'])):
        if not groups or item['start'] >= groups[-1]['end']:
            groups.append(dict(start=item['start'], end=item['end'], items=[]))
        groups[-1]['items'].append(item)
        groups[-1]['end'] = max(groups[-1]['end'], item['end'])
    settled, unsettled = [], []
    for group in groups:
        pending = any(item['live'] for item in group['items'])
        row = dict(opened_at=datetime.fromtimestamp(group['start'], timezone.utc).isoformat(),
                   closed_at=None if pending else datetime.fromtimestamp(group['end'], timezone.utc).isoformat(),
                   tickets=[item['ticket'] for item in group['items']],
                   closed_tickets=sum(not item['live'] for item in group['items']),
                   profit=round(sum(item['profit'] for item in group['items']), 8))
        (unsettled if pending else settled).append(row)
    return dict(input_closed_trades=metrics(trades), settled_campaigns=metrics(settled),
                campaigns=settled, incomplete_campaigns=unsettled,
                additional_cost_stress={str(cost): metrics([dict(row,
                    profit=row['profit']-cost*row['closed_tickets']) for row in settled])
                                       for cost in (0., .1, .25, .5)},
                limitations=['Temporal overlap defines a campaign, not a proven independent market signal.',
                    'Open-position campaigns are right-censored and excluded from settled metrics.',
                    'Existing broker P/L already includes recovered costs; stress adds hypothetical USD per closed ticket.',
                    'Not a simulation of changed entries, exits, fills or slippage.',
                    'The requested cohort must start flat, or left-censored campaigns require separate reconciliation.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--monitor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    history = json.loads(args.history.read_text(encoding='utf-8'))
    monitor = json.loads(args.monitor.read_text(encoding='utf-8'))
    if monitor.get('positions') is None or monitor.get('account', {}).get('trade_mode') != 0:
        raise ValueError('Reconciled demo position snapshot required')
    if monitor['account'].get('currency') != 'USD':
        raise ValueError('USD account required for the stated extra-cost scenarios')
    if abs(epoch(monitor['observed_at'])-epoch(history['as_of'])) > 30:
        raise ValueError('History and position snapshots must be contemporaneous within thirty seconds')
    offset = float(monitor['status']['config']['broker_utc_offset_seconds'])
    positions = [dict(ticket=position['ticket'], opened_epoch=position['time_msc']/1000-offset)
                 for position in monitor['positions'] if position['magic'] == 631011]
    result = campaign_summary(history['requested_scalp_cohort']['trades'], positions)
    result.update(history_as_of=history['as_of'], positions_as_of=monitor['observed_at'],
                  cohort_started_at=history['requested_scalp_cohort']['opened_on_or_after'], execution_enabled=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in ('campaigns', 'incomplete_campaigns')}, indent=2))


if __name__ == '__main__':
    main()
