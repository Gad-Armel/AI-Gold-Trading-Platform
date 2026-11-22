"""Per-ticket executable profit giveback; independent of candle availability."""
import math
from config import gold_consensus_settings as settings


def bind_exit_positions(positions, state, *, now, bid, ask):
    signature = sorted([[p['ticket'], p['direction'], p['entry_price'], p['volume']] for p in positions])
    if state.get('position_signature') != signature:
        prior = state.get('ticket_profit_peaks', {})
        bindings = {str(p[0]):p for p in state.get('position_signature', [])}
        retained = {}
        for ticket, direction, entry_price, size in signature:
            old = bindings.get(str(ticket))
            if old and old[1:3] == [direction, entry_price] and str(ticket) in prior:
                retained[str(ticket)] = prior[str(ticket)]*size/old[3]
        volume = sum(p['volume'] for p in positions)
        entry = sum(p['entry_price']*p['volume'] for p in positions)/volume
        move = bid-entry if positions[0]['direction'] == 'BUY' else entry-ask
        state.clear()
        state.update(position_signature=signature, started=now, adverse_since=None,
                     peak_move=move, trough_move=move,
                     ticket_profit_peaks=retained)


def profit_lock_exit(positions, state, *, now, bid, ask, feed_age, config, contract_size):
    result = dict(close=False, policy='PER_POSITION_PROFIT_LOCK_V1', reason='Profit lock not triggered')
    arm = float(config.get('profit_lock_arm_usd', 0))
    retain = float(config.get('profit_lock_retained_fraction', .8))
    if not positions or arm <= 0 or not 0 < retain < 1:
        return result
    try:
        noise_spreads = float(config.get('profit_lock_noise_spreads', 0.))
        minimum_retained = float(config.get('profit_lock_min_retained_usd', .30))
    except (TypeError, ValueError):
        return dict(result, reason='Profit lock unavailable: invalid noise configuration')
    if (not math.isfinite(noise_spreads) or noise_spreads < 0 or
            not math.isfinite(minimum_retained) or minimum_retained < 0):
        return dict(result, reason='Profit lock unavailable: invalid noise configuration')
    noise_aware = noise_spreads > 0
    if noise_aware and minimum_retained <= 0:
        return dict(result, reason='Profit lock unavailable: positive retained floor required')
    if (not all(math.isfinite(v) for v in (now, bid, ask, feed_age, contract_size))
            or not 0 <= feed_age <= settings.EXIT_MAX_FEED_AGE_SECONDS
            or min(bid, ask, contract_size) <= 0 or ask < bid):
        return dict(result, reason='Profit lock unavailable: invalid or stale quote')
    if any(p.get('direction') not in ('BUY','SELL') or
           not all(isinstance(p.get(k), (int,float)) and math.isfinite(p[k]) and p[k] > 0
                   for k in ('ticket','entry_price','volume')) for p in positions):
        return dict(result, reason='Profit lock unavailable: invalid position data')
    bind_exit_positions(positions, state, now=now, bid=bid, ask=ask)
    peaks = state.setdefault('ticket_profit_peaks', {})
    closing = []
    thresholds = {}
    givebacks = {}
    for p in positions:
        key = str(p['ticket'])
        sign = 1 if p['direction'] == 'BUY' else -1
        profit = sign*((bid if sign == 1 else ask)-p['entry_price'])*p['volume']*contract_size
        if not math.isfinite(profit):
            continue
        peak = max(float(peaks.get(key, profit)), profit)
        peaks[key] = peak
        threshold = retain*peak
        if noise_aware and peak > 0:
            exposure = p['volume']*contract_size
            allowance = max((1-retain)*peak, noise_spreads*(ask-bid)*exposure)
            # A noise allowance may not spend the configured positive remainder.
            allowance = min(allowance, max(0., peak-minimum_retained))
            threshold = peak-allowance
        thresholds[key] = threshold
        givebacks[key] = max(0., peak-threshold)
        armed = peak >= arm and (not noise_aware or peak >= minimum_retained)
        if armed and profit <= threshold+1e-8:
            closing.append(p['ticket'])
    return dict(result, close=bool(closing), close_tickets=closing,
                ticket_profit_peaks=dict(peaks),
                ticket_profit_thresholds=thresholds, ticket_giveback_allowances=givebacks,
                noise_aware=noise_aware,
                reason=(f'Noise-aware profit lock: spread allowance with ${minimum_retained:.2f} retained floor'
                        if noise_aware else
                        f'Profit lock: retained {retain:.0%} of position peak after ${arm:.2f} arm')
                       if closing else result['reason'])
