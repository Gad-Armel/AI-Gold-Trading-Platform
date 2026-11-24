"""Tick-built thirty-second candles for observation only, never entry authority."""
import math
from statistics import median


def s30_observation(ticks, *, now, commission_price=None, slippage_price=None, bar_count=3,
                    require_micro_confirmation=True, period_seconds=30, require_range_cost_screen=True,
                    range_cost_multiple=3., micro_window_seconds=6, activity_mode=False):
    if isinstance(micro_window_seconds, bool) or micro_window_seconds not in (3, 6):
        raise ValueError('Micro confirmation window must be three or six seconds')
    if isinstance(period_seconds, bool) or period_seconds not in (1, 5, 15, 30):
        raise ValueError('Supported fast candle periods are 1, 5, 15 and 30 seconds')
    timeframe = f'S{period_seconds}'
    if isinstance(bar_count, bool) or bar_count not in (1, 2, 3, 5, 6):
        raise ValueError('Fast confirmation requires 1, 2, 3, 5 or 6 bars')
    if (isinstance(range_cost_multiple, bool) or not isinstance(range_cost_multiple, (int, float))
            or not math.isfinite(range_cost_multiple) or range_cost_multiple < 1):
        raise ValueError('Finite range cost multiple of at least one required')
    lookback = max(12, (bar_count+1)*period_seconds)
    result = dict(available=False, execution_enabled=False, role='SHADOW_ONLY',
                  timeframe=timeframe, direction='WAIT', bars=[], observed_epoch=now)
    if not math.isfinite(now):
        return dict(result, reason='Invalid observation time')
    if ticks is None or len(ticks) == 0:
        return dict(result, reason='No tick history')
    if hasattr(ticks, 'to_dict'):
        ticks = ticks[(ticks.timestamp >= now-lookback) & (ticks.timestamp <= now)].to_dict('records')
    usable = []
    try:
        for tick in ticks:
            stamp, bid, ask = (float(tick[key]) for key in ('timestamp', 'bid', 'ask'))
            if not all(math.isfinite(value) for value in (stamp, bid, ask)) or bid <= 0 or ask < bid:
                continue
            if now-lookback <= stamp <= now:
                usable.append((stamp, bid, ask))
    except (KeyError, TypeError, ValueError):
        return dict(result, reason='Invalid tick history')
    usable = sorted(dict.fromkeys(usable), key=lambda tick: tick[0])
    if not usable or now-usable[-1][0] > min(3., period_seconds):
        return dict(result, reason='Tick history is stale')
    last_end = math.floor(now/period_seconds)*period_seconds
    bars = []
    for start in range(last_end-bar_count*period_seconds, last_end, period_seconds):
        group = [tick for tick in usable if start <= tick[0] < start+period_seconds]
        boundaries = [start]+[tick[0] for tick in group]+[start+period_seconds]
        maximum_gap = min(5., period_seconds/3.)
        observed_gap = max(current-previous for previous, current in zip(boundaries, boundaries[1:]))
        if len(group) < 2 or observed_gap > maximum_gap:
            return dict(result, bars=bars,
                        coverage=dict(bar_start=start, ticks=len(group),
                                      maximum_gap_seconds=observed_gap,
                                      allowed_gap_seconds=maximum_gap),
                        reason=(f'Incomplete {timeframe} tick coverage; no synthetic fill '
                                f'({len(group)} ticks, largest gap {observed_gap:.2f}s; '
                                f'limit {maximum_gap:.2f}s)'))
        mids = [(bid+ask)/2 for _, bid, ask in group]
        bars.append(dict(time=start, open=mids[0], high=max(mids), low=min(mids), close=mids[-1],
                         ticks=len(group), maximum_spread=max(ask-bid for _, bid, ask in group)))
    bodies = [bar['close']-bar['open'] for bar in bars]
    direction = 'BUY' if all(body > 0 for body in bodies) else 'SELL' if all(body < 0 for body in bodies) else 'WAIT'
    fast = fast_candidate(usable, bars, now=now, direction=direction,
                          commission_price=commission_price, slippage_price=slippage_price,
                          require_micro_confirmation=require_micro_confirmation, timeframe=timeframe,
                          require_range_cost_screen=require_range_cost_screen,
                          range_cost_multiple=range_cost_multiple, micro_window_seconds=micro_window_seconds,
                          activity_mode=activity_mode)
    return dict(result, available=True, bars=bars, direction=direction, fast_candidate=fast,
                reason=f'{bar_count} completed midpoint {timeframe} candles; costs are not a profit forecast')


def fast_candidate(ticks, bars, *, now, direction, commission_price=None, slippage_price=None,
                   require_micro_confirmation=True, timeframe='S30', require_range_cost_screen=True,
                   range_cost_multiple=3., micro_window_seconds=6, activity_mode=False):
    if isinstance(micro_window_seconds, bool) or micro_window_seconds not in (3, 6):
        raise ValueError('Micro confirmation window must be three or six seconds')
    if (isinstance(range_cost_multiple, bool) or not isinstance(range_cost_multiple, (int, float))
            or not math.isfinite(range_cost_multiple) or range_cost_multiple < 1):
        raise ValueError('Finite range cost multiple of at least one required')
    result = dict(execution_enabled=False, role='SHADOW_ONLY', setup=f'{timeframe}_TICK_CONTINUATION',
                  direction=direction, calibrated_probability=None, expected_value=None,
                  pattern_ready=False, cost_screen_passed=None, blocks=[], warnings=[],
                  setup_id=f"{timeframe}:{bars[-1]['time']}:{direction}")
    blocks = result['blocks']
    if direction not in {'BUY', 'SELL'}:
        blocks.append(f'Completed {timeframe} candles do not agree')
    recent = [tick for tick in ticks if now-micro_window_seconds <= tick[0] <= now]
    boundaries = [now-micro_window_seconds] + [tick[0] for tick in recent] + [now]
    window_name = 'Three' if micro_window_seconds == 3 else 'Six'
    if len(recent) < 4 or max(current-previous for previous, current in zip(boundaries, boundaries[1:])) > 2:
        blocks.append(f'Insufficient continuous {window_name.lower()}-second quote coverage')
    mids = [(bid+ask)/2 for _, bid, ask in recent]
    net = mids[-1]-mids[0] if mids else 0.
    path = sum(abs(current-previous) for previous, current in zip(mids, mids[1:]))
    raw_efficiency = abs(net)/path if path else 0.
    second_closes = {}
    for tick, midpoint in zip(recent, mids):
        second_closes[math.floor(tick[0])] = midpoint
    sampled = ([mids[0]] if mids else []) + list(second_closes.values())
    sampled_path = sum(abs(current-previous) for previous, current in zip(sampled, sampled[1:]))
    efficiency = abs(net)/sampled_path if sampled_path else 0.
    sign = 1 if direction == 'BUY' else -1 if direction == 'SELL' else 0
    spread = ticks[-1][2]-ticks[-1][1]
    spread_reference = sorted(ask-bid for _, bid, ask in ticks)[len(ticks)//2]
    ranges = sorted(bar['high']-bar['low'] for bar in bars)
    range_proxy = median(ranges)
    extension = sign*((ticks[-1][1]+ticks[-1][2])/2-bars[-1]['close'])
    movement_floor = .1*spread if activity_mode else spread
    efficiency_floor = .35 if activity_mode else .65
    if sign*net <= movement_floor or efficiency < efficiency_floor:
        destination = blocks if require_micro_confirmation else result['warnings']
        destination.append(f'{window_name}-second follow-through is too weak relative to spread or too noisy')
    bid_move = sign*(recent[-1][1]-recent[0][1]) if recent else 0.
    ask_move = sign*(recent[-1][2]-recent[0][2]) if recent else 0.
    executable_confirmation = sign != 0 and min(bid_move, ask_move) > 0
    if not executable_confirmation:
        destination = blocks if require_micro_confirmation else result['warnings']
        destination.append('Both bid and ask must progress in the signal direction; midpoint alone is insufficient')
    if spread > 1.5*spread_reference:
        blocks.append('Spread expansion')
    if extension < -spread or extension > range_proxy:
        blocks.append(f'Current quote has reversed or is extended beyond one recent {timeframe} range')
    result.update(pattern_ready=not blocks, micro_window_seconds=micro_window_seconds,
                  activity_mode=activity_mode, movement_floor_price=movement_floor,
                  efficiency_floor=efficiency_floor,
                  quote_efficiency=round(efficiency, 4),
                  executable_confirmation=executable_confirmation,
                  signed_bid_move_price=bid_move, signed_ask_move_price=ask_move,
                  micro_confirmation_enforced=require_micro_confirmation,
                  raw_tick_efficiency=round(raw_efficiency, 4), efficiency_sampling_seconds=1,
                  signed_move_price=sign*net, spread_price=spread,
                  recent_range_proxy_price=range_proxy, extension_price=extension)
    costs = (commission_price, slippage_price)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not math.isfinite(value) or value < 0 for value in costs):
        blocks.append('Explicit round-trip commission and slippage price equivalents required')
    else:
        cost = spread+commission_price+slippage_price
        result.update(round_trip_cost_price=cost, cost_screen_passed=range_proxy > range_cost_multiple*cost,
                      range_cost_multiple=range_cost_multiple,
                      range_cost_screen_enforced=require_range_cost_screen)
        if not result['cost_screen_passed']:
            destination = blocks if require_range_cost_screen else result['warnings']
            multiple = 'three' if range_cost_multiple == 3 else f'{range_cost_multiple:g}'
            destination.append(f'Recent {timeframe} range does not clear {multiple} times estimated round-trip cost')
    result['research_candidate'] = (result['pattern_ready'] and not blocks and
                                   (result['cost_screen_passed'] is True or not require_range_cost_screen))
    return result
