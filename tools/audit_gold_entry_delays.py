"""Observed signal-to-entry diagnostics; no counterfactual trades or fitting."""
import bisect
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/research/entry_efficiency'


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def main():
    observations=[]
    for path in sorted((ROOT/'data/monitoring').glob('*/observations.jsonl')):
        for line in path.open(encoding='utf-8'):
            row=json.loads(line)
            if row.get('status',{}).get('lanes') and row['status'].get('market'):
                observations.append(row)
    observations.sort(key=lambda row:epoch(row['observed_at']))
    times=[epoch(row['observed_at']) for row in observations]
    features={row['ticket']:row for row in csv.DictReader((OUT/'recorded_entry_features.csv').open())}
    closed={}
    for obs in observations:
        for lane,item in obs['status']['lanes'].items():
            for trade in item.get('closed_trades',[]):
                closed[str(trade['position_id'])]=dict(trade,horizon=lane)
    entries={}
    for line in (ROOT/'data/demo/gold_consensus_demo_journal.jsonl').open(encoding='utf-8'):
        row=json.loads(line)
        if row.get('record_type')=='HORIZON_OPEN' and row.get('success'):
            entries[str(row['order'])]=row
    rows=[]
    for ticket,trade in sorted(closed.items(),key=lambda item:item[1]['opened_at']):
        if ticket not in entries:
            continue
        entry=entries[ticket]
        at=epoch(entry['timestamp_utc'])
        end=bisect.bisect_right(times,at)-1
        if end<0 or at-times[end]>35:
            continue
        horizon=trade['horizon'];direction=entry['direction'];sign=1 if direction=='BUY' else -1
        start=end
        # Ignore occupied observations: waiting while already holding a lane
        # is not evidence of an avoidable execution delay.
        def usable(index):
            lane=observations[index]['status']['lanes'].get(horizon,{})
            decision=lane.get('decision',{})
            return (not lane.get('positions') and decision.get('dominant_bias')==direction
                    and decision.get('evidence',0)>=15)
        if not usable(end):
            continue
        while start>0 and times[start]-times[start-1]<=45 and usable(start-1):
            start-=1
        censored=start==0 or times[start]-times[start-1]>45
        first=observations[start]['status']['market']
        first_price=first['ask'] if sign==1 else first['bid']
        lane=observations[end]['status']['lanes'][horizon]
        conflicts=[c['advisor'] for c in lane['decision'].get('contributors',[])
                   if c.get('source_usable') and c.get('bias') in ('BUY','SELL')
                   and c['bias']!=direction and c.get('evidence',0)>=70]
        ready=start
        for index in range(start,end+1):
            if not observations[index]['status']['lanes'][horizon].get('entry_timing_ready'):
                ready=index+1
        row=dict(ticket=ticket,horizon=horizon,opened_at=trade['opened_at'],profit=trade['profit'],
            observed_signal_age_seconds=round(at-times[start],2),signal_left_censored=censored,
            observed_ready_age_seconds=round(at-times[ready],2) if ready<=end else None,
            pre_entry_observation_age_seconds=round(at-times[end],2),
            price_travel_before_entry=round(sign*(entry['entry_price']-first_price),3),
            opposing_strong_sources=conflicts,
            last_entry_blocks=lane.get('entry_timing_blocks',[]),
            last_execution=lane.get('last_execution',{}),
            ready_run_execution_results=([observations[index]['status']['lanes'][horizon].get('last_execution',{})
                for index in range(ready,end+1)] if ready<=end else []),
            signal_age_at_last_observation=lane.get('signal_age_seconds'),
            recorded_local_risk=float(features[ticket]['local_risk']) if ticket in features else None)
        rows.append(row)
    groups=[]
    for horizon in ('SCALP','INTRADAY','SWING','ALL'):
        subset=[r for r in rows if horizon=='ALL' or r['horizon']==horizon]
        uncensored=[r for r in subset if not r['signal_left_censored']]
        groups.append(dict(horizon=horizon,trades=len(subset),uncensored_signals=len(uncensored),
            median_observed_signal_age=statistics.median([r['observed_signal_age_seconds'] for r in uncensored]) if uncensored else None,
            median_price_travel=statistics.median([r['price_travel_before_entry'] for r in uncensored]) if uncensored else None,
            strong_source_conflicts=sum(bool(r['opposing_strong_sources']) for r in subset),
            ready_observations_before_entry=sum(r['observed_ready_age_seconds'] is not None for r in subset)))
    report=dict(groups=groups,rows=rows,limitations=[
        'Diagnostic of actually recorded entries only; not chronological holdout or a counterfactual portfolio.',
        '15-second observation cadence cannot establish precise signal onset or millisecond execution latency.',
        'Signal runs exclude occupied lanes and break at observation gaps over 45 seconds.',
        'Signal age includes legitimate candle confirmation, cooldown, cost and freshness waits.',
        'Price travel is relative to the first observed executable quote, not the attainable historical fill.',
        'Mixed deployed policies and left-censored runs limit causal attribution; missing pre-entry records are excluded.'])
    (OUT/'entry_delay_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(groups=groups,matched_trades=len(rows)),indent=2))


if __name__=='__main__':
    main()
