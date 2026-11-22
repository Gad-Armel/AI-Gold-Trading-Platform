"""Causal sequence diagnostics only; no thresholds or execution authority."""
import math
from services.research.gold_scalp_setups import _bars


def sequence_quality(candles, *, now, direction, bid, ask, atr, required_bars, offset):
    result = dict(available=False, execution_enabled=False, role='SEQUENCE_QUALITY_RESEARCH_V1')
    try:
        if direction not in ('BUY', 'SELL'):
            return dict(result, reason='No directional sequence')
        if (type(required_bars) is not int or not 1 <= required_bars <= 6
                or not all(math.isfinite(value) for value in (now, bid, ask, atr, offset))
                or bid <= 0 or ask < bid or atr <= 0):
            return dict(result, reason='Invalid quote, ATR or sequence configuration')
        raw = candles.tail(64) if hasattr(candles, 'tail') else candles[-64:]
        frame = _bars(raw, 60, offset, now).tail(required_bars)
        if (len(frame) < required_bars or not 0 <= now-float(frame.available.iloc[-1]) < 60
                or any(abs(float(gap)-60) >= .01 for gap in frame.available.diff().dropna())):
            return dict(result, reason='Incomplete or stale completed M1 sequence')
        sign = 1 if direction == 'BUY' else -1
        bodies = frame.close-frame.open
        ranges = frame.high-frame.low
        last = frame.iloc[-1]
        last_range = float(last.high-last.low)
        rejection = float(last.high-last.close if sign == 1 else last.close-last.low)
        movement = sign*float(last.close-frame.open.iloc[0])
        spread = ask-bid
        close_path = [float(frame.open.iloc[0]), *frame.close.astype(float).tolist()]
        path_length = sum(abs(current-previous) for previous, current in zip(close_path, close_path[1:]))
        execution_price = ask if sign == 1 else bid
        sequence_extreme = float(frame.high.max() if sign == 1 else frame.low.min())
        distance_to_extreme = sign*(sequence_extreme-execution_price)
        return dict(result, available=True, required_bars=required_bars,
                    last_closed_at=float(last.available), direction=direction,
                    all_bodies_agree=bool((sign*bodies > 0).all()),
                    body_range_fraction=float(bodies.abs().sum()/ranges.sum()) if ranges.sum() > 0 else 0.,
                    last_rejection_fraction=rejection/last_range if last_range > 0 else 0.,
                    directional_move_atr=movement/atr, spread_atr=spread/atr,
                    close_path_efficiency=abs(movement)/path_length if path_length > 0 else 0.,
                    distance_to_sequence_extreme_atr=distance_to_extreme/atr,
                    remaining_sequence_range_in_spreads=distance_to_extreme/spread if spread > 0 else None,
                    last_body_atr=sign*float(last.close-last.open)/atr,
                    spread_to_sequence_move=spread/movement if movement > 0 else None,
                    entry_extension_atr=sign*((ask if sign == 1 else bid)-float(last.close))/atr,
                    reason='Observed price geometry, not a calibrated profit forecast')
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return dict(result, reason='Invalid sequence candle data')
