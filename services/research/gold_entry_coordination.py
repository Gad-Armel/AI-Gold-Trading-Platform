"""Stage correlated entries using fresh follow-through, independent of exits."""
import math
from datetime import datetime, timezone
from config import gold_consensus_settings as settings


def assess_entry_coordination(decision, positions, candles, *, now, bid, ask, contract_size=100,
                              scalp_priority=False):
    result = dict(policy='STAGED_EXPOSURE_V1', allowed=True, stage='INITIAL', blocks=[], peers=0)
    direction = decision.get('direction')
    peers = [p for p in positions if p.get('direction') == direction]
    result['peers'] = len(peers)
    if scalp_priority:
        result['policy']='STAGED_EXPOSURE_SCALP_PRIORITY_V1'
        if decision.get('horizon')=='SCALP':
            # Preserve the leading lane's access. This is only an allocation
            # decision; normal signal, quote, cost, capacity and risk gates
            # remain responsible for authorizing an actual order.
            result['stage']='LEADING_SCALP'
            return result
    if not decision.get('allowed') or direction not in ('BUY', 'SELL') or not peers:
        return result
    result['stage'] = 'FOLLOW_THROUGH'
    try:
        if not all(math.isfinite(v) for v in (now, bid, ask, contract_size)) or bid <= 0 or ask < bid or contract_size <= 0:
            raise ValueError('quote')
        sign = 1 if direction == 'BUY' else -1
        latest_entry = max(float(p['opened_epoch']) for p in peers)
        if not math.isfinite(latest_entry) or not 0 < latest_entry <= now:
            raise ValueError('position timestamp')
        for p in peers:
            entry, volume = float(p['entry_price']), float(p['volume'])
            if not all(math.isfinite(v) and v > 0 for v in (entry, volume)):
                raise ValueError('position')
            cushion = sign*((bid if sign == 1 else ask)-entry)*volume*contract_size
            dealing_noise = 2*(ask-bid)*volume*contract_size
            if cushion <= dealing_noise:
                result['blocks'].append('Same-direction exposure has not covered dealing noise; wait before adding another lane.')
                break
        rows = candles.to_dict('records') if hasattr(candles, 'to_dict') else candles or []
        completed = []
        for b in rows:
            raw = b['time']
            if hasattr(raw, 'timestamp'):
                stamp = raw.timestamp()
            elif isinstance(raw, str):
                value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                stamp = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
            else:
                stamp = float(raw)
            stamp -= settings.MT5_SERVER_UTC_OFFSET_SECONDS
            opened, closed = float(b['open']), float(b['close'])
            if not all(math.isfinite(v) for v in (stamp, opened, closed)) or min(opened, closed) <= 0:
                raise ValueError('candle')
            if stamp+300 <= now:
                completed.append((stamp, opened, closed))
        latest = max(completed, default=None)
        if (latest is None or latest[0] < latest_entry or now-latest[0]-300 > 120
                or sign*(latest[2]-latest[1]) <= 0):
            result['blocks'].append('Same-direction addition waits for a fresh completed M5 candle after the previous entry.')
    except (KeyError, TypeError, ValueError, OverflowError):
        result['blocks'].append('Correlated-entry confirmation unavailable; existing positions remain managed.')
    result['allowed'] = not result['blocks']
    if not result['allowed']:
        result['stage'] = 'WAIT'
    return result
