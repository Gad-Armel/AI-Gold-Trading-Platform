"""Counterfactual exit-only audit, not a strategy/portfolio backtest."""
import bisect
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/research/entry_efficiency'


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def metrics(rows, field):
    gains = sum(max(0, r[field]) for r in rows)
    losses = -sum(min(0, r[field]) for r in rows)
    return dict(trades=len(rows), net=round(gains-losses, 2),
                profit_factor=round(gains/losses, 4) if losses else None)


def main():
    quotes = []
    for line in (ROOT/'data/research/gold_forward/quotes_20261008.jsonl').open():
        q = json.loads(line)
        if 0 <= q['quote_age_seconds'] <= 15 and 0 < q['bid'] <= q['ask']:
            quotes.append((epoch(q['observed_at']), q['bid'], q['ask']))
    quotes.sort()
    times = [q[0] for q in quotes]
    entries = {}
    for line in (ROOT/'data/demo/gold_consensus_demo_journal.jsonl').open():
        r = json.loads(line)
        if r.get('record_type') == 'HORIZON_OPEN' and r.get('success'):
            entries[str(r['order'])] = r
    rows = []
    for trade in csv.DictReader((OUT/'recorded_entry_features.csv').open()):
        entry = entries[trade['ticket']]
        start, end = epoch(trade['opened_at']), epoch(trade['closed_at'])
        path = quotes[bisect.bisect_left(times, start):bisect.bisect_right(times, end)]
        if not path:
            continue
        maximum_gap = max([path[0][0]-start, end-path[-1][0]]+
                          [b[0]-a[0] for a, b in zip(path, path[1:])])
        direction = trade['direction']
        sign = 1 if direction == 'BUY' else -1
        price = float(trade['entry_price'])
        moves = [sign*((bid if sign == 1 else ask)-price) for _, bid, ask in path]
        row = dict(ticket=trade['ticket'], horizon=trade['horizon'],
                   period='EARLY' if start < epoch('2026-10-08T06:08:30+00:00') else 'LATER',
                   actual=float(trade['profit']), maximum_quote_gap=round(maximum_gap, 3),
                   peak=round(max(moves), 2), trough=round(min(moves), 2))
        stop = float(entry['analysis_sl'])
        hit = next(((at, move) for (at, _, _), move in zip(path, moves)
                    if sign*(price+sign*move-stop) <= 0), None)
        row['analysis_stop_hit'] = hit is not None
        row['analysis_stop_exit'] = round(hit[1]-.05, 2) if hit else row['actual']
        row['exit_delay_seconds'] = round(end-hit[0], 1) if hit else None
        rows.append(row)
    usable = [r for r in rows if r['maximum_quote_gap'] <= 10]
    groups = []
    for period in ('EARLY', 'LATER', 'ALL'):
        for lane in ('SCALP', 'INTRADAY', 'SWING', 'ALL'):
            selected = [r for r in usable if (period == 'ALL' or r['period'] == period)
                        and (lane == 'ALL' or r['horizon'] == lane)]
            groups.append(dict(period=period, lane=lane, actual=metrics(selected, 'actual'),
                               analysis_stop=metrics(selected, 'analysis_stop_exit')))
    report = dict(rows=rows, groups=groups, excluded_quote_gaps=len(rows)-len(usable),
        limitations=['Exit-only diagnostic using already-recorded trades; no changed re-entry opportunities.',
                     'Journal requested entry prices approximate actual fills; hypothetical exits assume $.05 slippage.',
                     'Sampled quotes may miss intragap stop touches; paths with gaps >10 seconds excluded.',
                     'Analysis stop known at entry; quote path is used only to measure subsequent outcomes.',
                     'No policy promotion; both chronological periods previously inspected.'])
    (OUT/'analysis_stop_audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(groups=groups, excluded_quote_gaps=report['excluded_quote_gaps']), indent=2))


if __name__ == '__main__':
    main()
