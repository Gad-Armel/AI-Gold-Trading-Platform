"""Add to profitable SCALP exposure without averaging down or hedging it."""
import math
from config import gold_consensus_settings as settings


def addition_blocks(decision, positions, bid, ask):
    if not positions:
        return []
    direction = decision.get('direction')
    vote_mode = decision.get('entry_mode') == 'THREE_SOURCE_VOTE'
    if vote_mode and len(positions) >= min(3, int(decision.get('source_position_limit', 0))):
        return ['Strong-source position allowance reached.']
    if direction not in ('BUY', 'SELL') or any(p['direction'] != direction for p in positions):
        return ['SCALP additions require the same direction as every open SCALP position.']
    try:
        if len(positions) >= 3:
            evidence = float(decision.get('evidence', 0.0))
            if not math.isfinite(evidence) or evidence < settings.SCALP_EXTENDED_POSITION_EVIDENCE:
                return [f'Fourth and fifth SCALP positions require evidence >= {settings.SCALP_EXTENDED_POSITION_EVIDENCE:.0f}/100.']
        if not all(math.isfinite(float(v)) for v in (bid, ask)) or bid <= 0 or ask < bid:
            raise ValueError('quote')
        sign = 1 if direction == 'BUY' else -1
        for p in positions:
            stop = float(p.get('sl', 0))
            if not math.isfinite(stop) or stop <= 0 or (stop >= bid if sign == 1 else stop <= ask):
                return ['SCALP additions require a valid broker SL on every existing position.']
            entry, volume = float(p['entry_price']), float(p['volume'])
            profit = float(p['profit'])
            if not all(math.isfinite(v) for v in (entry, volume, profit)) or min(entry, volume) <= 0:
                raise ValueError('position')
            cushion = sign * ((bid if sign == 1 else ask) - entry) * volume * 100
            if profit <= 0 or cushion <= 2 * (ask - bid) * volume * 100:
                return ['SCALP additions wait until every open position is profitable beyond dealing noise.']
    except (KeyError, TypeError, ValueError, OverflowError):
        return ['SCALP addition profit/quote validation unavailable.']
    return []
