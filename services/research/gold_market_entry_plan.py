"""Causal executable-price risk plan; observed range is not expected return."""
import math
from datetime import datetime, timezone


def _finite(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _bar_epoch(value):
    if _finite(value):
        return float(value)
    if not isinstance(value, str):
        raise ValueError('Completed M1 bar identity unavailable')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Completed M1 bar identity must be timezone-aware')
    return stamp.timestamp()


def market_entry_plan(ticks, context, *, now, direction, commission, slippage,
                      maximum_risk=5.):
    """Plan an entry in an externally supplied direction without inventing alpha.

    ``context.bar_id`` is the UTC *opening* timestamp of the most recently
    completed M1 candle, as emitted by market_exit_context. ATR and regime are
    context only. Stop risk is price distance, equivalent to USD for the main's
    fixed .01 lot on a 100oz USD XAUUSD contract; broker risk checks still decide.
    """
    result = dict(available=False, allowed=False, policy='MARKET_AWARE_RISK_V1',
                  direction=direction, setup_id=None, levels={}, blocks=[],
                  calibrated_probability=None, expected_return=None)
    if direction not in ('BUY', 'SELL'):
        return dict(result, blocks=['A directional source context is required.'])
    if not isinstance(context, dict) or not context.get('available'):
        return dict(result, blocks=['Completed market context is unavailable.'])
    atr = context.get('atr')
    if (not all(_finite(v) for v in (now, commission, slippage, maximum_risk, atr))
            or min(commission, slippage) < 0 or min(atr, maximum_risk) <= 0):
        return dict(result, blocks=['Explicit finite volatility, cost and risk inputs required.'])
    try:
        bar_epoch = _bar_epoch(context.get('bar_id'))
        if bar_epoch % 60 != 0 or bar_epoch + 60 > now or now-(bar_epoch+60) > 65:
            raise ValueError('Completed M1 context is future-dated, stale or unaligned')
    except (ValueError, TypeError, OverflowError) as error:
        return dict(result, blocks=[str(error)])

    rows = []
    try:
        if ticks is None:
            raise ValueError('Missing tick history')
        if hasattr(ticks, 'to_dict'):
            ticks = ticks[(ticks['timestamp'] >= now-60) & (ticks['timestamp'] <= now)].to_dict('records')
        for tick in ticks:
            if isinstance(tick['timestamp'], bool):
                raise ValueError('Invalid tick time')
            stamp = float(tick['timestamp'])
            if not math.isfinite(stamp):
                raise ValueError('Invalid tick time')
            if not now-60 <= stamp <= now:
                continue  # No future data, interpolation or synthetic observations.
            if any(isinstance(tick[key], bool) for key in ('bid', 'ask')):
                raise ValueError('Invalid executable quote')
            bid, ask = float(tick['bid']), float(tick['ask'])
            if not all(math.isfinite(v) for v in (bid, ask)) or bid <= 0 or ask < bid:
                raise ValueError('Malformed executable quote')
            rows.append((stamp, bid, ask))
    except (KeyError, TypeError, ValueError, OverflowError):
        return dict(result, blocks=['Malformed or missing executable tick history.'])
    rows = list(dict.fromkeys(rows))
    rows.sort(key=lambda row: row[0])
    if not rows or now-rows[-1][0] > 2:
        return dict(result, blocks=['Fresh executable quote required.'])
    if rows[-1][0]-rows[0][0] < 30:
        return dict(result, blocks=['At least thirty seconds of observed tick history required.'])
    structure = [row for row in rows if row[0] >= now-30]
    boundaries = [now-30]+[row[0] for row in structure]+[now]
    if len(structure) < 2 or max(b-a for a,b in zip(boundaries, boundaries[1:])) > 3:
        return dict(result, blocks=['Quote gap exceeds three seconds in recent structure.'])

    bid, ask = rows[-1][1:]
    spread = ask-bid
    cost = spread+commission+slippage
    sign = 1 if direction == 'BUY' else -1
    recent = [row for row in rows if row[0] >= now-3]
    short_coverage = bool(len(recent) >= 2 and recent[-1][0]-recent[0][0] >= 1.5)
    bid_move = sign*(recent[-1][1]-recent[0][1]) if short_coverage else None
    ask_move = sign*(recent[-1][2]-recent[0][2]) if short_coverage else None
    net = (bid_move+ask_move)/2 if short_coverage else None
    directly_opposed = bool(short_coverage and bid_move < 0 and ask_move < 0 and net < -.25*spread)

    mids = [(row[1]+row[2])/2 for row in rows]
    observed_range = max(mids)-min(mids)
    buffer = max(.5*spread, .1*atr)
    pivot = min(row[1] for row in structure) if sign == 1 else max(row[2] for row in structure)
    stop = pivot-sign*buffer
    reference = ask if sign == 1 else bid
    risk = sign*(reference-stop)
    executable_stop_room = sign*((bid if sign == 1 else ask)-stop)
    blocks = []
    if directly_opposed:
        blocks.append('Both executable sides are moving directly against the proposed entry.')
    if observed_range <= 1.25*cost:
        blocks.append('Observed sixty-second range does not clear 1.25 times estimated dealing costs.')
    if risk <= 0 or risk > maximum_risk:
        blocks.append('Structural stop is invalid or exceeds the maximum trade-risk budget.')
    if risk < 2*cost:
        blocks.append('Structural stop leaves insufficient room relative to estimated dealing costs.')
    levels = dict(sl=stop, entry_reference=reference, entry_zone=[bid, ask],
                  source='EXECUTABLE_30S_SWING',
                  tp1=reference+sign*2*risk, tp2=reference+sign*3*risk,
                  tp3=reference+sign*4*risk)
    bar_id = datetime.fromtimestamp(bar_epoch, timezone.utc).isoformat()
    structure_context = context.get('structure_research', {})
    classification = structure_context.get('regime') if isinstance(structure_context, dict) else None
    return dict(result, available=True, allowed=not blocks, blocks=blocks, levels=levels,
        setup_id=f'M1_CONTEXT:{bar_id}:{direction}', context_bar_id=bar_id,
        observed_epoch=now, direction=direction, bid=bid, ask=ask, spread_price=spread,
        observed_span_seconds=rows[-1][0]-rows[0][0], observed_quote_count=len(rows),
        commission_price=commission, slippage_price=slippage, estimated_cost_price=cost,
        initial_risk_price=risk, executable_stop_room_price=executable_stop_room,
        risk_to_cost=risk/cost if cost > 0 else None,
        observed_range_price=observed_range, range_to_cost=observed_range/cost if cost > 0 else None,
        observed_range_role='Backward-looking movement proxy; not an expected return or profit forecast',
        analysis_target_role='Synthetic R-multiple references for broker validation; broker TP remains dynamic',
        stop_buffer_price=buffer, structural_pivot_price=pivot,
        short_quote_coverage=short_coverage, signed_bid_move_price=bid_move,
        signed_ask_move_price=ask_move, signed_mid_move_price=net,
        direct_opposition=directly_opposed,
        regime=dict(trend=context.get('trend'), momentum=context.get('momentum'),
                    classification=classification,
                    role='Observed context only; no inferred profitability'))
