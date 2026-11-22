"""Completed-candle geometry for offline entry research; no execution authority."""
import numpy as np
import pandas as pd


def candle_structure(frame, *, seconds, broker_offset_seconds, window=20):
    frame=frame.sort_values('time').reset_index(drop=True)
    high,low,close,opened=(pd.to_numeric(frame[name],errors='coerce')
                           for name in ('high','low','close','open'))
    body=close-opened
    span=(high-low).replace(0,np.nan)
    tr=pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False).mean().clip(lower=.01)
    prior_high=high.shift().rolling(window).max()
    prior_low=low.shift().rolling(window).min()
    epoch=frame.time+seconds-broker_offset_seconds
    # Tick volume supports a broker-local intraday average only; this is not
    # centralized exchange volume, aggressor flow or an institutional order map.
    volume=pd.to_numeric(frame.tick_volume,errors='coerce').clip(lower=0)
    day=pd.to_datetime(frame.time-broker_offset_seconds,unit='s',utc=True).dt.floor('D')
    total=volume.groupby(day).cumsum().replace(0,np.nan)
    vwap=(((high+low+close)/3*volume).groupby(day).cumsum()/total)
    return pd.DataFrame(dict(feature_epoch=epoch.astype(np.int64),
        support_distance_atr=(close-prior_low)/atr,
        resistance_distance_atr=(prior_high-close)/atr,
        support_distance_stop_budget=(close-prior_low)/5.,
        resistance_distance_stop_budget=(prior_high-close)/5.,
        upper_wick_fraction=(high-pd.concat([opened,close],axis=1).max(axis=1))/span,
        lower_wick_fraction=(pd.concat([opened,close],axis=1).min(axis=1)-low)/span,
        two_candle_direction=np.sign(body).rolling(2).sum()/2,
        upside_sweep=((high>prior_high)&(close<prior_high)).astype(float),
        downside_sweep=((low<prior_low)&(close>prior_low)).astype(float),
        bullish_three_bar_gap=(low-high.shift(2)).clip(lower=0)/atr,
        bearish_three_bar_gap=(low.shift(2)-high).clip(lower=0)/atr,
        local_vwap_distance_atr=(close-vwap)/atr,
        range_relative_atr=span/atr)).replace([np.inf,-np.inf],np.nan)
