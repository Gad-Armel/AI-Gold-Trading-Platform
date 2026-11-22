"""Entry-only confirmation after a strong signal loses conviction."""
import math
from datetime import datetime, timezone
from config import gold_consensus_settings as settings


def confirm_next_move(decision, state, candles, *, now, frame='M5', required_bars=2):
    seconds = {'M1': 60, 'M5': 300}[frame]
    label = f'{required_bars} completed {frame} candle(s)'
    evidence = float(decision.get('evidence', 0) or 0)
    direction = decision.get('dominant_bias', 'WAIT')
    if not math.isfinite(evidence):
        return ['Invalid signal evidence.']
    previous = state.get('direction')
    peak = float(state.get('peak', 0))
    weakened = (peak >= settings.CANDLE_CONFIRM_STRONG_EVIDENCE
                and (direction != previous or
                     (evidence <= settings.CANDLE_CONFIRM_WEAKENED_EVIDENCE
                      and peak-evidence >= settings.CANDLE_CONFIRM_DROP_POINTS)))
    if weakened and state.get('waiting_since') is None:
        state['waiting_since'] = now
        state['confirmation'] = {'waiting': True, 'completed_bars': 0, 'frame': frame}
    state['direction'] = direction
    state['peak'] = max(peak, evidence) if direction == previous else evidence
    since = state.get('waiting_since')
    if since is None:
        return []
    if candles is None:
        return [f'Waiting for {label}: candle data unavailable.']
    rows = candles.to_dict('records') if hasattr(candles, 'to_dict') else candles
    completed = {}
    try:
        for row in rows:
            raw = row['time']
            if hasattr(raw, 'timestamp'):
                stamp = raw.timestamp()
            elif isinstance(raw, str):
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                stamp = parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
            else:
                stamp = float(raw)
            stamp -= settings.MT5_SERVER_UTC_OFFSET_SECONDS
            opened, closed = float(row['open']), float(row['close'])
            if not all(math.isfinite(value) for value in (stamp, opened, closed)) or min(opened, closed) <= 0:
                return [f'Waiting for {label}: invalid candle data.']
            if stamp >= since and stamp+seconds <= now:
                completed[stamp] = (opened, closed)
    except (ValueError, TypeError, KeyError, OverflowError):
        return [f'Waiting for {label}: invalid candle data.']
    latest = sorted(completed)[-required_bars:]
    confirmed = False
    if len(latest) == required_bars and direction in ('BUY', 'SELL'):
        consecutive = all(abs(b-a-seconds) < .01 for a,b in zip(latest,latest[1:]))
        fresh = now-latest[-1]-seconds < seconds
        bodies = [completed[stamp][1]-completed[stamp][0] for stamp in latest]
        confirmed = (consecutive and fresh and
                     (all(body > 0 for body in bodies) if direction == 'BUY' else all(body < 0 for body in bodies)))
    state['confirmation'] = {'waiting': not bool(confirmed), 'completed_bars': len(latest),
                             'direction': direction, 'frame': frame, 'required_bars': required_bars}
    if confirmed:
        state['waiting_since'] = None
        state['peak'] = evidence
        return []
    return [f'Signal weakened: waiting for {label} agreeing with the next direction.']
