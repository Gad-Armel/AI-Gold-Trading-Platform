"""Chronological, cost-aware candle challenger. Does not execute or promote models.

This is a simplified research strategy, NOT a replay of the three-advisor bot.
Labels and evaluation use identical executable next-open fills and causal exits.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
import joblib

FEATURES = ['trend','momentum','distance','range_atr','volatility_ratio','cost_atr','hour_sin','hour_cos']


def features(frame):
    c = frame.close
    tr = pd.concat([frame.high-frame.low,(frame.high-c.shift()).abs(),(frame.low-c.shift()).abs()],axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14,adjust=False).mean()
    fast, slow = c.ewm(span=12,adjust=False).mean(), c.ewm(span=26,adjust=False).mean()
    hour = pd.to_datetime(frame.time,unit='s',utc=True).dt.hour
    out = pd.DataFrame(dict(trend=(fast-slow)/atr,momentum=c.diff(3)/atr,
        distance=(c-fast)/atr,range_atr=(frame.high-frame.low)/atr,
        volatility_ratio=atr/atr.rolling(100).mean(),cost_atr=frame.spread*.01/atr,
        hour_sin=np.sin(hour*2*np.pi/24),hour_cos=np.cos(hour*2*np.pi/24)))
    return out, atr


def path_return(frame, x, atr, i, direction, policy, horizon, stress=1.0):
    """Bid OHLC, constant entry spread for asks; stop gaps at worse next open.

    No intrabar profit target assumption: the legacy basket was polled, so this
    approximation recognizes its $5 price-distance target at a completed close.
    One ounce equivalent; excludes broker-specific commission and swaps.
    """
    entry_i = i+1
    spread = max(.28, float(frame['spread'][entry_i])*.01)*stress
    cost = spread + .10*stress
    entry = float(frame['open'][entry_i])
    stop_distance = max(1.5*float(atr[i]),cost*3)
    stop = entry-direction*stop_distance
    peak = 0.
    for j in range(entry_i,min(entry_i+horizon,len(atr)-1)):
        adverse = float(frame['low'][j]) if direction == 1 else float(frame['high'][j])
        if direction*(adverse-stop) <= 0:
            fill = min(stop,float(frame['open'][j])) if direction==1 else max(stop,float(frame['open'][j]))
            return direction*(fill-entry)-cost,j
        move = direction*(float(frame['close'][j])-entry)
        peak = max(peak,move)
        invalid = direction*x['trend'][j] < 0 and direction*x['momentum'][j] < 0
        giveback = peak >= atr[j] and peak-move >= 1.5*atr[j] and direction*x['momentum'][j] < 0
        if (policy == 'fixed' and move >= 5) or (policy != 'fixed' and (invalid or giveback)) or j==entry_i+horizon-1:
            return direction*(float(frame['open'][j+1])-entry)-cost,j+1
    return direction*(float(frame['close'][-1])-entry)-cost,len(atr)-1


def metrics(trades):
    pnl=np.array([t[0] for t in trades],dtype=float)
    if not len(pnl):return {'trades':0,'net':0.,'profit_factor':None,'mean':None,'drawdown':0.}
    equity=np.r_[0,np.cumsum(pnl)]
    loss=-pnl[pnl<0].sum()
    return dict(trades=len(pnl),net=round(float(pnl.sum()),2),mean=round(float(pnl.mean()),4),
        win_rate=round(float((pnl>0).mean()),4),profit_factor=round(float(pnl[pnl>0].sum()/loss),4) if loss else None,
        drawdown=round(float((np.maximum.accumulate(equity)-equity).max()),2))


def evaluate(frame,x,atr,start,end,horizon,policy,probs=None,threshold=.5,stress=1.):
    trades=[];i=start
    while i < end-horizon-2:
        direction=1 if x['trend'][i]>.05 and x['momentum'][i]>0 else -1 if x['trend'][i]<-.05 and x['momentum'][i]<0 else 0
        if direction and (probs is None or probs[i] >= threshold):
            pnl,j=path_return(frame,x,atr,i,direction,policy,horizon,stress)
            trades.append((pnl,int(frame['time'][j])));i=j+1
        else:i+=1
    return trades


def main():
    root=Path('data/research/xauusd_audit'); reports={}
    for name,horizon in [('M5',12),('M15',16),('H1',24)]:
        raw=pd.read_csv(root/(name+'.csv')).sort_values('time').drop_duplicates('time').reset_index(drop=True)
        x,atr=features(raw); keep=x.notna().all(axis=1)&(atr>0)
        raw,x,atr=raw[keep].reset_index(drop=True),x[keep].reset_index(drop=True),atr[keep].reset_index(drop=True)
        bars={k:raw[k].to_numpy() for k in raw}; xx={k:x[k].to_numpy() for k in x}; aa=atr.to_numpy()
        n=len(raw);train_end=int(n*.60);valid_end=int(n*.80)
        side=np.where((x.trend>.05)&(x.momentum>0),1,np.where((x.trend<-.05)&(x.momentum<0),-1,0))
        # Direction-normalize market predictors; do not feed future returns as features.
        model_x=x.copy()
        for col in ['trend','momentum','distance']:model_x[col]*=side
        train_idx=[i for i in range(train_end-horizon-2) if side[i]]
        labels=[int(path_return(bars,xx,aa,i,int(side[i]),'adaptive',horizon)[0]>0) for i in train_idx]
        candidates={
            'logistic':make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=500)),
            'histogram':HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,l2_regularization=10,random_state=7),
        }
        results=[];best=None
        for model_name,model in candidates.items():
            model.fit(model_x.iloc[train_idx],labels)
            probability=model.predict_proba(model_x)[:,1]
            for threshold in [.50,.55,.60]:
                stats=metrics(evaluate(bars,xx,aa,train_end,valid_end,horizon,'adaptive',probability,threshold))
                candidate=dict(model=model_name,threshold=threshold,validation=stats)
                results.append(candidate)
                if stats['trades']>=100 and (best is None or stats['net']>best[0]):
                    best=(stats['net'],model_name,model,threshold,probability,candidate)
        result={'rows':n,'train_end_utc':pd.to_datetime(raw.time.iloc[train_end],unit='s',utc=True).isoformat(),
            'test_start_utc':pd.to_datetime(raw.time.iloc[valid_end],unit='s',utc=True).isoformat(),
            'validation_candidates':results,'test':{}}
        for policy in ['fixed','adaptive']:
            result['test'][policy]=metrics(evaluate(bars,xx,aa,valid_end,n,horizon,policy))
        if best:
            _,model_name,model,threshold,probability,choice=best
            selected=evaluate(bars,xx,aa,valid_end,n,horizon,'adaptive',probability,threshold)
            stress=evaluate(bars,xx,aa,valid_end,n,horizon,'adaptive',probability,threshold,2.)
            result['selected']=choice
            result['test']['learned_adaptive']=metrics(selected)
            result['test']['double_cost']=metrics(stress)
            pd.DataFrame(selected,columns=['net_price_return','exit_time']).to_csv(root/(name+'_holdout_trades.csv'),index=False)
            passed=(result['test']['learned_adaptive']['trades']>=100
                and (result['test']['learned_adaptive']['profit_factor'] or 0)>=1.1
                and result['test']['double_cost']['net']>0 and choice['validation']['net']>0)
            result['research_gate_passed']=bool(passed)
            # Research pass is insufficient for execution: calendar/tick replay and forward validation remain.
            result['execution_approved']=False
            joblib.dump(dict(model=model,features=FEATURES,threshold=threshold,timeframe=name,
                execution_approved=False,research_gate_passed=bool(passed),validation=result,
                created_at=pd.Timestamp.now(tz='UTC').isoformat()),root/(name+'_candidate.joblib'))
        reports[name]=result
        print(name,json.dumps(result['test']),flush=True)
    reports['limitations']=['Simplified trend challenger, not full main-bot replay',
        'Spread point assumed 0.01; minimum 0.28 and 0.10 slippage allowance',
        'No historical point-in-time news, swaps or commission; no tick execution replay',
        'Test results never authorize trading; holdout is consumed after this run']
    (root/'model_comparison.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')


if __name__=='__main__':main()
