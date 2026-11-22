"""Fresh completed M1 candles confirm entry timing in every lane, never exits."""
import math
from datetime import datetime, timezone
from config import gold_consensus_settings as settings


def scalp_confirmation_blocks(decision, scalp_confirmation):
    """Slow entries cannot bypass the leading scalp's same-direction wait."""
    if (scalp_confirmation.get('waiting_since') is not None
            and decision.get('allowed')
            and (scalp_confirmation.get('direction') not in ('BUY', 'SELL')
                 or decision.get('direction') == scalp_confirmation.get('direction'))):
        lane = decision.get('horizon', 'INTRADAY')
        return [f'Leading SCALP signal weakened: same-direction {lane} entry waits for its two completed M5 candles.']
    return []


def entry_momentum_blocks(decision, candles, *, now, flow=None, required_bars=1, after_epoch=None):
    if not decision.get('allowed'):
        return []
    direction = decision.get('direction')
    if direction not in ('BUY', 'SELL'):
        return ['No directional entry to confirm.']
    if type(required_bars) is not int or required_bars not in range(1, 7):
        return ['Invalid M1 confirmation count; expected 1 to 6 completed candles.']
    if candles is None:
        return ['Fast entry requires fresh completed M1 candles.']
    rows = candles.to_dict('records') if hasattr(candles, 'to_dict') else candles
    completed = {}
    try:
        for row in rows:
            raw = row['time']
            if hasattr(raw, 'timestamp'):
                stamp = raw.timestamp()
            elif isinstance(raw, str):
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                stamp = (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
            else:
                stamp = float(raw)
            stamp -= settings.MT5_SERVER_UTC_OFFSET_SECONDS
            opened, closed = float(row['open']), float(row['close'])
            if not all(math.isfinite(v) for v in (stamp, opened, closed)) or min(opened, closed) <= 0:
                return ['Invalid M1 candle data; entry confirmation unavailable.']
            if stamp+60 <= now:
                completed[stamp] = (opened, closed)
    except (TypeError, ValueError, KeyError, OverflowError):
        return ['Invalid M1 candle data; entry confirmation unavailable.']
    if not completed:
        return ['Fast entry requires a completed M1 candle; forming bars do not confirm.']
    latest = sorted(completed)[-required_bars:]
    if now-latest[-1]-60 >= 60:
        return ['Latest completed M1 candle is stale.']
    if len(latest) < required_bars:
        return [f'Entry requires {required_bars} completed M1 candles.']
    if any(abs(current-previous-60) >= .01 for previous, current in zip(latest, latest[1:])):
        return ['M1 confirmation candles are not consecutive; waiting for uninterrupted data.']
    if after_epoch is not None:
        if not isinstance(after_epoch, (int, float)) or not math.isfinite(after_epoch) or after_epoch <= 0:
            return ['SCALP addition opening time unavailable; waiting for a verifiable new candle.']
        if latest[-1]+60 <= after_epoch:
            return ['SCALP addition requires a newly closed M1 candle after the previous entry.']
    sign = 1 if direction == 'BUY' else -1
    blocks = []
    if any(sign*(completed[stamp][1]-completed[stamp][0]) <= 0 for stamp in latest):
        blocks.append(f'Latest {required_bars} completed M1 candle(s) do not confirm entry direction; waiting for fresh follow-through.')
    flow = flow or {}
    if flow.get('available') and flow.get('bias') in ('BUY', 'SELL') and flow['bias'] != direction:
        blocks.append('Fresh micro-flow opposes entry direction; waiting for alignment.')
    return blocks
