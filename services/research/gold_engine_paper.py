"""Identical causal paper fills/exits for every engine, including paused ones."""
from services.research.gold_causal_replay import replay, ReplayConfig
from services.research.gold_engine_score import EngineScore

ABC_REPLAY_CONFIG = ReplayConfig(latency=.35, round_trip_cost=.3, maximum_hold=3600.,
    trailing_arm_r=1.2, trailing_gap_r=.5, trailing_gap_atr=1.5,
    maximum_entry_risk=10., breakeven_arm_r=.8)


def evaluate_engines(ticks, events, *, start, end):
    engines = {}
    for engine in 'ABC':
        result = replay(ticks, events.get(engine, []), start=start, end=end, config=ABC_REPLAY_CONFIG)
        score = EngineScore()
        for index, trade in enumerate(result['trades']):
            score.observe(f'{engine}:{index}', trade['net_price']/trade['initial_risk_price'], now=trade['exited_at'])
        engines[engine] = dict(result, score=score.report(now=end),
            entry_candidates=sum(event['direction'] != 'WAIT' for event in events.get(engine, [])))
    return engines
