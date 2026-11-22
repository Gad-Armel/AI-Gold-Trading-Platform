"""Adapted ORBIT hypotheses on closed M1/M15 bars, without order authority."""
import numpy as np
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
from services.research.gold_scalp_setups import _bars


def orbit_features(m1, m15, *, offset):
    if pd.DataFrame(m1).empty or pd.DataFrame(m15).empty:
        return pd.DataFrame()
    one, slow = _bars(m1, 60, offset, None), _bars(m15, 900, offset, None)
    if len(one) < 30 or len(slow) < 200:
        return pd.DataFrame()
    previous = slow.close.shift()
    ranges = pd.concat([slow.high-slow.low, (slow.high-previous).abs(),
                        (slow.low-previous).abs()], axis=1).max(axis=1)
    atr15 = ranges.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    up, down = slow.high.diff(), -slow.low.diff()
    positive = up.where((up > down) & (up > 0), 0.).ewm(alpha=1/14, adjust=False).mean()/atr15
    negative = down.where((down > up) & (down > 0), 0.).ewm(alpha=1/14, adjust=False).mean()/atr15
    dx = (positive-negative).abs()/(positive+negative).replace(0, np.nan)*100
    adx = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    ema50 = slow.close.ewm(span=50, adjust=False, min_periods=50).mean()
    ema200 = slow.close.ewm(span=200, adjust=False, min_periods=200).mean()
    slope = ema50.diff(3)/atr15
    trend = np.where((ema50 > ema200) & (slope > .05) & (adx >= 22), 1,
                     np.where((ema50 < ema200) & (slope < -.05) & (adx >= 22), -1, 0))
    ranging = (adx < 18) & (slope.abs() <= .05) & ema200.notna()
    context = pd.DataFrame(dict(available=slow.available.astype(float), trend_sign=trend,
        ranging=ranging, adx=adx, ema200=ema200, ema50=ema50, context_close=slow.close))
    one['available'] = one.available.astype(float)
    output = pd.merge_asof(one, context, on='available', direction='backward', tolerance=900)
    ranges = pd.concat([output.high-output.low, (output.high-output.close.shift()).abs(),
                        (output.low-output.close.shift()).abs()], axis=1).max(axis=1)
    atr = ranges.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    ema20 = output.close.ewm(span=20, adjust=False, min_periods=20).mean()
    if 'tick_volume' not in output:
        raise ValueError('Observed broker tick activity is required, not synthetic volume')
    activity = pd.to_numeric(output.tick_volume, errors='coerce')
    relative = activity/activity.shift().rolling(20).mean().replace(0, np.nan)
    body = output.close-output.open
    lower = output[['close', 'open']].min(axis=1)-output.low
    upper = output.high-output[['close', 'open']].max(axis=1)
    rejection_buy = (body > 0) & (lower >= .5*body.abs())
    rejection_sell = (body < 0) & (upper >= .5*body.abs())
    pull_buy = (output.trend_sign == 1) & (output.low.shift() <= ema20.shift()) & (output.close > ema20) & rejection_buy
    pull_sell = (output.trend_sign == -1) & (output.high.shift() >= ema20.shift()) & (output.close < ema20) & rejection_sell
    level_high = output.high.rolling(10).max().shift(3)
    level_low = output.low.rolling(10).min().shift(3)
    break_buy = ((output.trend_sign == 1) & (output.close.shift(2) > level_high) &
                 (output.low.shift() <= level_high+.1*atr.shift()) &
                 (output.close.shift() >= level_high-.1*atr.shift()) &
                 (output.close > output.high.shift()) & (body > 0))
    break_sell = ((output.trend_sign == -1) & (output.close.shift(2) < level_low) &
                  (output.high.shift() >= level_low-.1*atr.shift()) &
                  (output.close.shift() <= level_low+.1*atr.shift()) &
                  (output.close < output.low.shift()) & (body < 0))
    prior_high = output.high.shift().rolling(20).max()
    prior_low = output.low.shift().rolling(20).min()
    fade_buy = output.ranging.fillna(False) & (output.low < prior_low) & (output.close > prior_low) & rejection_buy & (ema20-output.low >= 1.5*atr)
    fade_sell = output.ranging.fillna(False) & (output.high > prior_high) & (output.close < prior_high) & rejection_sell & (output.high-ema20 >= 1.5*atr)
    ready = output.available.diff().eq(60).rolling(21).sum().eq(21)
    common = ready & (relative >= 1.) & (ranges <= 1.5*atr.shift()) & output.ema200.notna()
    buy = common & (pull_buy | break_buy | fade_buy)
    sell = common & (pull_sell | break_sell | fade_sell)
    output['direction'] = np.where(buy & ~sell, 'BUY', np.where(sell & ~buy, 'SELL', 'WAIT'))
    output['setup'] = np.where(fade_buy | fade_sell, 'RANGE_SWEEP_RECLAIM',
                     np.where(break_buy | break_sell, 'BREAKOUT_RETEST', 'TREND_PULLBACK'))
    output['atr'] = atr
    output['relative_tick_activity'] = relative
    output['stop_buy'] = np.minimum(output.low.rolling(3).min()-.2*atr, output.close-atr)
    output['stop_sell'] = np.maximum(output.high.rolling(3).max()+.2*atr, output.close+atr)
    output['feature_epoch'] = output.available
    output['evidence'] = np.where(output.direction != 'WAIT', 70., 0.)
    return output


def orbit_candidate(row, *, now, bid, ask):
    base = dict(strategy='ORBIT_M1_M15_RESEARCH_V1', timeframe='M1', bias='WAIT',
        source_usable=False, evidence=0., calibrated_probability=None, levels={}, blocks=[])
    if row is None:
        return dict(base, blocks=['Requires at least 200 completed M15 bars and 30 M1 bars'])
    if not np.isfinite([now, bid, ask]).all() or bid <= 0 or ask < bid:
        return dict(base, blocks=['Invalid executable quote or clock'])
    if not 0 <= now-row['feature_epoch'] < 60:
        return dict(base, blocks=['Waiting for a fresh completed M1 setup'])
    side = row['direction']
    base.update(source_usable=True, thesis_bias='BUY' if row['trend_sign'] == 1 else
        'SELL' if row['trend_sign'] == -1 else 'WAIT', setup=row['setup'],
        setup_id=f"ORBIT:{int(row['feature_epoch'])}:{side}")
    if side not in ('BUY', 'SELL'):
        return dict(base, blocks=['No completed trend pullback, breakout retest or range sweep with activity confirmation'])
    sign = 1 if side == 'BUY' else -1
    reference = ask if sign == 1 else bid
    stop = float(row['stop_buy'] if sign == 1 else row['stop_sell'])
    risk = sign*(reference-stop)
    if not np.isfinite([stop, risk, row['atr']]).all() or not 0 < risk <= 10:
        return dict(base, blocks=['Structural stop outside the declared paper risk limit'])
    if ask-bid > .75 or ask-bid > .15*risk:
        return dict(base, blocks=['Spread exceeds 15% of structural risk or 0.75 price units'])
    if abs(reference-row['close']) > max(ask-bid, .25*row['atr']):
        return dict(base, blocks=['Setup price has moved too far; do not chase'])
    return dict(base, bias=side, evidence=70., blocks=[], levels=dict(sl=stop,
        entry_reference=reference, tp1=reference+sign*1.2*risk,
        tp2=reference+sign*2*risk, tp3=reference+sign*3*risk),
        valid_until=pd.Timestamp(row['feature_epoch']+60, unit='s', tz='UTC').isoformat())


class OrbitScalper:
    def __init__(self):
        self.key = None
        self.row = None

    def assess(self, ticks, candles, *, now, bid, ask, offset=10800):
        key = int(now//60)
        if key != self.key:
            features = orbit_features(candles.get('M1'), candles.get('M15'), offset=offset)
            features = features[features.feature_epoch <= now] if not features.empty else features
            self.row = features.iloc[-1].to_dict() if not features.empty else None
            self.key = key
        return orbit_candidate(self.row, now=now, bid=bid, ask=ask)


def read_orbit_forward(*, now, path='data/research/strategy_20261021/orbit_forward/latest.json'):
    base = dict(available=False, execution_enabled=False, role='FORWARD_RESEARCH_ONLY',
                strategy='ORBIT_M1_M15_RESEARCH_V1')
    try:
        report = json.loads(Path(path).read_text(encoding='utf-8'))
        stamp = datetime.fromisoformat(report['observed_at'])
        age = now-stamp.timestamp()
        if (stamp.tzinfo is None or not np.isfinite(age) or age < 0 or
                report.get('read_only') is not True or report.get('execution_enabled') is not False or
                report.get('strategy') != base['strategy']):
            raise ValueError('Invalid prospective observation metadata')
        running = age <= 90 and not report.get('completed_at')
        return dict(base, available=True, observer_state='RUNNING' if running else 'FINISHED_OR_STALE',
            observed_at=report['observed_at'], age_seconds=age,
            last_signal=report.get('last_signal', {}), paper_summary=report.get('paper_result', {}).get('summary', {}),
            errors=report.get('errors', []), limitations=report.get('limitations', []))
    except (OSError, ValueError, TypeError, KeyError):
        return dict(base, observer_state='NOT_AVAILABLE')
