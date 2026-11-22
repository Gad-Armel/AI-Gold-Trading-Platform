"""Predefined sensitivity audit of the hourly challenger, without retuning."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_gold_adaptive import features, evaluate, metrics


def main():
    root=Path('data/research/xauusd_audit')
    raw=pd.read_csv(root/'H1.csv').sort_values('time').drop_duplicates('time').reset_index(drop=True)
    x,atr=features(raw);keep=x.notna().all(axis=1)&(atr>0)
    raw,x,atr=raw[keep].reset_index(drop=True),x[keep].reset_index(drop=True),atr[keep].reset_index(drop=True)
    bars={k:raw[k].to_numpy() for k in raw};xx={k:x[k].to_numpy() for k in x};aa=atr.to_numpy()
    n=len(raw); start=int(n*.8); result={'frozen_parameters':True,'retuned_after_holdout':False,'cost_stress':{},'time_blocks':[]}
    for cost in (1.,2.,4.):
        trades=evaluate(bars,xx,aa,start,n,24,'adaptive',stress=cost)
        result['cost_stress'][str(cost)]=metrics(trades)
    for a,b in zip(np.linspace(100,n,6,dtype=int)[:-1],np.linspace(100,n,6,dtype=int)[1:]):
        result['time_blocks'].append(dict(start_broker_clock=pd.to_datetime(raw.time.iloc[a],unit='s').isoformat(),
            end_broker_clock=pd.to_datetime(raw.time.iloc[b-1],unit='s').isoformat(),
            fixed=metrics(evaluate(bars,xx,aa,a,b,24,'fixed')),
            adaptive=metrics(evaluate(bars,xx,aa,a,b,24,'adaptive'))))
    trades=evaluate(bars,xx,aa,start,n,24,'adaptive');pnl=np.array([t[0] for t in trades]);rng=np.random.default_rng(91)
    blocks=[pnl[i:i+10] for i in range(0,len(pnl),10) if len(pnl[i:i+10])==10]
    means=[float(np.concatenate([blocks[j] for j in rng.integers(0,len(blocks),len(blocks))]).mean()) for _ in range(2000)]
    result['holdout_block_bootstrap_mean_95_interval']=np.quantile(means,[.025,.975]).tolist()
    result['limitations']='Post-selection robustness audit, not a new independent holdout. Omits swap and commission, assumes bid-bar fills.'
    (root/'H1_stress.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
