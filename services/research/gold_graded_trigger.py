"""Transparent structural/micro trigger diagnostics, not a fitted ML model."""
import math


def graded_trigger(decision, context, flow, *, bid, ask, lot=.01, minimum_lot=.01):
    base = dict(execution_enabled=False, policy='STRUCTURE_MICRO_GRADED_V1',
                calibrated_probability=None, trained_model=False, acceptance_target=None)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0
               for value in (bid, ask, lot, minimum_lot)) or ask < bid:
        return dict(base, available=False, reason='Invalid quote or volume inputs')
    direction = decision.get('direction')
    sign = 1 if direction == 'BUY' else -1 if direction == 'SELL' else 0
    structure = context.get('structure_research', {}) if context.get('available') else {}
    sweep = structure.get('downside_sweep' if sign > 0 else 'upside_sweep') is True if sign else False
    gap = structure.get('bullish_gap_atr' if sign > 0 else 'bearish_gap_atr', 0.) if sign else 0.
    gap = gap if isinstance(gap, (int, float)) and math.isfinite(gap) else 0.
    zone = sweep or gap > 0
    pressure = flow.get('pressure', 0.) if flow.get('available') else 0.
    pressure = pressure if isinstance(pressure, (int, float)) and math.isfinite(pressure) else 0.
    efficiency = flow.get('efficiency', 0.) if flow.get('available') else 0.
    efficiency = efficiency if isinstance(efficiency, (int, float)) and math.isfinite(efficiency) else 0.
    ignition = bool(sign and sign*pressure >= .4 and efficiency >= .5)
    evidence = decision.get('evidence', 0.)
    evidence = evidence if isinstance(evidence, (int, float)) and math.isfinite(evidence) else 0.
    alignment = decision.get('higher_timeframe_context', {}).get('alignment', 0.)
    alignment = alignment if isinstance(alignment, (int, float)) and math.isfinite(alignment) else 0.
    components = dict(structure=30.*bool(zone), ignition=25.*ignition,
                      fast_candle_quality=25.*max(0., min(1., evidence/100.)),
                      higher_timeframe_alignment=20.*max(0., min(1., alignment)))
    score = sum(components.values())
    tier = 'FULL' if score >= 75 else 'REDUCED' if score >= 55 else 'DEFER' if score >= 40 else 'NO_SETUP'
    if not (zone and ignition):
        tier = 'NO_SETUP'
    multiplier = 1. if tier == 'FULL' else .5 if tier == 'REDUCED' else 0.
    representable = multiplier > 0 and lot*multiplier >= minimum_lot
    return dict(base, available=True, direction=direction, structural_precondition=bool(zone),
                micro_confirmation=ignition, heuristic_score=round(score, 2), components=components,
                suggested_tier=tier, suggested_size_multiplier=multiplier,
                reduced_size_representable=representable if tier == 'REDUCED' else None,
                actual_lot_unchanged=lot, fixed_lot_policy=True,
                unimplemented_sources=['Order-block freshness', 'Exchange aggressor delta', 'Trained meta-label probability'],
                reason='Research only; reduced tiers never round up to a full lot; no pending orders or stop widening')
