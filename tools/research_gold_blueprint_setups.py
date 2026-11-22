"""Frozen blueprint pattern experiment; no broker access or order authority."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.research.gold_scalp_setups import setup_features

OUT = ROOT/'data/research/blueprint_review_20261009'
SOURCE = ROOT/'data/research/entry_efficiency'
FAMILIES = ('pullback', 'sweep', 'breakout')


def simulate(times, bids, asks, events, *, stress=1.0):
    trades = []
    busy_until = 0
    for row in events.itertuples(index=False):
        signal = int(row.available*1000)
        executed = signal+100
        if executed < busy_until:
            continue
        entry_i = np.searchsorted(times, executed, side='right')-1
        deadline = executed+300_000
        last = np.searchsorted(times, deadline, side='right')-1
        if (entry_i < 0 or last < entry_i or deadline > times[-1]
                or executed-times[entry_i] > 2000 or deadline-times[last] > 15000):
            continue
        spread = asks[entry_i]-bids[entry_i]
        if not 0 <= spread <= .75:
            continue
        side = row.side
        slip = .05*stress
        entry = asks[entry_i]+(stress-1)*spread+slip if side == 1 else bids[entry_i]-slip
        begin = np.searchsorted(times, executed, side='right')
        path = bids[begin:last+1] if side == 1 else asks[begin:last+1]+(stress-1)*(asks-bids)[begin:last+1]
        movement = side*(path-entry)
        hit = np.flatnonzero((movement <= -5) | (movement >= 6))
        index = begin+int(hit[0]) if len(hit) else last
        exit_price = bids[index] if side == 1 else asks[index]+(stress-1)*(asks[index]-bids[index])
        # One-ounce exposure: .01 lot * measured standard 100oz contract.
        profit = side*(exit_price-entry)-slip-.07*stress
        exit_epoch = times[index]/1000 if len(hit) else deadline/1000
        trades.append(dict(entry_epoch=executed/1000, exit_epoch=exit_epoch,
                           side=int(side), profit=float(profit)))
        busy_until = int(exit_epoch*1000)+30_000
    return trades


def performance(trades):
    profits = np.array([t['profit'] for t in trades])
    wins = profits[profits > 0].sum()
    losses = -profits[profits < 0].sum()
    equity = np.r_[0, profits.cumsum()]
    return dict(trades=len(profits), net=round(float(profits.sum()), 2),
                mean=round(float(profits.mean()), 4) if len(profits) else None,
                profit_factor=float(wins/losses) if losses else None,
                win_rate=float((profits > 0).mean()) if len(profits) else None,
                max_closed_drawdown=round(float((np.maximum.accumulate(equity)-equity).max()), 2))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted((SOURCE/'historical_ticks').glob('*.npz'))
    days = [p.stem for p in files]
    split_a, split_b = int(len(days)*.6), int(len(days)*.8)
    groups = dict(development=days[:split_a], validation=days[split_a:split_b], holdout=days[split_b:])
    hypothesis = dict(frozen_at=datetime.now(timezone.utc).isoformat(), groups=groups,
        families=FAMILIES, parameters=dict(stop_usd=5, target_usd=6, horizon_seconds=300,
        latency_ms=100, slippage_each_side=.05, commission_round_trip_per_001=.07,
        spread_cap=.75, post_exit_seconds=30),
        sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (Path(__file__), ROOT/'services/research/gold_scalp_setups.py')},
        acceptance=dict(minimum_validation_trades=100, base_pf=1.10, stress_pf=1.05),
        limitations=['Historical dates have been inspected by earlier research; not a blind experiment.',
                     'Fixed 300s/$6 target exits isolate setup quality, not full production adaptive exits.',
                     'One position per family; no averaging, scaling, financing, news or liquidity model.',
                     'Commission is conservative assumed $7/lot round trip, not a broker tariff.',
                     'Bid/ask already include spread; it is not subtracted a second time.',
                     'No live promotion; a future independent evaluation remains necessary.'])
    (OUT/'setup_hypothesis.json').write_text(json.dumps(hypothesis, indent=2))
    m1 = pd.read_csv(SOURCE/'broker_bars/M1.csv')
    m5 = pd.read_csv(SOURCE/'broker_bars/M5.csv')
    features = setup_features(m1, m5, broker_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
    outcomes = {}
    selected = []
    for group in ('development', 'validation', 'holdout'):
        if group == 'holdout' and not selected:
            break
        buckets = {f:{'base':[], 'stress':[]} for f in FAMILIES if group != 'holdout' or f in selected}
        for path in files:
            if path.stem not in groups[group]:
                continue
            with np.load(path) as data:
                times, bids, asks = data['utc_time_msc'], data['bid'], data['ask']
                if not len(times):
                    print(json.dumps(dict(group=group, day=path.stem, status='NO_TICKS')), flush=True)
                    continue
                sample = features[(features.available*1000 >= times[0]) &
                                  (features.available*1000 <= times[-1])]
                for family in buckets:
                    events = sample[sample[family+'_side'] != 0].assign(side=lambda x:x[family+'_side'])
                    for name, cost in [('base',1.), ('stress',1.5)]:
                        buckets[family][name].extend(simulate(times, bids, asks, events, stress=cost))
            print(json.dumps(dict(group=group, day=path.stem,
                                  trades={f:len(buckets[f]['base']) for f in buckets})), flush=True)
        outcomes[group] = {f:{name:performance(trades) for name,trades in values.items()}
                           for f,values in buckets.items()}
        if group == 'validation':
            selected = [f for f,values in outcomes[group].items()
                        if values['base']['trades'] >= 100
                        and (values['base']['profit_factor'] or 0) >= 1.10
                        and values['stress']['trades'] >= 100
                        and (values['stress']['profit_factor'] or 0) >= 1.05]
    report = dict(hypothesis=hypothesis, outcomes=outcomes,
                  validation_qualified_families=selected, holdout_evaluated=bool(selected),
                  live_approved=False, result='RESEARCH_ONLY')
    (OUT/'setup_results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(outcomes, indent=2), flush=True)


if __name__ == '__main__':
    main()
