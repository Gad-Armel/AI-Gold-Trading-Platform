"""Closed-bar A/B/C hypotheses adapted from the supplied regime EA, paper only."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import numpy as np
import pandas as pd
from services.research.gold_scalp_setups import _bars


def opening_range(raw_m1, *, now, zone, hour, minute=0, duration=30, offset=0):
    local = datetime.fromtimestamp(now, timezone.utc).astimezone(ZoneInfo(zone))
    lower = datetime.combine(local.date(), time(hour, minute), tzinfo=ZoneInfo(zone)).timestamp()
    upper = lower+duration*60
    if now < upper:
        return dict(available=False, reason='Opening range is not completed')
    frame = _bars(raw_m1, 60, offset, now)
    sample = frame[(frame.available > lower) & (frame.available <= upper)]
    expected = np.arange(lower+60, upper+1, 60)
    if len(sample) != len(expected) or not np.array_equal(sample.available.to_numpy(), expected):
        return dict(available=False, reason='Opening range requires every completed M1; retry after data refresh')
    return dict(available=True, high=float(sample.high.max()), low=float(sample.low.min()),
                start_epoch=lower, end_epoch=upper, range_id=f'{zone}:{int(lower)}')


def multi_features(m5, m15, *, offset):
    if pd.DataFrame(m5).empty or pd.DataFrame(m15).empty:
        return pd.DataFrame()
    five, slow = _bars(m5, 300, offset, None), _bars(m15, 900, offset, None)
    if len(five) < 300 or len(slow) < 60:
        return pd.DataFrame()
    close = five.close
    ranges = pd.concat([five.high-five.low, (five.high-close.shift()).abs(),
                        (five.low-close.shift()).abs()], axis=1).max(axis=1)
    atr = ranges.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    up, down = five.high.diff(), -five.low.diff()
    positive = up.where((up > down) & (up > 0), 0.).ewm(alpha=1/14, adjust=False).mean()/atr
    negative = down.where((down > up) & (down > 0), 0.).ewm(alpha=1/14, adjust=False).mean()/atr
    dx = (positive-negative).abs()/(positive+negative).replace(0, np.nan)*100
    adx = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    efficiency = close.diff(20).abs()/close.diff().abs().rolling(20).sum().replace(0, np.nan)
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = 100*gain/(gain+loss).replace(0, np.nan)
    fast, middle = close.ewm(span=9, adjust=False).mean(), close.ewm(span=21, adjust=False).mean()
    center = close.rolling(20).mean()
    deviation = close.rolling(20).std(ddof=0)
    lower, upper = center-2.2*deviation, center+2.2*deviation
    htf_fast = slow.close.ewm(span=21, adjust=False, min_periods=55).mean()
    htf_slow = slow.close.ewm(span=55, adjust=False, min_periods=55).mean()
    bias = np.where((htf_fast > htf_slow) & (htf_fast > htf_fast.shift(3)), 1,
                    np.where((htf_fast < htf_slow) & (htf_fast < htf_fast.shift(3)), -1, 0))
    context = pd.DataFrame(dict(available=slow.available.astype(float), htf_bias=bias))
    five['available'] = five.available.astype(float)
    output = pd.merge_asof(five, context, on='available', direction='backward', tolerance=900)
    output['trend_sign'] = output.htf_bias.fillna(0).astype(int)
    trending = (adx >= 20) | (efficiency >= .3)
    ranging = (adx < 18) & (efficiency < .22)
    ready = five.available.diff().eq(300).rolling(21).sum().eq(21)
    percentile = atr.rolling(288).rank(pct=True)*100
    quality = ready & percentile.between(15, 95) & output.htf_bias.notna()
    lows, highs = five.low.rolling(3).min(), five.high.rolling(3).max()
    buy = (quality & trending & (output.htf_bias == 1) & (lows <= middle+.25*atr) &
           (close > middle) & (close > fast) & (close > five.open) & (rsi > 50) &
           (rsi > rsi.shift()) & (close > close.shift()))
    sell = (quality & trending & (output.htf_bias == -1) & (highs >= middle-.25*atr) &
            (close < middle) & (close < fast) & (close < five.open) & (rsi < 50) &
            (rsi < rsi.shift()) & (close < close.shift()))
    fade_buy = quality & ranging & (close.shift() < lower.shift()) & (close > lower) & (rsi.shift() < 35)
    fade_sell = quality & ranging & (close.shift() > upper.shift()) & (close < upper) & (rsi.shift() > 65)
    output['engine_a'] = np.where(buy, 1, np.where(sell, -1, 0))
    output['engine_c'] = np.where(fade_buy, 1, np.where(fade_sell, -1, 0))
    output['atr'] = atr
    output['adx'] = adx
    output['efficiency'] = efficiency
    output['atr_percentile'] = percentile
    output['quality_ok'] = quality
    output['low3'], output['high3'], output['center'] = lows, highs, center
    output['feature_epoch'] = output.available
    return output


def multi_candidates(row, m1, *, now, bid, ask, offset=0, commission=.1, slippage=.2):
    base = dict(available=False, execution_enabled=False, strategy='ABC_REGIME_RESEARCH_V1',
                calibrated_probability=None, candidates=[], blocks=[])
    if row is None:
        return dict(base, blocks=['Requires 300 M5 bars and 60 M15 bars for causal warm-up'])
    if (not np.isfinite([now, bid, ask, commission, slippage]).all() or bid <= 0 or ask < bid
            or min(commission, slippage) < 0 or not 0 <= now-row['feature_epoch'] < 30):
        return dict(base, blocks=['Invalid/stale setup, quote or explicit cost inputs'])
    raw = []
    for engine, sign in (('A', int(row['engine_a'])), ('C', int(row['engine_c']))):
        if sign:
            raw.append(dict(engine=engine, sign=sign, range_id=None))
    ranges = []
    if row['quality_ok']:
        for zone, hour, minute in (('Europe/London', 8, 0), ('America/New_York', 9, 30)):
            level = opening_range(m1, now=now, zone=zone, hour=hour, minute=minute, offset=offset)
            ranges.append(level)
            if not level['available'] or now-level['end_epoch'] > 7200:
                continue
            width = level['high']-level['low']
            if not .8*row['atr'] <= width <= 4*row['atr']:
                continue
            sign = (1 if row['close'] > level['high']+.1*row['atr'] and row['trend_sign'] >= 0 else
                    -1 if row['close'] < level['low']-.1*row['atr'] and row['trend_sign'] <= 0 else 0)
            if sign:
                raw.append(dict(engine='B', sign=sign, range_id=level['range_id'], width=width))
    candidates, rejected = [], []
    cost = ask-bid+commission+slippage
    for item in raw:
        sign, engine = item['sign'], item['engine']
        reference = ask if sign == 1 else bid
        if abs(reference-row['close']) > max(ask-bid, .25*row['atr']):
            rejected.append(f'{engine}: price moved too far from completed setup')
            continue
        buffer = (.3 if engine == 'C' else .2)*row['atr']
        stop = row['low3']-buffer if sign == 1 else row['high3']+buffer
        if engine == 'B':
            distance = max(.8*row['atr'], .5*item['width'])
            stop = reference-sign*distance
        distance = sign*(reference-stop)
        ceiling = (2.5 if engine == 'B' else 2.)*row['atr']
        if not .8*row['atr'] <= distance <= min(ceiling, 10.) or ask-bid > .75:
            rejected.append(f'{engine}: structural stop/spread outside declared limits; stop not clipped inside structure')
            continue
        room = sign*(row['center']-reference) if engine == 'C' else distance*(3. if engine == 'A' else 1.8)
        if engine == 'C' and room < .8*distance:
            continue
        candidates.append(dict(engine=engine, direction='BUY' if sign == 1 else 'SELL',
            feature_epoch=float(row['feature_epoch']), valid_until_epoch=float(row['feature_epoch'])+30,
            stop=float(stop), atr=float(row['atr']), setup=f'ABC_{engine}',
            setup_id=f"ABC:{engine}:{int(row['feature_epoch'])}:{sign}", range_id=item['range_id'],
            initial_risk_price=float(distance), analytical_room_price=float(room),
            round_trip_cost_price=float(cost), room_cost_diagnostic_passed=bool(room >= 4*cost),
            room_cost_veto_enforced=False, broker_tp=0., lot=.01, execution_enabled=False))
    return dict(base, available=True, candidates=candidates, opening_ranges=ranges,
        feature_epoch=float(row['feature_epoch']), regime='TREND' if row['adx'] >= 20 or row['efficiency'] >= .3
        else 'RANGE' if row['adx'] < 18 and row['efficiency'] < .22 else 'TRANSITION',
        blocks=rejected if rejected else [] if candidates else ['No A/B/C setup on this completed M5'])


class MultiEngineResearch:
    def __init__(self):
        self.key, self.row = None, None

    def assess(self, ticks, candles, *, now, bid, ask, offset=10800):
        key = int(now//300)
        if key != self.key:
            features = multi_features(candles.get('M5'), candles.get('M15'), offset=offset)
            features = features[features.feature_epoch <= now] if not features.empty else features
            self.row = features.iloc[-1].to_dict() if not features.empty else None
            self.key = key if self.row is not None and self.row['feature_epoch'] == key*300 else None
        return multi_candidates(self.row, candles.get('M1'), now=now, bid=bid, ask=ask, offset=offset)


def read_multi_research(*, now, folder='data/research/external_regime_20261021'):
    base = dict(available=False, execution_enabled=False, strategy='ABC_REGIME_RESEARCH_V1')
    forward = Path(folder)/'forward/latest.json'
    path = forward if forward.exists() else Path(folder)/'abc_replay.json'
    try:
        report = json.loads(path.read_text(encoding='utf-8'))
        stamp = datetime.fromisoformat(report.get('observed_at', report.get('as_of', '')))
        if (stamp.tzinfo is None or not np.isfinite(now-stamp.timestamp()) or now < stamp.timestamp() or
                report.get('execution_enabled') is not False or report.get('read_only') is not True or
                report.get('strategy') != base['strategy']):
            raise ValueError('Invalid A/B/C research metadata')
        live = report.get('evaluation') == 'PROSPECTIVE_PAPER'
        state = ('RUNNING_PAPER' if now-stamp.timestamp() <= 90 and not report.get('completed') and
                 report.get('observer_state', 'RUNNING') == 'RUNNING' else
                 'FINISHED_OR_STALE') if live else 'OFFLINE_REPLAY_NOT_LIVE'
        return dict(base, available=True, evaluation=state,
            observed_at=stamp.isoformat(), last_signal=report.get('last_signal', {}),
            engines={engine: dict(summary=result.get('summary', {}), score=result.get('score', {}))
                     for engine, result in report.get('engines', {}).items()},
            limitations=report.get('limitations', []))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return base
