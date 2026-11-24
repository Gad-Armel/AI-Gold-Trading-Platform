"""Summarize saved live observations without connecting to or trading through MT5."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics


def summarize(rows):
    usable = [r for r in rows if r.get('snapshot')]
    if not usable:
        raise ValueError('No dashboard snapshots')
    snap = usable[-1]['snapshot']
    grouped = defaultdict(dict)
    # Keep fills across snapshots, so a busy feed's rolling 60-deal view cannot
    # silently drop an entry already observed earlier in the run.
    for row in usable:
        for deal in row['snapshot'].get('deals', []):
            grouped[deal['position']][deal['ticket']] = deal
    cohorts = defaultdict(list)
    trades = []
    candles = {c['time']: c for row in usable for c in row['snapshot'].get('candles', [])}
    for ident, fills in grouped.items():
        entries = [d for d in fills.values() if d['entry'] == 'DEAL_ENTRY_IN' and d['owned']]
        exits = sorted((d for d in fills.values() if d['entry'] in ('DEAL_ENTRY_OUT', 'DEAL_ENTRY_OUT_BY')), key=lambda d:(d['time'],int(d['ticket'])))
        if len(entries) != 1 or not exits or sum(d['volume'] for d in exits)+1e-8 < entries[0]['volume']:
            continue
        entry = entries[0]
        net = round(sum(d['net'] for d in fills.values()), 4)
        policy = entry['comment'].split(':')[0]
        stamp = int(datetime.strptime(entry['time'], '%Y.%m.%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp())
        # Wire candle epochs and deal labels use the same broker clock. Do not
        # reinterpret these as actual UTC or infer the unseen intrabar tick path.
        prior = [c for t,c in sorted(candles.items()) if stamp//60*60-300 <= t < stamp//60*60]
        delta = prior[-1]['close']-prior[0]['open'] if len(prior)==5 else None
        trade = {'position': ident, 'policy': policy, 'side': entry['side'], 'entry_server': entry['time'],
                 'net': net, 'exit_reason': exits[-1]['reason'],
                 'preceding_5_closed_m1_change': round(delta,4) if delta is not None else None}
        trades.append(trade);cohorts[policy].append(net)
    performance = {}
    for policy, values in cohorts.items():
        wins = [v for v in values if v>0];losses = [v for v in values if v<0]
        avg_win = statistics.mean(wins) if wins else 0
        avg_loss = -statistics.mean(losses) if losses else 0
        performance[policy] = {'closed':len(values), 'net':round(sum(values),4),
                               'win_rate':round(100*len(wins)/len(values),2),
                               'profit_factor':round(sum(wins)/-sum(losses),4) if losses else None,
                               'average_win':round(avg_win,4), 'average_loss':round(avg_loss,4),
                               'breakeven_win_rate_at_observed_payoffs':round(100*avg_loss/(avg_win+avg_loss),2) if avg_win+avg_loss else None}
    cadence = [(datetime.fromisoformat(b['observed_utc'])-datetime.fromisoformat(a['observed_utc'])).total_seconds() for a,b in zip(rows,rows[1:])]
    spreads = [r['snapshot']['market']['spread'] for r in usable]
    return {'first_utc':rows[0]['observed_utc'], 'last_utc':rows[-1]['observed_utc'],
            'observations':len(rows), 'duration_seconds':sum(cadence), 'errors':sum('error' in r for r in rows),
            'cadence_median_seconds':statistics.median(cadence) if cadence else None,
            'cadence_max_seconds':max(cadence) if cadence else None,
            'states':dict(Counter(r.get('state','error') for r in rows)),
            'sampled_statuses':dict(Counter(r['snapshot']['status'] for r in usable)),
            'median_spread':statistics.median(spreads), 'maximum_spread':max(spreads),
            'cohorts':performance, 'trades':sorted(trades,key=lambda r:r['entry_server']),
            'latest':{k:snap.get(k) for k in ('version','status','locked','risk','kpi','execution','account')},
            'limitations':['35-second observations can miss short trades; fills are reconciled separately.',
                           'Minute candles cannot prove tick MFE/MAE, signal quality or counterfactual execution.',
                           'This is an observational audit, not a profitability backtest.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=[json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
    report=summarize(rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('trades','latest')},indent=2))


if __name__=='__main__':
    main()
