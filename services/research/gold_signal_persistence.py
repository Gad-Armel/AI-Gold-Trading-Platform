"""Elapsed confirmation belongs to one directional signal source."""
import math


def update_signal_persistence(state, *, direction, source, now):
    if not math.isfinite(now):
        raise ValueError('Finite monotonic observation time required')
    same = (direction in ('BUY', 'SELL') and direction == state.get('direction')
            and source == state.get('signal_source') and state.get('signal_since') is not None
            and now >= state['signal_since'])
    if same:
        state['cycles'] = state.get('cycles', 0)+1
    elif direction in ('BUY', 'SELL'):
        state.update(direction=direction, cycles=1, signal_since=now)
    else:
        state.update(direction='WAIT', cycles=0, signal_since=None)
    state['signal_source'] = source
