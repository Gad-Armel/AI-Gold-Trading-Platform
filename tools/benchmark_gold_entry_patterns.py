"""Frozen candle challengers with chronological splits and executable cost stress.

Not a production replay: full-history EMAs approximate windowed Advisor 1 views;
fixed time exits isolate entry quality, omitting live adaptive/news protections.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]/'data/research/entry_efficiency'


def view(frame, seconds):
    c = frame.close
    tr = pd.concat([frame.high-frame.low, (frame.high-c.shift()).abs(),
                    (frame.low-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean().clip(lower=.01)
    fast = c.ewm(span=12, adjust=False).mean()
    separation = (fast-c.ewm(span=26, adjust=False).mean())/atr
    slope = (fast-fast.shift(3))/atr
    side = (c-c.ewm(span=50, adjust=False).mean())/atr
    direction = np.where((separation>.05)&(slope>0)&(side>0), 1,
                         np.where((separation<-.05)&(slope<0)&(side<0), -1, 0))
    return pd.DataFrame(dict(available=frame.time+seconds, direction=direction,
        atr=atr, extension=(c-fast)/atr)).iloc[55:]


def dataset(frames=None, *, include_latest=False):
    if frames is None:
        frames = {name: pd.read_csv(ROOT/'broker_bars'/(name+'.csv')).sort_values('time').reset_index(drop=True)
                  for name in ('M1', 'M5', 'M15')}
    m1 = frames['M1']
    result = m1.assign(available=m1.time+60)
    for name, seconds in [('M1', 60), ('M5', 300), ('M15', 900)]:
        v = view(frames[name], seconds).rename(columns={k: name+'_'+k for k in ('direction', 'atr', 'extension')})
        result = pd.merge_asof(result, v, on='available', direction='backward', tolerance=seconds*3)
    # Only bars actually closed at the signal instant enter these comparisons.
    buys = sum((result[name+'_direction'] == 1).astype(int) for name in frames)
    sells = sum((result[name+'_direction'] == -1).astype(int) for name in frames)
    result['direction'] = np.where(buys>=2, 1, np.where(sells>=2, -1, 0))
    result['body'] = result.close-result.open
    result['prior_body'] = result.body.shift()
    result['prior_high'] = result.high.shift().rolling(3).max()
    result['prior_low'] = result.low.shift().rolling(3).min()
    result['gap_next'] = result.time.shift(-1)-result.time
    subset = [column for column in result.columns if column != 'gap_next'] if include_latest else None
    return result.dropna(subset=subset).reset_index(drop=True)


def evaluate(frame, start, end, policy, minutes, stress, *, predictions=None, threshold=0, collect=False, return_trades=False):
    if collect and return_trades:
        raise ValueError('Overlapping training labels cannot be requested as non-overlapping trade events.')
    arrays = {key: frame[key].to_numpy() for key in frame.columns}
    trades = []
    i = start
    while i < end-minutes-2:
        d = arrays['direction'][i]
        setup = (d != 0 and d*arrays['body'][i]>0 and arrays['gap_next'][i] == 60)
        if policy == 'ANY_DIRECTION':
            setup = d != 0 and arrays['gap_next'][i] == 60
        if predictions is not None:
            setup &= predictions[i] >= threshold
        if policy == 'M1_M5_ALIGN':
            setup &= d == arrays['M1_direction'][i] == arrays['M5_direction'][i]
        elif policy == 'PULLBACK_RESUME':
            setup &= d*arrays['prior_body'][i]<0 and abs(arrays['M1_extension'][i])<=1
        elif policy == 'CLOSE_BREAKOUT':
            setup &= (arrays['close'][i]>arrays['prior_high'][i] if d==1 else arrays['close'][i]<arrays['prior_low'][i])
        if not setup:
            i += 1
            continue
        k = i+1
        if arrays['time'][k+minutes]-arrays['time'][k] != minutes*60:
            i += 1
            continue
        spread = max(.28, float(arrays['spread'][k])*.01)*stress
        if spread > .50*stress:
            i += 1
            continue
        entry = float(arrays['open'][k])+(spread if d==1 else 0)+d*.05*stress
        stop = entry-d*5
        profit = None
        for j in range(k, min(k+minutes, end-1)):
            ask_spread = max(.28, float(arrays['spread'][j])*.01)*stress
            adverse = float(arrays['low'][j]) if d==1 else float(arrays['high'][j])+ask_spread
            if d*(adverse-stop)<=0:
                opened_exit = float(arrays['open'][j])+(ask_spread if d==-1 else 0)
                fill = min(stop, opened_exit) if d==1 else max(stop, opened_exit)
                profit = d*(fill-entry)-.05*stress
                break
            if j==k+minutes-1:
                spread_exit = max(.28, float(arrays['spread'][j+1])*.01)*stress
                fill = float(arrays['open'][j+1])+(spread_exit if d==-1 else 0)
                profit = d*(fill-entry)-.05*stress
                j += 1
                break
        if profit is not None:
            if return_trades:
                trades.append(dict(signal_epoch=int(arrays['time'][i]+60), entry_epoch=int(arrays['time'][k]),
                                   exit_epoch=int(arrays['time'][j]), direction=int(d), profit=float(profit)))
            else:
                trades.append((i, float(profit)) if collect else float(profit))
        i = i+1 if collect else j+2  # Labels may overlap; evaluated positions never do.
    if collect or return_trades:
        return trades
    pnl = np.array(trades)
    gains = pnl[pnl>0].sum()
    losses = -pnl[pnl<0].sum()
    equity = np.r_[0, pnl.cumsum()]
    return dict(trades=len(trades), net=round(float(pnl.sum()),2),
                mean=round(float(pnl.mean()),4) if len(pnl) else None,
                profit_factor=round(float(gains/losses),4) if losses else None,
                drawdown=round(float((np.maximum.accumulate(equity)-equity).max()),2))


def main():
    frame = dataset()
    n = len(frame)
    periods = [('EARLY_60', 100, int(n*.6)), ('MIDDLE_20', int(n*.6), int(n*.8)),
               ('LATEST_20', int(n*.8), n)]
    results = []
    for label, start, end in periods:
        for policy in ('DIRECTIONAL_BODY', 'M1_M5_ALIGN', 'PULLBACK_RESUME', 'CLOSE_BREAKOUT'):
            for minutes in (5, 15):
                for stress in (1., 1.5):
                    results.append(dict(period=label, policy=policy, minutes=minutes, cost_stress=stress,
                        **evaluate(frame, start, end, policy, minutes, stress)))
    report = dict(bars=n, first_broker_epoch=int(frame.time.iloc[0]), last_broker_epoch=int(frame.time.iloc[-1]),
                  results=results, live_approved=False, limitations=[
        'Predetermined entry patterns; no model fitting or parameter selection on latest period.',
        'Approximate candle challenger, not exact Advisor 1 or main-bot replay.',
        'Bid OHLC and per-bar spread approximate asks; sampled extrema cannot model spread paths.',
        '$5 per-position stop, .01 lot = one ounce assumption; no account margin constraints.',
        'Fixed 5/15 minute exits omit production adaptive, flow, news and candle-wait controls.',
        'No commission or financing; costs stressed separately. Same split compared across multiple patterns.',
        'Entry/exit paths crossing missing M1 bars are excluded.',
        'Historical EMA input uses only completed bars; next-open entries prevent same-close fills.'])
    (ROOT/'historical_entry_benchmark.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(bars=n, latest=[r for r in results if r['period']=='LATEST_20']), indent=2))


if __name__ == '__main__':
    main()
