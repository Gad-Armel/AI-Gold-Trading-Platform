"""Closed-M1 breakout/retest candidate diagnostics without order authority."""
import math

from services.research.gold_scalp_setups import _bars


def retest_observation(candles, *, now, direction, atr, offset, lookback=20,
                       expiry_bars=3, tolerance_atr=.1):
    result = dict(available=False, execution_enabled=False, role='M1_RETEST_SHADOW_V1')
    try:
        if (direction not in ('BUY', 'SELL') or type(lookback) is not int
                or type(expiry_bars) is not int or not 14 <= lookback <= 40
                or not 1 <= expiry_bars <= 10
                or not all(math.isfinite(value) for value in (now, atr, offset, tolerance_atr))
                or atr <= 0 or not 0 <= tolerance_atr <= .5):
            return dict(result, reason='Invalid retest research inputs')
        raw = candles.tail(64) if hasattr(candles, 'tail') else candles[-64:]
        frame = _bars(raw, 60, offset, now)
        if (len(frame) < lookback+2
                or not 0 <= now-float(frame.available.iloc[-1]) < 60
                or any(abs(float(gap)-60) >= .01 for gap in frame.available.diff().dropna())):
            return dict(result, reason='Insufficient, discontinuous or stale completed M1 data')
        sign = 1 if direction == 'BUY' else -1
        latest = len(frame)-1
        candidate = None
        for index in range(max(lookback, latest-expiry_bars-1), latest):
            previous = frame.iloc[index-lookback:index]
            level = float(previous.high.max() if sign == 1 else previous.low.min())
            bar = frame.iloc[index]
            if sign*(float(bar.close)-level) > 0 and sign*(float(bar.open)-level) <= 0:
                candidate = (index, level)
        if candidate is None:
            return dict(result, available=True, state='NO_CANDIDATE', direction=direction)
        index, level = candidate
        age = latest-index
        history = frame.iloc[max(0, index-15):index]
        true_ranges = [max(float(current.high-current.low),
                           abs(float(current.high-previous.close)),
                           abs(float(current.low-previous.close)))
                       for previous, current in zip(history.itertuples(), history.iloc[1:].itertuples())]
        breakout_atr = sum(true_ranges[-14:])/len(true_ranges[-14:])
        metadata = dict(available=True, direction=direction, level=level,
                        breakout_closed_at=float(frame.available.iloc[index]),
                        observed_at=float(frame.available.iloc[-1]), age_bars=age,
                        lookback=lookback, expiry_bars=expiry_bars, tolerance_atr=tolerance_atr,
                        breakout_atr=breakout_atr)
        for position in range(index+1, latest+1):
            if position-index > expiry_bars:
                return dict(result, **metadata, state='EXPIRED')
            bar = frame.iloc[position]
            if sign*(float(bar.close)-level) <= 0:
                return dict(result, **metadata, state='INVALIDATED')
            touched = (float(bar.low) <= level+tolerance_atr*breakout_atr if sign == 1
                       else float(bar.high) >= level-tolerance_atr*breakout_atr)
            if touched and sign*float(bar.close-bar.open) > 0:
                return dict(result, **metadata,
                            state='CONFIRMED_NOW' if position == latest else 'ALREADY_CONFIRMED',
                            confirmation_closed_at=float(bar.available))
        return dict(result, **metadata, state='WAIT_RETEST')
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return dict(result, reason='Invalid retest candle data')
