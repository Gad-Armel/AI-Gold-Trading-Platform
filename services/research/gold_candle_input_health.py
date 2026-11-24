"""Main-only expiry of actual candle inputs, independent of report refresh time."""
import math
from services.research.gold_scalp_setups import _bars


def candle_input_health(candles, *, now, offset, grace_seconds=5):
    result = dict(available=False, frames={}, entry_blocks=[])
    if (not all(isinstance(value, (int, float)) and math.isfinite(value)
                for value in (now, offset, grace_seconds)) or grace_seconds < 0):
        return dict(result, entry_blocks=['Invalid candle-health clock configuration'])
    for name, seconds in (('M1', 60), ('M5', 300), ('M15', 900)):
        try:
            raw = candles.get(name)
            raw = raw.tail(4) if hasattr(raw, 'tail') else raw[-4:]
            frame = _bars(raw, seconds, offset, None)
            if ((frame.available-seconds > now+grace_seconds).any()
                    or int((frame.available > now).sum()) > 1):
                raise ValueError('Future or multiple forming candles')
            frame = frame[frame.available <= now]
            if frame.empty:
                raise ValueError('No completed candles')
            latest = float(frame.available.iloc[-1])
            age = now-latest
            fresh = math.isfinite(age) and 0 <= age < seconds+grace_seconds
            result['frames'][name] = dict(available=fresh, last_closed_epoch=latest,
                                         seconds_since_close=age, maximum_seconds=seconds+grace_seconds)
            if not fresh:
                result['entry_blocks'].append(f'{name} completed input is stale; report refresh does not refresh candles.')
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
            result['frames'][name] = dict(available=False)
            result['entry_blocks'].append(f'{name} completed input is missing or invalid.')
    result['available'] = not result['entry_blocks']
    return result


def guard_candle_report(report, health):
    guarded = dict(report)
    guarded['candle_input_health'] = health
    guarded['horizons'] = dict(report.get('horizons', {}))
    if 'SCALP' in guarded['horizons']:
        item = dict(guarded['horizons']['SCALP'])
        item['source_usable'] = bool(item.get('source_usable', True) and health['available'])
        item['blocks'] = list(item.get('blocks', []))+list(health['entry_blocks'])
        guarded['horizons']['SCALP'] = item
    return guarded
