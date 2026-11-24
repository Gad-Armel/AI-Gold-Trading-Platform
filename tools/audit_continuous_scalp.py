"""Offline quote replay and chronological ML experiment. Never connects to MT5.

The forecast experiment labels 30-second continuation, not trade profitability.
No model is promoted or loaded by the execution runner from this report.
"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import json
import hashlib
import time
from datetime import datetime
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from services.research.gold_micro_flow import MicroFlow
from services.research.gold_horizon_policy import _flow_primary_decision
from config import gold_consensus_settings as settings


def stamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def chronological_split(times, target_times):
    """Last 40% is untouched; purge observations whose labels reach that period."""
    boundary=times[int(len(times)*.6)]
    return np.flatnonzero(target_times < boundary), np.flatnonzero(times >= boundary), boundary


def main():
    directory=ROOT/'data/research/gold_forward'
    files=sorted(directory.glob('quotes_*.jsonl'))
    quotes=[]; invalid=0; manifest=[]
    for path in files:
        content=path.read_bytes()
        manifest.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(content).hexdigest(),bytes=len(content)))
        for line in content.decode('utf-8').splitlines():
            try:
                row=json.loads(line)
                quote_time=float(row['broker_time_msc'])/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS
                observed=stamp(row['observed_at'])
                bid,ask=float(row['bid']),float(row['ask'])
                if not all(np.isfinite(x) for x in (observed,quote_time,bid,ask)) or bid <= 0 or ask < bid:
                    raise ValueError('invalid')
                quotes.append((observed,quote_time,bid,ask))
            except (ValueError,TypeError,KeyError): invalid+=1
    quotes=sorted(set(quotes))
    engine=MicroFlow(); samples=[]; ready=0; stale=0; directional=0
    started=time.perf_counter()
    for index,(observed,quote_time,bid,ask) in enumerate(quotes):
        engine.observe(now=observed,quote_time=quote_time,bid=bid,ask=ask)
        flow=engine.read(now=observed)
        if not 0 <= observed-quote_time <= settings.ENTRY_MAX_QUOTE_AGE_SECONDS: stale+=1
        if not flow['available']: continue
        ready+=1
        if flow['bias'] in ('BUY','SELL'): directional+=1
        # Features use only the quotes observed at or before this instant.
        features=[flow['pressure'],flow['efficiency'],flow['acceleration'],ask-bid,flow['spread_expansion']]
        for duration in (6.,12.,30.):
            window=flow['windows'].get(str(duration),{})
            features += [window.get('two_sided_move_spreads',0.),window.get('efficiency',0.),
                         float(bool(window))]
        samples.append((index,features,flow['bias']))
    elapsed=time.perf_counter()-started
    observed=np.array([q[0] for q in quotes]); quote_times=np.array([q[1] for q in quotes])
    bids=np.array([q[2] for q in quotes]); asks=np.array([q[3] for q in quotes])
    # Segments prohibit labels spanning a feed outage or stale observations.
    bad=np.array([not 0 <= q[0]-q[1] <= 2 for q in quotes],dtype=int)
    gaps=np.r_[True,np.diff(observed)>settings.MICRO_FLOW_MAX_SAMPLE_GAP_SECONDS]
    segments=np.cumsum(gaps|bad.astype(bool))
    x=[]; y=[]; indices=[]; targets=[]; biases=[]
    for index,features,bias in samples:
        target=int(np.searchsorted(observed,observed[index]+30))
        if target >= len(quotes): continue
        if (observed[target]-observed[index]>32 or segments[index]!=segments[target]
                or bad[target] or quote_times[target]<=quote_times[index]): continue
        x.append(features); y.append(bids[target]-bids[index]);indices.append(index);targets.append(target);biases.append(bias)
    forecast={'available':False,'reason':'Insufficient continuously observed 30-second labels'}
    if len(x)>=200:
        x=np.array(x); y=np.array(y); indices=np.array(indices); targets=np.array(targets)
        train,test,boundary=chronological_split(observed[indices],observed[targets])
        if len(train)>=100 and len(test)>=50:
            model=make_pipeline(StandardScaler(),Ridge(alpha=100.))
            model.fit(x[train],y[train]); prediction=model.predict(x[test])
            # Comparison on identical held-out observations, including a zero-change baseline.
            rows=[]
            for block in np.array_split(np.arange(len(test)),4):
                rows.append(dict(examples=len(block),ridge_mae=float(np.abs(prediction[block]-y[test[block]]).mean()),
                    zero_change_mae=float(np.abs(y[test[block]]).mean())))
            chosen=[]; next_entry=-float('inf')
            # Diagnostic only: flow-selected, non-overlapping 30-second holds,
            # actual recorded bid/ask and .05 price slippage on each fill.
            # Not the production strategy: no candle/news/risk/margin simulation.
            for sample_index in test:
                i,j=indices[sample_index],targets[sample_index]
                if observed[i]<next_entry or asks[i]-bids[i]>.35: continue
                side=biases[sample_index]
                if side not in ('BUY','SELL'): continue
                pnl=(bids[j]-asks[i]-.10) if side=='BUY' else (bids[i]-asks[j]-.10)
                chosen.append(float(pnl));next_entry=observed[j]
            forecast=dict(available=True,algorithm='StandardScaler + Ridge(alpha=100), fixed before evaluation',
                target='Executable bid change 30 seconds ahead; USD per ounce, not a trade outcome',
                training_examples=len(train),test_examples=len(test),purged_examples=len(x)-len(train)-len(test),
                training_label_end=float(observed[targets[train]].max()),test_start=float(observed[indices[test]].min()),
                ridge_mae=float(np.abs(prediction-y[test]).mean()),zero_change_mae=float(np.abs(y[test]).mean()),
                blocks=rows,nonoverlapping_flow_hold_diagnostic=dict(samples=len(chosen),
                    net_usd_for_one_ounce=sum(chosen),mean_usd=float(np.mean(chosen)) if chosen else None),
                promoted=False,reason='Single retrospective experiment on sparse recordings; no executable strategy validation')
    policies={'recorded_scalp_decisions':0,'old_consensus_allowed':0,'flow_authority_allowed':0}
    for path in sorted(directory.glob('decisions_*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row.get('horizon')!='SCALP':continue
            d=row['decision']; contributors=d.get('contributors',[])
            if len(contributors)!=3:continue
            policies['recorded_scalp_decisions']+=1
            flow=next((c for c in contributors if c['advisor']=='MT5_TICK_FLOW'),{})
            direction=flow.get('bias')
            strong=[c for c in contributors if c.get('source_usable',True) and c.get('bias')==direction and c.get('evidence',0)>=82]
            if flow in strong and len(strong)>=2 and direction in ('BUY','SELL'):policies['old_consensus_allowed']+=1
            # Unit ATR isolates signal authority only. Actual M1 levels and all
            # timing/news/cost gates are intentionally excluded from this count.
            candidate=_flow_primary_decision(contributors,settings.HORIZON_LANES['SCALP'],1.,float(row['ask']))
            if candidate['dominant'] in ('BUY','SELL') and not candidate['blocks']: policies['flow_authority_allowed']+=1
    report=dict(quote_files=manifest,
        quotes=len(quotes),invalid_rows=invalid,stale_quotes=stale,flow_available=ready,directional_flow=directional,
        replay_seconds=elapsed,microseconds_per_observation=elapsed/max(1,len(quotes))*1e6,
        labelled_examples=len(x),forecast=forecast,policy_authority_only=policies,
        limitations=['Recorded decisions are sampled, not all loop cycles. Gate counts are not fill counts.',
            'Overlapping 30-second labels are correlated; no independent-trade significance claim.',
            'Flow-hold diagnostic omits stops, margin, full fees, news and production entry gates.',
            'Existing data helped design thresholds; this is development evidence, not pristine validation.',
            'No model or strategy is promoted by this script.'])
    target=ROOT/'data/research/continuous_scalp';target.mkdir(parents=True,exist_ok=True)
    (target/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='quote_files'},indent=2))


if __name__=='__main__':main()
