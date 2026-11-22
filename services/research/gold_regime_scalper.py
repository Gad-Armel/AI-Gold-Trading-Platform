"""Causal trend-pullback and breakout-retest candidates; no broker operations."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from services.research.gold_scalp_setups import _bars


@dataclass(frozen=True)
class RegimeConfig:
    period: int = 5
    trend_threshold: float = .15
    maximum_spread: float = .75
    maximum_spread_atr: float = .35
    maximum_risk_price: float = 3.
    minimum_body_fraction: float = .4
    maximum_expansion: float = 2.5


def quote_bars(ticks, period=5):
    if period not in (5, 15, 30):
        raise ValueError('Supported closed-quote periods are 5, 15 and 30 seconds')
    frame = pd.DataFrame(ticks).copy()
    if frame.empty or not {'timestamp', 'bid', 'ask'}.issubset(frame):
        return pd.DataFrame()
    frame = frame[np.isfinite(frame[['timestamp', 'bid', 'ask']]).all(axis=1) &
                  (frame.bid > 0) & (frame.ask >= frame.bid)].sort_values('timestamp', kind='stable')
    frame['bucket'] = (frame.timestamp//period).astype('int64')*period
    frame['mid'] = (frame.bid+frame.ask)/2
    frame['spread'] = frame.ask-frame.bid
    frame['gap'] = frame.groupby('bucket').timestamp.diff()
    bars = frame.groupby('bucket', sort=True).agg(open=('mid', 'first'), high=('mid', 'max'),
        low=('mid', 'min'), close=('mid', 'last'), count=('mid', 'size'),
        first=('timestamp', 'first'), last=('timestamp', 'last'), gap=('gap', 'max'),
        spread=('spread', 'last'), bid=('bid', 'last'), ask=('ask', 'last')).reset_index()
    bars['feature_epoch'] = (bars.bucket+period).astype(float)
    bars['covered'] = ((bars['count'] >= 2) &
        ((bars['first']-bars.bucket) <= min(5., period/3)) &
        ((bars.feature_epoch-bars['last']) <= min(5., period/3)) &
        (bars.gap.fillna(period) <= min(5., period/3)))
    bars['covered'] &= bars.bucket.diff().fillna(period).eq(period)
    bars['tr'] = pd.concat([bars.high-bars.low, (bars.high-bars.close.shift()).abs(),
                           (bars.low-bars.close.shift()).abs()], axis=1).max(axis=1)
    bars['atr5'] = bars.tr.ewm(alpha=1/14, adjust=False).mean()
    bars['ema5'] = bars.close.ewm(span=9, adjust=False).mean()
    return bars


def rate_features(rates, period, offset, prefix):
    frame = pd.DataFrame(rates).copy()
    if len(frame) < 30:
        return pd.DataFrame(columns=['feature_epoch'])
    frame = _bars(frame, period, offset, None)
    frame['feature_epoch'] = frame.available.astype(float)
    ranges = pd.concat([frame.high-frame.low, (frame.high-frame.close.shift()).abs(),
                        (frame.low-frame.close.shift()).abs()], axis=1).max(axis=1)
    atr = ranges.ewm(alpha=1/14, adjust=False).mean()
    fast, slow = frame.close.ewm(span=9, adjust=False).mean(), frame.close.ewm(span=21, adjust=False).mean()
    output = pd.DataFrame(dict(feature_epoch=frame.feature_epoch, **{
        f'{prefix}_atr': atr, f'{prefix}_trend': (fast-slow)/atr,
        f'{prefix}_slope': fast.diff(3)/atr, f'{prefix}_close': frame.close}))
    output.loc[output.index[:29], output.columns != 'feature_epoch'] = np.nan
    continuous = frame.available.diff().eq(period).rolling(20).sum().eq(20)
    output.loc[~continuous, output.columns != 'feature_epoch'] = np.nan
    return output


def feature_table(ticks, m1, m5, *, offset=10800, config=RegimeConfig()):
    bars = quote_bars(ticks, config.period)
    if bars.empty:
        return bars
    for rates, period, prefix in ((m1, 60, 'm1'), (m5, 300, 'm5')):
        slow = rate_features(rates, period, offset, prefix)
        if slow.empty:
            return pd.DataFrame()
        bars = pd.merge_asof(bars, slow.rename(columns={'feature_epoch': f'{prefix}_epoch'}),
            left_on='feature_epoch', right_on=f'{prefix}_epoch', direction='backward')
    trend = np.where((bars.m1_trend >= config.trend_threshold) & (bars.m1_slope > 0) &
                     (bars.m5_trend > -.3), 1,
                     np.where((bars.m1_trend <= -config.trend_threshold) & (bars.m1_slope < 0) &
                              (bars.m5_trend < .3), -1, 0))
    bars['trend_sign'] = trend
    body = bars.close-bars.open
    body_fraction = body.abs()/(bars.high-bars.low).replace(0, np.nan)
    prior_high = bars.high.rolling(12).max().shift(3)
    prior_low = bars.low.rolling(12).min().shift(3)
    atr = bars.atr5.shift()
    pull_buy = ((body.shift() < 0) | (body.shift(2) < 0)) & (bars.low.shift() <= bars.ema5.shift()+.15*atr)
    pull_sell = ((body.shift() > 0) | (body.shift(2) > 0)) & (bars.high.shift() >= bars.ema5.shift()-.15*atr)
    break_buy = (bars.close.shift(2) > prior_high) & (bars.low.shift() <= prior_high+.15*atr) & (bars.close.shift() >= prior_high-.15*atr)
    break_sell = (bars.close.shift(2) < prior_low) & (bars.high.shift() >= prior_low-.15*atr) & (bars.close.shift() <= prior_low+.15*atr)
    confirmation_buy = (body > 0) & (bars.close > bars.high.shift()+.02*atr)
    confirmation_sell = (body < 0) & (bars.close < bars.low.shift()-.02*atr)
    common = (bars.covered.rolling(16).sum().eq(16) & (body_fraction >= config.minimum_body_fraction) &
              (bars.tr <= config.maximum_expansion*atr) & (bars.spread <= config.maximum_spread) &
              (bars.spread <= config.maximum_spread_atr*bars.m1_atr) &
              ((bars.feature_epoch-bars.m1_epoch) < 180) & ((bars.feature_epoch-bars.m5_epoch) < 900))
    bars['coverage_ok'] = bars.covered.rolling(16).sum().eq(16)
    bars['confirmation_ok'] = np.where(trend == 1, confirmation_buy, np.where(trend == -1, confirmation_sell, False))
    bars['structure_ok'] = np.where(trend == 1, pull_buy | break_buy, np.where(trend == -1, pull_sell | break_sell, False))
    bars['body_ok'] = body_fraction >= config.minimum_body_fraction
    bars['spread_ok'] = (bars.spread <= config.maximum_spread) & (bars.spread <= config.maximum_spread_atr*bars.m1_atr)
    bars['expansion_ok'] = bars.tr <= config.maximum_expansion*atr
    buy = common & (trend == 1) & confirmation_buy & (pull_buy | break_buy)
    sell = common & (trend == -1) & confirmation_sell & (pull_sell | break_sell)
    bars['direction'] = np.where(buy, 'BUY', np.where(sell, 'SELL', 'WAIT'))
    bars['setup'] = np.where((buy & break_buy) | (sell & break_sell), 'BREAKOUT_RETEST', 'TREND_PULLBACK')
    buffer = np.maximum(bars.spread, .1*bars.m1_atr)
    buy_stop = np.minimum(bars.low.rolling(4).min()-buffer, bars.bid-np.maximum(2*bars.spread, .25*bars.m1_atr))
    sell_stop = np.maximum(bars.high.rolling(4).max()+buffer, bars.ask+np.maximum(2*bars.spread, .25*bars.m1_atr))
    bars['stop'] = np.where(buy, buy_stop, sell_stop)
    bars['reference'] = np.where(buy, bars.ask, bars.bid)
    bars['risk'] = (bars.reference-bars.stop).abs()
    bars.loc[(bars.risk > config.maximum_risk_price) | (bars.risk <= 0), 'direction'] = 'WAIT'
    bars['evidence'] = (body_fraction*100).clip(0, 100)
    return bars


def candidate_from_row(row, *, now, bid, ask, config=RegimeConfig()):
    output = dict(bias='WAIT', evidence=0., source_usable=False, levels={}, timeframe='S5',
                  strategy='REGIME_PULLBACK_V1', blocks=[])
    if not np.isfinite([now, bid, ask]).all() or bid <= 0 or ask < bid:
        return dict(output, blocks=['Invalid executable quote or observation clock'])
    if row is None:
        return dict(output, blocks=['Insufficient completed S5/M1/M5 history'])
    if not 0 <= now-float(row['feature_epoch']) < config.period:
        return dict(output, blocks=['Setup has expired; waiting for a fresh S5 close'])
    output.update(source_usable=True, evidence=float(row['evidence']) if pd.notna(row['evidence']) else 0.,
                  thesis_bias='BUY' if row['trend_sign'] == 1 else 'SELL' if row['trend_sign'] == -1 else 'WAIT',
                  setup_id=f"{row['setup']}:{int(row['feature_epoch'])}:{row['direction']}")
    output['checks'] = {name: bool(row.get(name, False)) for name in (
        'coverage_ok', 'confirmation_ok', 'structure_ok', 'body_ok', 'spread_ok', 'expansion_ok')}
    output['next_evaluation_epoch'] = float(row['feature_epoch'])+config.period
    if row['direction'] not in ('BUY', 'SELL'):
        failed = [name for name, passed in output['checks'].items() if not passed]
        if not row['trend_sign']:
            failed.append('M1/M5 trend alignment')
        return dict(output, blocks=['Waiting for '+', '.join(failed)] if failed else
                    ['Structural stop outside strategy limits or completed context unavailable'])
    reference = ask if row['direction'] == 'BUY' else bid
    stop, sign = float(row['stop']), 1 if row['direction'] == 'BUY' else -1
    risk = sign*(reference-stop)
    if not np.isfinite([reference, stop, risk]).all():
        return dict(output, source_usable=False, blocks=['Invalid executable quote or structural stop'])
    if ask-bid > config.maximum_spread or risk <= 0 or risk > config.maximum_risk_price:
        return dict(output, blocks=['Live spread or structural stop risk outside strategy limits'])
    if abs(reference-float(row['reference'])) > max(ask-bid, .25*float(row['m1_atr'])):
        return dict(output, blocks=['Price moved too far from the confirmed setup'])
    levels = dict(sl=stop, entry_reference=reference, entry_zone=[bid, ask], source='REGIME_STRUCTURE',
                  tp1=reference+sign*1.8*risk, tp2=reference+sign*2.5*risk, tp3=reference+sign*3*risk)
    return dict(output, bias=row['direction'], levels=levels, setup=row['setup'], blocks=[],
                valid_until=pd.Timestamp((float(row['feature_epoch'])+config.period), unit='s', tz='UTC').isoformat())


class RegimeScalper:
    def __init__(self):
        self.key = None
        self.row = None

    def assess(self, ticks, candles, *, now, bid, ask, offset=10800):
        frame = pd.DataFrame(ticks)
        if frame.empty:
            return candidate_from_row(None, now=now, bid=bid, ask=ask)
        closed_end = int(now//5)*5
        key = closed_end
        if key != self.key:
            frame = frame[(frame.timestamp < closed_end) & (frame.timestamp >= closed_end-920)]
            features = feature_table(frame, candles.get('M1', []), candles.get('M5', []), offset=offset)
            self.row = features.iloc[-1].to_dict() if not features.empty else None
            self.key = key
        return candidate_from_row(self.row, now=now, bid=bid, ask=ask)
