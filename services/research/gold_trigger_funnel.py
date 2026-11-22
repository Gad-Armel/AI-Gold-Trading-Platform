"""Unique-setup execution telemetry, never order authority."""
from collections import Counter


def observe_funnel(state, decision, *, timing_blocks, attempted=False, result=None, limit=200):
    state['evaluation_cycles'] = state.get('evaluation_cycles', 0) + 1
    observation = decision.get('s30_entry', {})
    candidate = observation.get('fast_candidate', {})
    setup_id = candidate.get('setup_id')
    rows = state.setdefault('setups', {})
    valid = (observation.get('available') and decision.get('direction') in ('BUY', 'SELL')
             and candidate.get('direction') == decision.get('direction') and setup_id)
    if valid:
        row = rows.setdefault(setup_id, dict(stage='CANDIDATE', attempts=0, reasons=[]))
        if row['stage'] not in ('REPORTED_DONE', 'UNCONFIRMED_EXECUTION'):
            row['reasons'] = list(dict.fromkeys(decision.get('blocks', []) + list(timing_blocks)))
            row['stage'] = 'LOCAL_BLOCKED' if row['reasons'] or not decision.get('allowed') else 'ELIGIBLE'
        if attempted:
            row['attempts'] += 1
            metrics = (result or {}).get('execution_metrics', {})
            row['stage'] = ('REPORTED_DONE' if (result or {}).get('success') and
                            metrics.get('state') == 'REPORTED_DONE' else 'UNCONFIRMED_EXECUTION'
                            if (result or {}).get('success') else 'EXECUTION_FAILED')
        while len(rows) > limit:
            del rows[next(iter(rows))]
    counts = Counter(row['stage'] for row in rows.values())
    attempts = sum(row['attempts'] for row in rows.values())
    return dict(window_unique_setups=len(rows), evaluation_cycles=state['evaluation_cycles'],
                denominator='Unique directional fast setups with available completed bars; rolling window, per process',
                stages=dict(counts), request_attempts=attempts,
                reported_done_setups=counts['REPORTED_DONE'],
                reported_execution_rate=counts['REPORTED_DONE']/len(rows) if rows else None,
                confirmed_fill_rate=None, acceptance_target=None,
                execution_enabled=False,
                reason='Reported DONE is not deal reconciliation; local blocks are not broker rejections')
