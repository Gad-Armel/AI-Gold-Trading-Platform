"""Causal quote features and tick-path labels. Contains no broker connection or orders."""
import numpy as np
import pandas as pd


def tick_features(times_msc, bids, asks, *, cadence_seconds=5):
    if not len(times_msc):
        return pd.DataFrame()
    if np.any(np.diff(times_msc)<0):
        raise ValueError('Ticks must be chronological')
    mid = (bids+asks)/2
    changes = np.diff(mid, prepend=mid[0])
    raw = pd.DataFrame(dict(second=times_msc//1000, bid=bids, ask=asks, last_msc=times_msc,
                            uptick=(changes>0).astype(int), downtick=(changes<0).astype(int)))
    seconds = raw.groupby('second', sort=True).agg(bid=('bid','last'), ask=('ask','last'),
        last_msc=('last_msc','last'), ticks=('bid','size'), up=('uptick','sum'), down=('downtick','sum'))
    seconds = seconds.reindex(np.arange(seconds.index[0], seconds.index[-1]+1))
    seconds[['bid','ask','last_msc']] = seconds[['bid','ask','last_msc']].ffill(limit=8)
    seconds[['ticks','up','down']] = seconds[['ticks','up','down']].fillna(0)
    mid = (seconds.bid+seconds.ask)/2
    spread = seconds.ask-seconds.bid
    scale = spread.rolling(30).median().clip(lower=.01)
    features = pd.DataFrame(dict(feature_epoch=seconds.index+1,
        spread=spread, tick_age=(seconds.index+1)-seconds.last_msc/1000,
        spread_ratio=spread/scale, quote_rate=seconds.ticks.rolling(30).sum()/30,
        uptick_fraction=seconds.up.rolling(30).sum()/
            (seconds.up+seconds.down).rolling(30).sum().replace(0,np.nan),
        realized_30=np.sqrt(mid.diff().pow(2).rolling(30).sum())/scale,
        range_30=(mid.rolling(30).max()-mid.rolling(30).min())/scale))
    features['uptick_fraction'] = features.uptick_fraction.fillna(.5)
    for window in (6,12,30,60):
        bd, ad = seconds.bid.diff(window), seconds.ask.diff(window)
        both = pd.Series(np.where(bd*ad>0, np.sign(bd)*np.minimum(abs(bd),abs(ad)), 0.), index=bd.index)
        both = both.where(bd.notna() & ad.notna())
        path = mid.diff().abs().rolling(window).sum()
        features[f'pressure_{window}'] = both/scale
        features[f'efficiency_{window}'] = (mid.diff(window).abs()/path.replace(0,np.nan)).fillna(0).where(path.notna())
    features['acceleration'] = (mid.diff(6)/6-mid.diff(30)/30)/scale
    # Each feature timestamp is AFTER all ticks in its second. Missing/stale
    # prices cannot become executable examples through forward-filling.
    features = features.replace([np.inf,-np.inf], np.nan).dropna()
    return features[(features.feature_epoch%cadence_seconds==0) &
                    (features.tick_age<=2) & (features.spread<=.50)].reset_index(drop=True)


def tick_path_labels(times_msc, bids, asks, feature_epochs, *, horizon_seconds=180,
                     latency_ms=100, stress=1., stop_usd=5.):
    if min(horizon_seconds, stress, stop_usd)<=0 or latency_ms<0:
        raise ValueError('Invalid simulation parameters')
    count = len(feature_epochs)
    outputs = {name: np.full(count,np.nan) for name in
               ('buy_profit','sell_profit','buy_exit_epoch','sell_exit_epoch','entry_epoch')}
    outputs['valid'] = np.zeros(count,dtype=bool)
    if not len(times_msc):
        return pd.DataFrame(outputs)
    if np.any(np.diff(times_msc)<0):
        raise ValueError('Ticks must be chronological')
    execution = np.asarray(feature_epochs,dtype=np.int64)*1000+latency_ms
    entry_indices = np.searchsorted(times_msc, execution, side='right')-1
    deadlines = execution+int(horizon_seconds*1000)
    exit_indices = np.searchsorted(times_msc, deadlines, side='right')-1
    spreads = asks-bids
    slippage = .05*stress
    for k,(entry_i,exit_i) in enumerate(zip(entry_indices,exit_indices)):
        if (entry_i<0 or exit_i<entry_i or execution[k]-times_msc[entry_i]>2000
                or not 0<=spreads[entry_i]<=.50):
            continue
        exit_time = deadlines[k]
        if deadlines[k]-times_msc[exit_i]>15000:
            exit_i += 1
            if exit_i>=len(times_msc) or times_msc[exit_i]-deadlines[k]>15000:
                continue
            exit_time = times_msc[exit_i]
        if deadlines[k]>times_msc[-1]:
            continue  # Dataset-end marks are not complete outcome labels.
        entry_buy = asks[entry_i]+(stress-1)*spreads[entry_i]+slippage
        entry_sell = bids[entry_i]-slippage
        begin = np.searchsorted(times_msc,execution[k],side='right')
        for side,entry,name in ((1,entry_buy,'buy'),(-1,entry_sell,'sell')):
            stop = entry-side*stop_usd
            path = bids[begin:exit_i+1] if side==1 else asks[begin:exit_i+1]+(stress-1)*spreads[begin:exit_i+1]
            hits = np.flatnonzero(side*(path-stop)<=0)
            actual_exit_i = begin+int(hits[0]) if len(hits) else exit_i
            price = bids[actual_exit_i] if side==1 else asks[actual_exit_i]+(stress-1)*spreads[actual_exit_i]
            outputs[name+'_profit'][k] = side*(price-entry)-slippage
            outputs[name+'_exit_epoch'][k] = (times_msc[actual_exit_i] if len(hits) else exit_time)/1000
        outputs['valid'][k] = True
        outputs['entry_epoch'][k] = execution[k]/1000
    return pd.DataFrame(outputs)
