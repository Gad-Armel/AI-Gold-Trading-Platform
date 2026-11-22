"""Causal feature audit of recorded entries; filtering is not a portfolio replay."""
import bisect
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def metrics(rows):
    gains = sum(max(0, r['profit']) for r in rows)
    losses = -sum(min(0, r['profit']) for r in rows)
    return dict(trades=len(rows), net=round(gains-losses, 2),
                profit_factor=round(gains/losses, 3) if losses else None)


def main():
    observations, trades = [], {}
    for folder in sys.argv[1:]:
        path = Path(folder)
        for line in (path/'observations.jsonl').open(encoding='utf-8'):
            row = json.loads(line)
            if 'status' not in row or 'candles' not in row:
                continue
            observations.append(row)
            for name, lane in row['status'].get('lanes', {}).items():
                for t in lane.get('closed_trades', []):
                    trades[t['position_id']] = dict(t, horizon=name)
    observations.sort(key=lambda r: epoch(r['observed_at']))
    times = [epoch(r['observed_at']) for r in observations]
    entries = {}
    for line in (ROOT/'data/demo/gold_consensus_demo_journal.jsonl').open(encoding='utf-8'):
        r = json.loads(line)
        if r.get('record_type') == 'HORIZON_OPEN' and r.get('success'):
            entries[r['order']] = r
    rows = []
    for ticket, trade in sorted(trades.items(), key=lambda p: p[1]['opened_at']):
        entry = entries.get(ticket)
        if not entry:
            continue
        now = epoch(entry['timestamp_utc'])
        i = bisect.bisect_right(times, now)-1
        if i < 0 or now-times[i] > 35:
            continue
        obs = observations[i]
        frames = {}
        for frame, seconds in [('M1', 60), ('M5', 300)]:
            frames[frame] = [b for b in obs['candles'][frame]
                             if b['time']-10800+seconds <= now]
        bars = frames['M1']
        if len(bars) < 15 or len(frames['M5']) < 4:
            continue
        sign = 1 if entry['direction'] == 'BUY' else -1
        spread = obs['status']['market']['ask']-obs['status']['market']['bid']
        price = entry['entry_price']
        atr = sum(max(b['high']-b['low'], abs(b['high']-p['close']), abs(b['low']-p['close']))
                  for p, b in zip(bars[-15:-1], bars[-14:]))/14
        structure = min(b['low'] for b in bars[-3:])-spread if sign == 1 else max(b['high'] for b in bars[-3:])+spread
        local_risk = sign*(price-structure)
        travel = sum(abs(b['close']-p['close']) for p, b in zip(bars[-7:-1], bars[-6:]))
        efficiency = abs(bars[-1]['close']-bars[-7]['close'])/travel if travel else 0
        scalp = obs['status']['lanes']['SCALP']['decision']
        candle_body = sign*(bars[-1]['close']-bars[-1]['open'])
        rows.append(dict(ticket=ticket, horizon=trade['horizon'], opened_at=trade['opened_at'],
            closed_at=trade['closed_at'], direction=entry['direction'], entry_price=trade['entry_price'],
            profit=trade['profit'], evidence=entry['evidence'],
            analysis_risk=round(abs(price-entry['analysis_sl']), 4),
            actual_rr=round(abs(entry['analysis_tp']-price)/5, 4),
            local_risk=round(local_risk, 4), atr=round(atr, 4),
            extension_atr=round(sign*(price-bars[-1]['close'])/atr, 4),
            efficiency=round(efficiency, 4), candle_agrees=candle_body > 0,
            m5_agrees=sign*(frames['M5'][-1]['close']-frames['M5'][-3]['close']) > 0,
            scalp_opposes=(scalp['dominant_bias'] in ('BUY', 'SELL')
                           and scalp['dominant_bias'] != entry['direction'] and scalp['evidence'] >= 70)))
    rules = dict(baseline=lambda r: True, risk_fits=lambda r: 0 < r['local_risk'] <= 5,
                 no_chase=lambda r: r['extension_atr'] <= 1,
                 m5_aligned=lambda r: r['m5_agrees'],
                 directional_path=lambda r: r['efficiency'] >= .3,
                 leading_alignment=lambda r: not r['scalp_opposes'],
                 actual_reward_risk=lambda r: r['actual_rr'] >= .7)
    output = ROOT/'data/research/entry_efficiency'
    output.mkdir(parents=True, exist_ok=True)
    with (output/'recorded_entry_features.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    report = {'note': 'Diagnostic trade subsets only; not out-of-sample or counterfactual portfolio returns.',
              'rules': {name: {lane: metrics([r for r in rows if (lane == 'ALL' or r['horizon'] == lane) and fn(r)])
                               for lane in ('ALL', 'SCALP', 'INTRADAY', 'SWING')} for name, fn in rules.items()}}
    accepted, rejected = [], []
    for row in rows:
        now = epoch(row['opened_at'])
        active = [p for p in accepted if epoch(p['closed_at']) > now and p['direction'] == row['direction']]
        obs = observations[bisect.bisect_right(times, now)-1]
        sign = 1 if row['direction'] == 'BUY' else -1
        bid, ask = obs['status']['market']['bid'], obs['status']['market']['ask']
        spread = ask-bid
        fresh_m5 = [b for b in obs['candles']['M5'] if b['time']-10800+300 <= now]
        confirmed = (not active or (fresh_m5 and fresh_m5[-1]['time']-10800 >= max(epoch(p['opened_at']) for p in active)
                     and sign*(fresh_m5[-1]['close']-fresh_m5[-1]['open']) > 0
                     and all(sign*((bid if sign == 1 else ask)-p['entry_price']) >= 2*spread for p in active)))
        (accepted if confirmed else rejected).append(row)
    report['staged_exposure'] = dict(accepted=metrics(accepted), rejected=metrics(rejected),
                                    tickets=[r['ticket'] for r in accepted])
    (output/'recorded_audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
