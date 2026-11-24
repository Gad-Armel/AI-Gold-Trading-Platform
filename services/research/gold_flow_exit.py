"""Bounded, causal quote-flow protection. Heuristic, not a return forecast.

This is the only exit source that sees between completed candles, so it is
what notices a position turning against itself inside the bar.

Thresholds are derived from live ATR and spread. They were previously fixed
dollars (0.35 / 0.70 / 1.50) chosen at ~$2,000 gold; by ~$4,270 with M5 ATR
~$5.71 those had decayed to ~0.06 ATR, which is dealing noise rather than
directional flow.
"""
import math

from config import gold_consensus_settings as settings


def evaluate_flow_exit(positions, state, *, now, quote_time, bid, ask, horizon, atr=None):
    result = dict(close=False, policy='QUOTE_FLOW_V2', reason='Waiting for sustained quote-flow deterioration')
    if not positions:
        state.clear()
        return result
    signature = sorted((p['ticket'], p['direction'], p['entry_price'], p['volume']) for p in positions)
    if state.get('signature') != signature:
        state.clear()
        state.update(signature=signature, samples=[], adverse_since=None)
    ceiling = float(settings.EXIT_MAX_FEED_AGE_SECONDS)
    # A quiet market still has an executable price; only a genuinely stale or
    # future-dated broker tick makes flow unreadable.
    if (not all(math.isfinite(x) for x in (now, quote_time, bid, ask))
            or not -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS <= now-quote_time <= ceiling or bid <= 0 or ask < bid):
        state.update(samples=[], adverse_since=None)
        return dict(result, reason='Flow exit unavailable: invalid or stale quote')
    if len({p['direction'] for p in positions}) != 1:
        return dict(result, close=True, reason='Mixed lane directions')
    config = dict(settings.FLOW_EXIT_CONFIG[horizon])
    window = float(config['window_seconds'])
    confirmation = float(config['confirmation_seconds'])
    samples = state['samples']
    if samples and quote_time <= samples[-1][0]:
        # Repeated timestamps cannot advance confirmation, including at retry.
        return dict(result, reason='Waiting for a new quote')
    if samples and quote_time-samples[-1][0] > max(6.0, ceiling/2.0):
        samples.clear()
        state['adverse_since'] = None
    samples.append((quote_time, bid, ask))
    samples[:] = [s for s in samples if quote_time-s[0] <= window+4][-256:]
    sign = 1 if positions[0]['direction'] == 'BUY' else -1
    entry = sum(p['entry_price']*p['volume'] for p in positions)/sum(p['volume'] for p in positions)
    move = sign*((bid if sign == 1 else ask)-entry)
    state['peak'] = max(state.get('peak', move), move)
    if len(samples) < 5 or samples[-1][0]-samples[0][0] < window:
        return result
    # Both executable quote sides must move against the trade: spread widening
    # on its own is not directional flow. No inferred aggressor or order volume.
    bid_move, ask_move = bid-samples[0][1], ask-samples[0][2]
    mids = [(s[1]+s[2])/2 for s in samples]
    path = sum(abs(b-a) for a,b in zip(mids,mids[1:]))
    efficiency = abs(mids[-1]-mids[0])/path if path else 0
    spread = max(s[2]-s[1] for s in samples)
    volatility = float(atr) if atr is not None and math.isfinite(float(atr)) and float(atr) > 0 else 0.0
    threshold = max(float(config['atr_threshold'])*volatility,
                    float(settings.FLOW_EXIT_SPREAD_FLOOR)*spread)
    opposing = (min(-sign*bid_move, -sign*ask_move) >= threshold
                and efficiency >= float(settings.FLOW_EXIT_MIN_EFFICIENCY))
    damaged = move <= -threshold or (state['peak'] >= threshold and state['peak']-move >= threshold)
    if opposing and damaged:
        if state['adverse_since'] is None:
            state['adverse_since'] = quote_time
    else:
        state['adverse_since'] = None
    close = state['adverse_since'] is not None and quote_time-state['adverse_since'] >= confirmation
    return dict(result, close=close, reason='Sustained executable quote reversal with loss or profit giveback' if close else result['reason'],
                window_seconds=window, efficiency=efficiency, threshold=threshold, peak_move=state['peak'], move=move)
