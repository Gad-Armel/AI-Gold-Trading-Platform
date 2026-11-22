"""Chronological tick/candle entry challenger. Never exports approved models or orders."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import gold_consensus_settings as settings
from services.research.gold_tick_entry_research import tick_features,tick_path_labels
from benchmark_gold_entry_patterns import ROOT,dataset
from research_gold_bidirectional import entry_features


def prepare():
    candles=dataset(include_latest=True)
    candle_features=entry_features(candles).add_prefix('c_')
    candle_features['feature_epoch']=(candles.available-settings.MT5_SERVER_UTC_OFFSET_SECONDS).astype(np.int64)
    pieces=[]
    quality=[]
    for path in sorted((ROOT/'historical_ticks').glob('*.npz')):
        cache=ROOT/'tick_datasets'/(path.stem+'.pkl')
        cache.parent.mkdir(parents=True,exist_ok=True)
        # The version belongs to the causal feature/label implementation, not a
        # model; cached outcomes are still split strictly by their observed day.
        if cache.exists():
            piece=pd.read_pickle(cache)
            pieces.append(piece)
            continue
        with np.load(path) as raw:
            times,bids,asks=raw['utc_time_msc'],raw['bid'],raw['ask']
            if len(times)<1000:
                continue
            features=tick_features(times,bids,asks)
            features=pd.merge_asof(features,candle_features,on='feature_epoch',direction='backward',tolerance=120).dropna()
            normal=tick_path_labels(times,bids,asks,features.feature_epoch.to_numpy())
            stressed=tick_path_labels(times,bids,asks,features.feature_epoch.to_numpy(),stress=1.5)
            valid=normal.valid & stressed.valid
            piece=pd.concat([features.reset_index(drop=True),normal.add_prefix('normal_'),stressed.add_prefix('stress_')],axis=1)
            piece=piece[valid].copy()
            piece['day']=path.stem
            piece.to_pickle(cache)
            quality.append(dict(day=path.stem,ticks=len(times),features=len(features),complete_labels=int(valid.sum())))
            print(json.dumps(quality[-1]),flush=True)
            pieces.append(piece)
    if not pieces:
        raise RuntimeError('No complete historical tick examples')
    data=pd.concat(pieces,ignore_index=True).sort_values('feature_epoch').reset_index(drop=True)
    return data,quality


def performance(data,choice,expected,threshold,*,stress=False):
    prefix='stress_' if stress else 'normal_'
    trades=[]
    available_after=0
    for i,row in enumerate(data.itertuples(index=False)):
        # Research positions do not overlap. Thirty seconds after a close are
        # reserved for fresh analysis, matching the requested main-bot pause.
        if row.normal_entry_epoch<available_after or expected[i]<threshold or choice[i]==0:
            continue
        side='buy' if choice[i]==1 else 'sell'
        profit=getattr(row,prefix+side+'_profit')
        exited=getattr(row,prefix+side+'_exit_epoch')
        trades.append(dict(day=row.day,profit=profit,entry_epoch=row.normal_entry_epoch,exit_epoch=exited))
        available_after=exited+30
    values=np.array([t['profit'] for t in trades])
    gains=values[values>0].sum();losses=-values[values<0].sum()
    equity=np.r_[0,values.cumsum()]
    return dict(trades=len(trades),net=round(float(values.sum()),2),
        mean=round(float(values.mean()),4) if len(values) else None,
        profit_factor=round(float(gains/losses),4) if losses else None,
        drawdown=round(float((np.maximum.accumulate(equity)-equity).max()),2))


def main(*, augment=None, filename='tick_entry_assessment.json'):
    data,quality=prepare()
    if augment is not None:
        data=augment(data)
    days=sorted(data.day.unique())
    train_days,valid_days=days[:int(len(days)*.6)],days[int(len(days)*.6):int(len(days)*.8)]
    latest_days=days[int(len(days)*.8):]
    inputs=[c for c in data.columns if c not in ('day','feature_epoch') and not c.startswith(('normal_','stress_'))]
    # At least one non-neutral completed-candle view remains required.
    active=(data[['c_m1_bias','c_m5_bias','c_m15_bias']]!=0).any(axis=1)
    training=data.day.isin(train_days)&active
    prediction={}
    for side in ('buy','sell'):
        model=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,min_samples_leaf=200,
            learning_rate=.05,l2_regularization=20,early_stopping=False,random_state=42)
        model.fit(data.loc[training,inputs],data.loc[training,'normal_'+side+'_profit'])
        prediction[side]=model.predict(data[inputs])
    expected=np.maximum(prediction['buy'],prediction['sell'])
    gap=np.abs(prediction['buy']-prediction['sell'])
    choice=np.where(active & (gap>=.25),np.where(prediction['buy']>prediction['sell'],1,-1),0)
    # Diagnose optimism on training/middle days without using the final holdout
    # to select another model or threshold. These overlapping labels are a
    # calibration diagnostic, not a portfolio return or independent trial count.
    calibration={}
    actual=np.where(prediction['buy']>prediction['sell'],data.normal_buy_profit,data.normal_sell_profit)
    for name,split in [('training',train_days),('validation',valid_days)]:
        sample=data.day.isin(split).to_numpy() & (choice!=0)
        rows=[]
        for low,high in [(-np.inf,0.),(0.,.25),(.25,.5),(.5,1.),(1.,2.),(2.,np.inf)]:
            use=sample & (expected>=low) & (expected<high)
            if use.any():
                rows.append(dict(expected_range=[None if not np.isfinite(low) else low,
                                                None if not np.isfinite(high) else high],
                    overlapping_examples=int(use.sum()),predicted_mean=float(expected[use].mean()),
                    realized_mean=float(actual[use].mean()),positive_fraction=float((actual[use]>0).mean())))
        calibration[name]=rows
    validation=[]
    mask=data.day.isin(valid_days)
    for threshold in (0.,.25,.5,1.):
        validation.append(dict(threshold=threshold,
            base=performance(data[mask],choice[mask],expected[mask],threshold),
            stress=performance(data[mask],choice[mask],expected[mask],threshold,stress=True)))
    eligible=[r for r in validation if r['base']['trades']>=100 and (r['base']['profit_factor'] or 0)>=1.1
              and r['stress']['trades']>=100 and (r['stress']['profit_factor'] or 0)>=1.05]
    selected=max(eligible,key=lambda r:r['base']['mean']) if eligible else None
    latest=[]
    if selected:
        mask=data.day.isin(latest_days)
        latest=[dict(cost_stress=stress,**performance(data[mask],choice[mask],expected[mask],
                selected['threshold'],stress=stress>1)) for stress in (1.,1.5)]
    report=dict(examples=len(data),training_examples=int(training.sum()),features=inputs,
        train_days=train_days,validation_days=valid_days,latest_days=latest_days,
        validation=validation,calibration=calibration,selected_threshold=selected['threshold'] if selected else None,
        latest=latest,quality=quality,live_approved=False,limitations=[
            'Chronological day splits; outcome paths stay within each source UTC day, before later splits.',
            'Tick features known at second close; assumed 100ms order latency and $.05 per-side slippage.',
            'Observed bid/ask, first adverse tick stop fills, $5 planned risk, one ounce exposure, 180s time exits.',
            'No fees, financing, news or liquidity/depth; recorded ticks may miss server gaps.',
            'Four thresholds chosen only on middle days; final days used only if validation qualifies.',
            'Historical candles may contain later broker corrections; this is not blind prospective validation.',
            'No model exported, promoted or connected to main-bot execution.'])
    (ROOT/filename).write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('quality','features')},indent=2),flush=True)


if __name__=='__main__':
    main()
