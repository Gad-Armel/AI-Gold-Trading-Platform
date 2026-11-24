"""Reconcile scalp churn from completed net fills, including broker stop exits."""
import math
from datetime import datetime
from config import gold_consensus_settings as settings


def epoch(value):
    if isinstance(value, (int, float)):
        return float(value)
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()


def reconcile(state, history, positions, *, now):
    """Idempotent on repeated history. History errors must be passed as None."""
    if history is None:
        state['history_available'] = False
        return
    records = []
    try:
        for trade in history:
            opened = epoch(trade.get('opened_at', trade.get('opened_epoch')))
            closed = epoch(trade.get('closed_at', trade.get('closed_epoch')))
            profit = float(trade['profit'])
            if not all(math.isfinite(x) for x in (opened, closed, profit)) or not 0 <= opened <= closed <= now:
                raise ValueError('Invalid fill history')
            records.append((closed, opened, str(trade.get('position_id', trade.get('ticket'))), profit, trade['direction']))
    except (ValueError, TypeError, KeyError, OverflowError):
        state['history_available'] = False
        return
    state['history_available'] = True
    records.sort()
    events = state.setdefault('entry_events', {})
    for position in positions:
        opened = position.get('opened_epoch')
        if isinstance(opened, (int,float)) and math.isfinite(opened) and 0 < opened <= now:
            events[str(position['ticket'])] = opened
    for closed, opened, ticket, profit, direction in records:
        events[ticket] = opened
    state['entry_events'] = {k:v for k,v in events.items() if 0 <= now-v <= 3600}
    state['entry_times'] = list(state['entry_events'].values())
    pending = set(state.get('pending_closed', []))
    pending -= {r[2] for r in records}
    state['pending_closed'] = sorted(pending)
    losses = 0
    for record in reversed(records):
        if record[3] > 0:
            break
        if record[3] < 0:
            losses += 1
    state['consecutive_losses'] = losses
    losing = [r for r in records if r[3] < 0]
    state['last_loss_at'] = losing[-1][0] if losing else -float('inf')
    if records and records[-1][0] >= state.get('last_exit_at', -float('inf')):
        state['last_exit_at'], state['last_exit_direction'] = records[-1][0], records[-1][4]
        state['reentry_until'] = records[-1][0] + 30.0


def reentry_blocks(state, *, now, direction):
    blocks = []
    if not state.get('history_available', False) or state.get('pending_closed'):
        blocks.append('SCALP waiting for reconciled execution history.')
    elapsed = now-state.get('last_exit_at', -float('inf'))
    cooldown = float(settings.SCALP_REENTRY_COOLDOWN_SECONDS)
    reentry_until = float(state.get('reentry_until', -float('inf')))
    if elapsed < cooldown or now < reentry_until:
        blocks.append(f'SCALP re-entry cooldown: {cooldown-elapsed:.0f}s remaining.')
    if (not settings.SCALP_ALLOW_DIRECTION_FLIP and state.get('last_exit_direction') in ('BUY','SELL')
            and direction in ('BUY','SELL') and direction != state['last_exit_direction'] and elapsed < cooldown*3):
        blocks.append('SCALP direction flip is disabled.')
    return blocks
