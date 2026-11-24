"""Offline executable-price signal diagnostics, not a strategy backtest."""
import math
from bisect import bisect_left


def executable_markout(ticks, decision_epoch, direction, *, horizon_seconds,
                       latency_seconds, commission_price, slippage_price,
                       maximum_gap_seconds=2.):
    values = (decision_epoch, horizon_seconds, latency_seconds, commission_price,
              slippage_price, maximum_gap_seconds)
    if (not all(math.isfinite(value) for value in values) or horizon_seconds <= 0
            or min(latency_seconds, commission_price, slippage_price) < 0
            or maximum_gap_seconds <= 0 or direction not in ('BUY', 'SELL')):
        raise ValueError('Explicit finite timing/cost assumptions and direction required')
    stamps = ticks['timestamp'].to_numpy()
    if len(stamps) == 0:
        return None
    entry_target = decision_epoch+latency_seconds
    entry_index = bisect_left(stamps, entry_target)
    if entry_index >= len(stamps) or stamps[entry_index]-entry_target > maximum_gap_seconds:
        return None
    exit_target = stamps[entry_index]+horizon_seconds+latency_seconds
    exit_index = bisect_left(stamps, exit_target)
    if exit_index >= len(stamps) or stamps[exit_index]-exit_target > maximum_gap_seconds:
        return None
    observed = ticks.iloc[entry_index:exit_index+1]
    if (observed.timestamp.diff().dropna() > maximum_gap_seconds).any():
        return None
    entry, exit_quote = ticks.iloc[entry_index], ticks.iloc[exit_index]
    if direction == 'BUY':
        gross = exit_quote.bid-entry.ask
        inverse_gross = entry.bid-exit_quote.ask
    else:
        gross = entry.bid-exit_quote.ask
        inverse_gross = exit_quote.bid-entry.ask
    costs = commission_price+slippage_price
    return dict(entry_epoch=float(entry.timestamp), exit_epoch=float(exit_quote.timestamp),
                main_net_price=float(gross-costs), inverse_net_price=float(inverse_gross-costs))


def validate_ticks(frame):
    frame = frame[['timestamp', 'bid', 'ask']].astype(float)
    if frame.empty or not all(math.isfinite(value) for value in frame.to_numpy().flat):
        raise ValueError('Finite, nonempty tick input required')
    if (frame.bid <= 0).any() or (frame.ask < frame.bid).any():
        raise ValueError('Invalid executable prices')
    if (frame.timestamp.diff().dropna() < 0).any():
        raise ValueError('Out-of-order tick input; repair provenance before replay')
    return frame.drop_duplicates(['timestamp', 'bid', 'ask']).reset_index(drop=True)
