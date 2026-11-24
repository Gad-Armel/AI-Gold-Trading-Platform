"""Causal setup observations shared by live diagnostics and offline research.

These patterns describe broker candles, not calibrated probabilities or orders.
No detector has execution authority until separate prospective validation.
"""
import numpy as np
import pandas as pd

VERSION = 1


def _bars(raw, seconds, offset, now):
    frame = pd.DataFrame(raw).copy()
    required = ['time', 'open', 'high', 'low', 'close']
    if not set(required).issubset(frame):
        raise ValueError('Missing candle fields')
    if not pd.api.types.is_numeric_dtype(frame.time):
        # Pandas may preserve seconds/us rather than ns: integer casts alone
        # would silently scale timestamps by 1e9 and break live/offline parity.
        frame['time'] = (pd.to_datetime(frame.time, utc=True)-pd.Timestamp('1970-01-01',tz='UTC')).dt.total_seconds()
    frame['available'] = pd.to_numeric(frame.time) + seconds - offset
    if now is not None:
        frame = frame[frame.available <= now]
    frame = frame.sort_values('available')
    if frame.available.duplicated().any():
        raise ValueError('Duplicate candle timestamps')
    prices = frame[['open', 'high', 'low', 'close']].apply(pd.to_numeric, errors='coerce')
    if (not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()
            or (prices.high < prices.max(axis=1)).any()
            or (prices.low > prices.min(axis=1)).any()):
        raise ValueError('Invalid candle prices or ranges')
    frame[prices.columns] = prices
    return frame.reset_index(drop=True)


def setup_features(m1, m5, *, broker_offset_seconds, now=None):
    one = _bars(m1, 60, broker_offset_seconds, now)
    five = _bars(m5, 300, broker_offset_seconds, now)
    c = five.close
    tr = pd.concat([five.high-five.low, (five.high-c.shift()).abs(),
                    (five.low-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean().replace(0, np.nan)
    fast = c.ewm(span=21, adjust=False, min_periods=21).mean()
    slow = c.ewm(span=50, adjust=False, min_periods=50).mean()
    separation = (fast-slow)/atr
    efficiency = c.diff(20).abs()/c.diff().abs().rolling(20).sum().replace(0, np.nan)
    trend = np.where((separation > .10) & (efficiency >= .25), 1,
                     np.where((separation < -.10) & (efficiency >= .25), -1, 0))
    context = pd.DataFrame(dict(available=five.available, m5_separation_atr=separation,
                                m5_efficiency=efficiency, m5_direction=trend))
    result = pd.merge_asof(one, context, on='available', direction='backward', tolerance=300)
    close, opened = result.close, result.open
    ema = close.ewm(span=21, adjust=False, min_periods=21).mean()
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1/7, adjust=False, min_periods=7).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1/7, adjust=False, min_periods=7).mean()
    rsi = 100*gain/(gain+loss).replace(0, np.nan)
    hi = result.high.shift().rolling(20).max()
    lo = result.low.shift().rolling(20).min()
    range_mode = (result.m5_efficiency < .25) & (result.m5_separation_atr.abs() <= .10)
    continuous = result.available.diff().eq(60).rolling(21).sum().eq(21)
    ready = result.m5_separation_atr.notna() & rsi.notna() & continuous
    buy_pullback = ((result.m5_direction == 1) & (result.low.shift() <= ema.shift())
                    & (close > ema) & (close > opened) & (rsi.shift() <= 50) & (rsi > 50))
    sell_pullback = ((result.m5_direction == -1) & (result.high.shift() >= ema.shift())
                     & (close < ema) & (close < opened) & (rsi.shift() >= 50) & (rsi < 50))
    buy_sweep = range_mode & (result.low < lo) & (close > lo) & (close > opened)
    sell_sweep = range_mode & (result.high > hi) & (close < hi) & (close < opened)
    buy_break = (result.m5_direction == 1) & (close > hi) & (close > opened)
    sell_break = (result.m5_direction == -1) & (close < lo) & (close < opened)
    for name, buy, sell in [('pullback', buy_pullback, sell_pullback),
                            ('sweep', buy_sweep, sell_sweep), ('breakout', buy_break, sell_break)]:
        result[name+'_side'] = np.where(ready & buy, 1, np.where(ready & sell, -1, 0))
    result['rsi7'] = rsi
    result['ready'] = ready
    return result


def latest_observation(m1, m5, *, broker_offset_seconds, now):
    try:
        rows = setup_features(m1, m5, broker_offset_seconds=broker_offset_seconds, now=now)
        if rows.empty or now-rows.available.iloc[-1] >= 120 or not rows.ready.iloc[-1]:
            raise ValueError('Insufficient, stale or discontinuous completed candles')
        row = rows.iloc[-1]
        return dict(available=True, role='RESEARCH_ONLY', version=VERSION,
                    feature_epoch=float(row.available),
                    regime='TREND_UP' if row.m5_direction == 1 else
                           'TREND_DOWN' if row.m5_direction == -1 else 'RANGE_OR_TRANSITION',
                    rsi7=float(row.rsi7), m5_efficiency=float(row.m5_efficiency),
                    candidates={name: 'BUY' if row[name+'_side'] == 1 else
                                      'SELL' if row[name+'_side'] == -1 else 'WAIT'
                                for name in ('pullback', 'sweep', 'breakout')},
                    calibrated_probability=None, execution_enabled=False)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return dict(available=False, role='RESEARCH_ONLY', version=VERSION,
                    reason=str(error), execution_enabled=False)
