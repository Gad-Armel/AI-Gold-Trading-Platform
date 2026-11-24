"""Four fixed entry hypotheses on existing tick labels; no orders or model fitting."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
from research_gold_tick_entries import ROOT,performance


def main():
    data=pd.concat([pd.read_pickle(p) for p in sorted((ROOT/'tick_datasets').glob('*.pkl'))],
                   ignore_index=True).sort_values('feature_epoch').reset_index(drop=True)
    days=sorted(data.day.unique())
    train=days[:int(len(days)*.6)]
    validation=days[int(len(days)*.6):int(len(days)*.8)]
    biases=data[['c_m1_bias','c_m5_bias','c_m15_bias']].to_numpy()
    majority=np.where((biases==1).sum(axis=1)>=2,1,
                      np.where((biases==-1).sum(axis=1)>=2,-1,0))
    m1=data.c_m1_bias.to_numpy().astype(int)
    hypotheses={'closed_candle_majority':majority,'early_m1_direction':m1}
    for name,direction in list(hypotheses.items()):
        # Fixed sign agreement at two already recorded flow windows. No fitted
        # magnitude, confidence threshold, timing search or holdout selection.
        aligned=(direction*data.pressure_6.to_numpy()>0)&(direction*data.pressure_30.to_numpy()>0)
        hypotheses[name+'_tick_aligned']=np.where(aligned,direction,0)
    results=[]
    for name,direction in hypotheses.items():
        row={'hypothesis':name}
        for label,split in [('training',train),('validation',validation)]:
            mask=data.day.isin(split).to_numpy()
            row[label]={str(stress):performance(data[mask],direction[mask],np.ones(mask.sum()),0.,stress=stress)
                        for stress in (False,True)}
        v=row['validation']
        row['passes_validation']=(v['False']['trades']>=100 and (v['False']['profit_factor'] or 0)>=1.1
            and v['True']['trades']>=100 and (v['True']['profit_factor'] or 0)>=1.05)
        results.append(row)
    report=dict(training_days=train,validation_days=validation,results=results,
        later_holdout_evaluated=False,live_approved=False,limitations=[
            'Four fixed causal rules, no model fitting or threshold search.',
            'Full-history EMA directions approximate Advisor 1; strength scores and live adaptive exits omitted.',
            'M1 direction is an early-response hypothesis, not an edit to standalone Advisor 1.',
            'Actual historical bid/ask paths, 100ms latency, $.05 per-side slippage, $5 stop and 180s exit.',
            'Non-overlapping positions, 30s re-entry pause; no fees, financing or liquidity/depth.',
            'Validation days were already inspected with other candidates, so this is exploratory evidence.',
            'Final holdout untouched; no rule is enabled for execution.'])
    (ROOT/'tick_alignment_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
