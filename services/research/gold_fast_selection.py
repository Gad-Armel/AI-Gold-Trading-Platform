"""Choose the shortest feasible fast period; no order or profitability authority."""
from services.research.gold_s30_execution import directional_signal, entry_check
import math
from config import gold_consensus_settings as settings


def select_period(ticks, *, now, bid, ask, atr, cost_path, account,
                  allow_provisional=False, held_period=None, include_s1=False, risk_evaluator=None,
                  required_direction=None):
    if required_direction not in (None, 'BUY', 'SELL'):
        raise ValueError('Required direction must be BUY or SELL')
    supported = (1, 5, 15, 30) if include_s1 else (5, 15, 30)
    periods = (held_period,) if held_period in supported else supported
    observations = []
    for period in periods:
        signal = directional_signal(ticks, now=now, bid=bid, ask=ask, atr=atr,
                                    period_seconds=period, bar_count=settings.FAST_CONFIRMATION_BARS)
        blocks, _ = entry_check(dict(direction=signal['bias']), ticks, now=now,
            plan=dict(required_bars=settings.FAST_CONFIRMATION_BARS, after_epoch=None), cost_path=cost_path,
            period_seconds=period, allow_provisional=allow_provisional, account=account)
        blocks = list(blocks)
        if required_direction is not None and signal['bias'] != required_direction:
            blocks.append('Candidate does not match requested reversal direction')
        if not signal['source_usable'] or signal['bias'] not in ('BUY', 'SELL') or signal['evidence'] < 15:
            blocks.append('No usable closed-candle direction above 15/100')
        if not blocks and risk_evaluator is not None:
            try:
                risk_blocks = risk_evaluator(signal)
                blocks.extend(risk_blocks)
            except Exception as error:
                blocks.append(f'Candidate stop risk unavailable: {error}')
        observations.append(dict(timeframe=f'S{period}', direction=signal['bias'], eligible=not blocks,
                                 blocks=blocks))
        if not blocks:
            return period, dict(policy='FASTEST_FEASIBLE', selected=f'S{period}',
                                 pinned=held_period is not None, candidates=observations)
    fallback = held_period if held_period in supported else 30
    return fallback, dict(policy='FASTEST_FEASIBLE', selected=f'S{fallback}',
                         pinned=held_period is not None, candidates=observations,
                         reason='No candidate passed; fallback is for observation only, entry gates still apply')


def candidate_risk_blocks(mt5, signal, *, bid, ask):
    from config import gold_consensus_settings as settings
    from services.execution.gold_consensus_demo_broker import _s30_grid_stop, _planned_risk_block
    direction = signal['bias']
    info = mt5.symbol_info(settings.SYMBOL)
    if info is None:
        return ['Broker metadata unavailable for candidate stop risk']
    stop = _s30_grid_stop(info, direction, float(signal['levels']['sl']))
    price = ask if direction == 'BUY' else bid
    if not math.isfinite(price) or price <= 0:
        return ['Invalid candidate executable quote']
    block = _planned_risk_block(mt5, direction, .01, price, stop)
    return [block['message']] if block else []
