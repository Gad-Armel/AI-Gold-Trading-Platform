"""Single-position bid/ask replay with delayed fills and explicit censoring."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class ReplayConfig:
    latency: float = .35
    round_trip_cost: float = .3
    maximum_hold: float = 180.
    trailing_arm_r: float = .8
    trailing_gap_r: float = .45
    cooldown: float = 5.
    maximum_entry_risk: float = 3.
    breakeven_arm_r: float | None = None
    trailing_gap_atr: float | None = None


def summary(trades):
    values = [trade['net_price'] for trade in trades]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    return dict(trades=len(values), net_price=round(sum(values), 6), wins=len(wins),
                losses=len(losses), win_rate=len(wins)/len(values) if values else None,
                profit_factor=sum(wins)/-sum(losses) if losses else None,
                average_price=sum(values)/len(values) if values else None)


def replay(ticks, candidates, *, start, end, config=ReplayConfig(), tick_sequence=False):
    values = [config.latency, config.round_trip_cost, config.maximum_hold,
              config.trailing_arm_r, config.trailing_gap_r, config.cooldown, config.maximum_entry_risk,
              start, end]
    if (not np.isfinite(values).all() or config.latency <= 0 or config.round_trip_cost < 0 or
            min(config.maximum_hold, config.trailing_arm_r, config.trailing_gap_r, config.maximum_entry_risk) <= 0 or
            config.cooldown < 0 or end <= start or
            (config.breakeven_arm_r is not None and
             (not np.isfinite(config.breakeven_arm_r) or config.breakeven_arm_r <= 0)) or
            (config.trailing_gap_atr is not None and
             (not np.isfinite(config.trailing_gap_atr) or config.trailing_gap_atr <= 0))):
        raise ValueError('Finite positive execution/risk parameters and increasing window required')
    frame = ticks.sort_values('timestamp', kind='stable')
    frame = frame[(frame.timestamp >= start) & (frame.timestamp < end)]
    stamps, bids, asks = (frame[column].to_numpy(dtype=float) for column in ('timestamp', 'bid', 'ask'))
    if not np.isfinite(np.column_stack([stamps, bids, asks])).all() or np.any(bids <= 0) or np.any(asks < bids):
        raise ValueError('Replay requires finite valid bid/ask quotes')
    events = sorted([row for row in candidates if start <= row['feature_epoch'] < end],
                    key=lambda row: row['feature_epoch'])
    event_index, position, pending, available_at = 0, None, None, start
    previous_mid, run_sign, run_count, run_id = None, 0, 0, 0
    used_run = None
    trades, rejected = [], dict(expired=0, invalid_risk=0, gap_entry=0, duplicate_range=0)
    filled_ranges = set()
    for quote_index, stamp in enumerate(stamps):
        bid, ask = bids[quote_index], asks[quote_index]
        mid = (bid+ask)/2
        change = 0 if previous_mid is None else int(np.sign(round(mid-previous_mid, 8)))
        if change:
            if change == run_sign:
                run_count += 1
            else:
                run_sign, run_count, run_id = change, 1, run_id+1
        previous_mid = mid
        newest = None
        while event_index < len(events) and events[event_index]['feature_epoch'] <= stamp:
            newest = events[event_index]
            event_index += 1
        if pending is not None and stamp >= pending['due']:
            request, pending = pending, None
            if request['operation'] == 'entry':
                candidate = request['candidate']
                range_key = (candidate.get('range_id'), candidate['direction'])
                if range_key[0] is not None and range_key in filled_ranges:
                    rejected['duplicate_range'] += 1
                elif stamp >= candidate.get('valid_until_epoch', candidate['feature_epoch']+(2. if tick_sequence else 5.)):
                    rejected['expired'] += 1
                elif quote_index and stamp-stamps[quote_index-1] > 3:
                    rejected['gap_entry'] += 1
                else:
                    sign = 1 if candidate['direction'] == 'BUY' else -1
                    entry = ask if sign == 1 else bid
                    risk = sign*(entry-candidate['stop'])
                    entry_atr = candidate.get('atr')
                    if (not 0 < risk <= config.maximum_entry_risk or
                            (config.trailing_gap_atr is not None and
                             (entry_atr is None or not np.isfinite(entry_atr) or entry_atr <= 0))):
                        rejected['invalid_risk'] += 1
                    else:
                        position = dict(direction=candidate['direction'], sign=sign, entry=entry,
                            stop=candidate['stop'], risk=risk, entered_at=float(stamp), peak=0.,
                            setup=candidate.get('setup', 'TICK_RUN'), atr=entry_atr,
                            run_id=candidate.get('run_id', run_id), reason=None)
                        if range_key[0] is not None:
                            filled_ranges.add(range_key)
            elif position is not None:
                exit_price = bid if position['sign'] == 1 else ask
                gross = position['sign']*(exit_price-position['entry'])
                trades.append(dict(entered_at=position['entered_at'], exited_at=float(stamp),
                    direction=position['direction'], entry=position['entry'], exit=exit_price,
                    setup=position['setup'], gross_price=float(gross),
                    initial_risk_price=float(position['risk']),
                    net_price=float(gross-config.round_trip_cost), reason=request['reason'],
                    hold_seconds=float(stamp-position['entered_at'])))
                position, available_at = None, stamp+config.cooldown
        if position is not None:
            executable = bid if position['sign'] == 1 else ask
            excursion = position['sign']*(executable-position['entry'])
            position['peak'] = max(position['peak'], excursion)
            stopped = position['sign']*(executable-position['stop']) <= 0
            reason = None
            if stopped:
                reason = 'BROKER_SL'
            elif tick_sequence and (run_sign != position['sign'] or run_id != position['run_id'] or run_count >= 5):
                reason = 'TICK_REVERSAL_OR_FIFTH'
            elif not tick_sequence and position['peak'] >= config.trailing_arm_r*position['risk'] and (
                    excursion <= position['peak']-max(
                        config.trailing_gap_atr*position['atr'] if config.trailing_gap_atr is not None else
                        config.trailing_gap_r*position['risk'], 2*(ask-bid))):
                reason = 'DYNAMIC_TRAIL'
            elif not tick_sequence and newest is not None and newest.get('trend_sign') == -position['sign']:
                reason = 'M1_THESIS_INVERSION'
            elif (not tick_sequence and config.breakeven_arm_r is not None and
                  position['peak'] >= config.breakeven_arm_r*position['risk'] and
                  excursion <= config.round_trip_cost):
                reason = 'BREAKEVEN_PROTECTION'
            elif stamp-position['entered_at'] >= config.maximum_hold:
                reason = 'TIME_EXIT'
            if stopped:
                trades.append(dict(entered_at=position['entered_at'], exited_at=float(stamp),
                    direction=position['direction'], entry=position['entry'], exit=float(executable),
                    setup=position['setup'], gross_price=float(excursion),
                    initial_risk_price=float(position['risk']),
                    net_price=float(excursion-config.round_trip_cost), reason=reason,
                    hold_seconds=float(stamp-position['entered_at'])))
                position, pending, available_at = None, None, stamp+config.cooldown
            elif reason and pending is None:
                pending = dict(operation='exit', due=stamp+config.latency, reason=reason)
        if position is None and pending is None and stamp >= available_at:
            candidate = None
            if tick_sequence and change and run_count == 2 and used_run != run_id:
                candidate = dict(feature_epoch=float(stamp), direction='BUY' if run_sign == 1 else 'SELL',
                                 stop=float(bid-2 if run_sign == 1 else ask+2), run_id=run_id)
                used_run = run_id
            elif not tick_sequence and newest is not None and newest['direction'] in ('BUY', 'SELL'):
                candidate = newest
            if candidate is not None:
                pending = dict(operation='entry', due=stamp+config.latency, candidate=candidate)
    return dict(summary=summary(trades), trades=trades, rejected=rejected,
                censored_positions=int(position is not None), unfilled_requests=int(pending is not None),
                modeled_quantity_ounces=1., read_only=True)
