"""Causal XAUUSD setup candidates; optional veto, never independent order authority."""
from dataclasses import dataclass
import copy
import hashlib
import math

import pandas as pd

from services.research.gold_scalp_setups import _bars


VERSION = 1
PERIODS = {'M1': 60, 'M5': 300, 'M15': 900, 'H1': 3600}


@dataclass(frozen=True)
class SmcConfig:
    swing_wing: int = 2
    atr_bars: int = 14
    volume_bars: int = 20
    displacement_atr: float = .6
    minimum_rvol: float = 1.2
    break_buffer_atr: float = .05
    retest_tolerance_atr: float = .1
    stop_buffer_atr: float = .2
    setup_ttl_bars: int = 3
    ob_search_bars: int = 5
    ob_expiry_seconds: float = 21600
    level_expiry_seconds: float = 86400
    min_stop_spreads: float = 6.
    max_cost_r: float = .2
    min_room_cost_multiple: float = 3.
    commission_price: float | None = None
    slippage_price: float | None = None

    def __post_init__(self):
        for name, lower, upper in (('swing_wing', 1, 5), ('atr_bars', 2, 50),
                                   ('volume_bars', 2, 50), ('setup_ttl_bars', 1, 10),
                                   ('ob_search_bars', 1, 10)):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f'Invalid {name}')
        for name in ('displacement_atr', 'minimum_rvol', 'break_buffer_atr',
                     'retest_tolerance_atr', 'stop_buffer_atr', 'ob_expiry_seconds', 'level_expiry_seconds',
                     'min_stop_spreads', 'max_cost_r', 'min_room_cost_multiple'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'Invalid {name}')
        for value in (self.commission_price, self.slippage_price):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError('Costs must be known nonnegative price distances, or None')


def completed_frame(raw, *, seconds, now, offset, minimum):
    frame = _bars(raw, seconds, offset, now)
    if (len(frame) < minimum or not math.isfinite(float(frame.available.iloc[-1]))
            or not 0 <= now-float(frame.available.iloc[-1]) < seconds+5
            or not all(math.isfinite(float(value)) for value in frame.available)
            or any(abs(float(gap)-seconds) >= .01 for gap in frame.available.diff().dropna())):
        raise ValueError('Insufficient, stale or discontinuous completed candles')
    if 'tick_volume' not in frame:
        raise ValueError('Broker tick activity is required, not synthesized')
    frame['tick_volume'] = pd.to_numeric(frame.tick_volume, errors='coerce')
    if any(not math.isfinite(float(value)) or value < 0 for value in frame.tick_volume):
        raise ValueError('Invalid broker tick activity')
    return frame


def structure(frame, config):
    rows = frame.to_dict('records')
    swings, breaks = [], []
    latest = {}
    broken = set()
    direction = 0
    true_ranges = []
    for index, bar in enumerate(rows):
        previous_close = rows[index-1]['close'] if index else bar['open']
        scale = sum(true_ranges[-config.atr_bars:])/config.atr_bars if len(true_ranges) >= config.atr_bars else None
        history = rows[max(0, index-config.volume_bars):index]
        average = sum(row['tick_volume'] for row in history)/config.volume_bars if len(history) == config.volume_bars else 0
        bar['atr_before'] = scale
        bar['rvol'] = bar['tick_volume']/average if average > 0 else None
        anchor = index-config.swing_wing
        if anchor >= config.swing_wing:
            neighborhood = rows[anchor-config.swing_wing:index+1]
            pivot = rows[anchor]
            for kind, column, comparison in (('HIGH', 'high', max), ('LOW', 'low', min)):
                others = [row[column] for position, row in enumerate(neighborhood) if position != config.swing_wing]
                if pivot[column] == comparison([pivot[column], *others]) and pivot[column] not in others:
                    swing = dict(kind=kind, price=float(pivot[column]), anchor_at=float(pivot['available']),
                                 known_at=float(bar['available']), known_index=index)
                    swings.append(swing)
                    latest[kind] = swing
        if scale and scale > 0:
            for sign, kind in ((1, 'HIGH'), (-1, 'LOW')):
                swing = latest.get(kind)
                identity = (kind, swing['anchor_at']) if swing else None
                if (swing and identity not in broken and sign*(bar['close']-swing['price']) > config.break_buffer_atr*scale
                        and sign*(previous_close-swing['price']) <= config.break_buffer_atr*scale):
                    event = dict(index=index, direction=sign, level=swing['price'], known_at=float(bar['available']),
                                 kind='CHOCH' if direction == -sign else 'BOS', atr=scale,
                                 displacement=sign*(bar['close']-bar['open']) >= config.displacement_atr*scale,
                                 rvol=bar['rvol'], source_swing=copy.deepcopy(swing))
                    breaks.append(event)
                    direction = sign
                    broken.add(identity)
        true_ranges.append(max(bar['high']-bar['low'], abs(bar['high']-previous_close), abs(bar['low']-previous_close)))
    return dict(rows=rows, swings=swings, breaks=breaks, direction=direction)


def _volume_ok(bar, config):
    return bar.get('rvol') is not None and bar['rvol'] >= config.minimum_rvol


def _candidate(model, sign, anchor, trigger, level, stop, bar, zones):
    return dict(id=f'{model}:{sign}:{anchor:.3f}:{trigger:.3f}', model=model,
                direction='BUY' if sign == 1 else 'SELL', sign=sign, anchor_at=anchor,
                known_at=trigger, reference_level=level, stop_loss=stop,
                rvol=bar.get('rvol'), zones=zones, execution_enabled=False)


def _sweeps(data, config):
    rows, result = data['rows'], []
    last_index = len(rows)-1
    last = rows[-1]
    for index in range(max(config.atr_bars, last_index-config.setup_ttl_bars), last_index):
        bar = rows[index]
        scale = bar['atr_before']
        if not scale or scale <= 0:
            continue
        known = [swing for swing in data['swings'] if swing['known_index'] < index]
        for sign, pool_kind, break_kind in ((1, 'LOW', 'HIGH'), (-1, 'HIGH', 'LOW')):
            pools = [swing for swing in known if swing['kind'] == pool_kind]
            triggers = [swing for swing in known if swing['kind'] == break_kind]
            if not pools or not triggers:
                continue
            pool, trigger = pools[-1], triggers[-1]
            extreme = bar['low'] if sign == 1 else bar['high']
            swept = sign*(pool['price']-extreme) >= config.break_buffer_atr*scale
            reclaimed = sign*(bar['close']-pool['price']) > 0
            intervening = rows[index+1:-1]
            if (not swept or not reclaimed or any(sign*(row['close']-pool['price']) <= 0 for row in intervening)
                    or any(sign*(row['close']-trigger['price']) > 0 for row in intervening)):
                continue
            if (sign*(last['close']-trigger['price']) > config.break_buffer_atr*scale
                    and sign*(last['close']-last['open']) >= config.displacement_atr*scale
                    and _volume_ok(last, config)):
                stop_extreme = min(row['low'] for row in rows[index:]) if sign == 1 else max(row['high'] for row in rows[index:])
                result.append(_candidate('SWEEP_RECLAIM', sign, bar['available'], last['available'],
                    pool['price'], stop_extreme-sign*config.stop_buffer_atr*scale, last, [pool, trigger]))
    return result


def _flips(data, config):
    result, rows = [], data['rows']
    last_index, last = len(rows)-1, rows[-1]
    for event in data['breaks']:
        age = last_index-event['index']
        if not 1 <= age <= config.setup_ttl_bars or not event['displacement']:
            continue
        if event['rvol'] is None or event['rvol'] < config.minimum_rvol:
            continue
        sign, level, scale = event['direction'], event['level'], event['atr']
        earlier = rows[event['index']+1:-1]
        def touched(bar):
            return bar['low'] <= level+config.retest_tolerance_atr*scale if sign == 1 else bar['high'] >= level-config.retest_tolerance_atr*scale
        if any(touched(bar) or sign*(bar['close']-level) <= 0 for bar in earlier):
            continue
        if (touched(last) and sign*(last['close']-level) > 0
                and sign*(last['close']-last['open']) > 0 and _volume_ok(last, config)):
            extreme = min(last['low'], level) if sign == 1 else max(last['high'], level)
            result.append(_candidate('SR_FLIP_RETEST', sign, event['known_at'], last['available'], level,
                extreme-sign*config.stop_buffer_atr*scale, last, [event['source_swing']]))
    return result


def _orderblocks(one, five, config):
    result, last = [], one['rows'][-1]
    for event in five['breaks']:
        if not event['displacement'] or event['rvol'] is None or event['rvol'] < config.minimum_rvol:
            continue
        if not 0 < last['available']-event['known_at'] <= config.ob_expiry_seconds:
            continue
        sign, index = event['direction'], event['index']
        origins = [bar for bar in five['rows'][max(0, index-config.ob_search_bars):index]
                   if sign*(bar['close']-bar['open']) < 0]
        if not origins:
            continue
        origin = origins[-1]
        low, high = origin['low'], origin['high']
        since = [bar for bar in one['rows'] if event['known_at'] < bar['available'] < last['available']]
        if not one['rows'][0]['available'] <= event['known_at']:
            continue
        if any(bar['low'] <= high and bar['high'] >= low for bar in since):
            continue
        if any(sign*(bar['close']-(low if sign == 1 else high)) <= 0 for bar in since):
            continue
        scale = last['atr_before']
        if (scale and last['low'] <= high and last['high'] >= low and _volume_ok(last, config)
                and sign*(last['close']-(high if sign == 1 else low)) > 0
                and sign*(last['close']-last['open']) > 0):
            zone = dict(kind='ORDER_BLOCK', low=low, high=high, anchor_at=origin['available'], known_at=event['known_at'], state='FIRST_RETEST')
            result.append(_candidate('OB_CONTINUATION', sign, event['known_at'], last['available'],
                high if sign == 1 else low, (low if sign == 1 else high)-sign*config.stop_buffer_atr*scale,
                last, [zone, event['source_swing']]))
    return result


def candidate_cost(candidate, *, bid, ask, structures, config):
    sign = candidate['sign']
    entry = ask if sign == 1 else bid
    risk = sign*(entry-candidate['stop_loss'])
    spread = ask-bid
    opposite = [swing['price'] for data in structures.values() for swing in data['swings']
                if swing['kind'] == ('HIGH' if sign == 1 else 'LOW') and sign*(swing['price']-entry) > 0
                and 0 <= candidate['known_at']-swing['known_at'] <= config.level_expiry_seconds]
    target = (min(opposite) if sign == 1 else max(opposite)) if opposite else None
    blocks = []
    if risk <= 0 or candidate['stop_loss'] <= 0:
        blocks.append('Structural stop is invalid at current executable price')
    if risk < config.min_stop_spreads*spread:
        blocks.append('Structural stop is too close relative to spread')
    if target is None:
        blocks.append('No known opposing liquidity level beyond entry')
    friction = None
    cost_r = None
    if config.commission_price is None or config.slippage_price is None:
        blocks.append('Round-trip commission/slippage assumptions are not configured')
    else:
        friction = spread+config.commission_price+config.slippage_price
        cost_r = friction/risk if risk > 0 else None
        if cost_r is None or cost_r > config.max_cost_r:
            blocks.append('All-in estimated friction exceeds the stop-relative budget')
        if target is not None and sign*(target-entry) < config.min_room_cost_multiple*friction:
            blocks.append('Room to opposing liquidity is insufficient relative to estimated friction')
    return dict(entry=entry, stop_distance=risk, opposing_level=target, spread=spread,
                friction_price=friction, cost_r=cost_r, blocks=blocks,
                expected_value=None, calibrated_probability=None)


class SmcStrategy:
    def __init__(self, config=None):
        self.config = config or SmcConfig()
        self.key = None
        self.cached = None
        self.builds = 0

    def assess(self, candles, *, now, bid, ask, offset):
        base = dict(available=False, execution_enabled=False, version=VERSION, candidates=[],
                    role='SMC_RESEARCH', calibrated_probability=None)
        try:
            if not all(math.isfinite(value) for value in (now, bid, ask, offset)) or bid <= 0 or ask < bid:
                raise ValueError('Invalid clock or executable quote')
            minimum = max(self.config.atr_bars, self.config.volume_bars, self.config.swing_wing*2)+2
            frames = {name: completed_frame(candles.get(name), seconds=seconds, now=now,
                       offset=offset, minimum=minimum) for name, seconds in PERIODS.items()}
            key = tuple((name, hashlib.sha256(pd.util.hash_pandas_object(
                frame[['available', 'open', 'high', 'low', 'close', 'tick_volume']], index=False).values.tobytes()).hexdigest())
                        for name, frame in frames.items())
            if key != self.key:
                structures = {name: structure(frame, self.config) for name, frame in frames.items()}
                one, five = structures['M1'], structures['M5']
                candidates = _sweeps(one, self.config)+_flips(one, self.config)+_orderblocks(one, five, self.config)
                self.cached = (structures, {candidate['id']: candidate for candidate in candidates})
                self.key = key
                self.builds += 1
            structures, raw = self.cached
            output = []
            context = {name: data['direction'] for name, data in structures.items() if name != 'M1'}
            for candidate in raw.values():
                item = copy.deepcopy(candidate)
                cost = candidate_cost(item, bid=bid, ask=ask, structures=structures, config=self.config)
                item.update(cost)
                if any(direction == -item['sign'] for direction in context.values()):
                    item['blocks'].append('Confirmed higher-timeframe structure opposes the setup')
                if item['model'] == 'OB_CONTINUATION' and context['M5'] != item['sign']:
                    item['blocks'].append('Order-block continuation requires aligned M5 structure')
                item['eligible'] = not item['blocks']
                output.append(item)
            return dict(base, available=True, observed_at=now,
                        feature_epoch=float(frames['M1'].available.iloc[-1]),
                        valid_until=float(frames['M1'].available.iloc[-1])+60,
                        context=context, candidates=output, builds=self.builds,
                        reason='Deterministic candidate geometry; no measured profitability or calibrated EV')
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
            return dict(base, reason=str(error))


def apply_smc_policy(decision, report, *, policy, now):
    if policy not in ('observe', 'filter'):
        raise ValueError('Invalid SMC policy')
    decision['smc_strategy'] = copy.deepcopy(report)
    decision['smc_strategy']['policy'] = policy
    if policy == 'observe' or not decision.get('allowed'):
        return
    try:
        stamps = (float(report['feature_epoch']), float(report['valid_until']), float(now))
        fresh = bool(report.get('available') and all(math.isfinite(value) for value in stamps)
                     and stamps[0] <= stamps[2] < stamps[1])
    except (KeyError, TypeError, ValueError, OverflowError):
        fresh = False
    matching = [item for item in report.get('candidates', [])
                if item.get('direction') == decision.get('direction') and item.get('eligible') is True]
    if not fresh or not matching:
        decision['allowed'] = False
        decision.setdefault('blocks', []).append('SMC filter: no fresh, cost-feasible same-direction setup')
    else:
        decision['smc_strategy']['matched_setup_ids'] = [item['id'] for item in matching]
