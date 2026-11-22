"""Fixed ORBIT proposal replay; comparison only, never broker orders or promotion."""
import json
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.research.gold_orbit_research import orbit_features, orbit_candidate
from services.research.gold_causal_replay import replay, ReplayConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=ROOT/'data/research/strategy_20261021/ny_capture')
    parser.add_argument('--output', type=Path, default=ROOT/'data/research/strategy_20261021/orbit_replay.json')
    args = parser.parse_args()
    folder = args.capture
    ticks = pd.read_parquet(folder/'ticks.parquet').sort_values('timestamp', kind='stable')
    metadata = json.loads((folder/'metadata.json').read_text())
    features = orbit_features(pd.read_parquet(folder/'M1.parquet'),
        pd.read_parquet(folder/'M15_extended.parquet'), offset=metadata['broker_offset_seconds'])
    stamps = ticks.timestamp.to_numpy()
    candidates, rejects = [], {}
    for row in features.to_dict('records'):
        index = int(np.searchsorted(stamps, row['feature_epoch'], side='left'))
        if index >= len(ticks) or row['feature_epoch'] < stamps[0]:
            continue
        quote = ticks.iloc[index]
        signal = orbit_candidate(row, now=float(quote.timestamp), bid=float(quote.bid), ask=float(quote.ask))
        candidate = dict(feature_epoch=float(quote.timestamp), valid_until_epoch=row['feature_epoch']+60,
            direction=signal['bias'], stop=signal['levels'].get('sl', 0.), setup=row['setup'],
            trend_sign=int(row['trend_sign']) if pd.notna(row['trend_sign']) else 0)
        candidates.append(candidate)
        if signal['blocks']:
            reason = signal['blocks'][0]
            rejects[reason] = rejects.get(reason, 0)+1
    start, end = float(stamps[0]), float(stamps[-1])
    split = start+.6*(end-start)
    report = dict(read_only=True, execution_enabled=False, strategy='ORBIT_M1_M15_RESEARCH_V1',
        proposal_parameters_frozen=True, split_epoch=split, rejection_counts=rejects, results=[])
    for cost in (.3, .08):
        for name, lower, upper in (('DEVELOPMENT', start, split), ('CHRONOLOGICAL_TAIL', split, end)):
            config = ReplayConfig(latency=.35, round_trip_cost=cost, maximum_hold=900.,
                trailing_arm_r=1.2, trailing_gap_r=.5, maximum_entry_risk=10., breakeven_arm_r=.8)
            result = replay(ticks, candidates, start=lower, end=upper, config=config)
            report['results'].append(dict(segment=name, round_trip_cost=cost, **result))
            print(name, cost, result['summary'], flush=True)
    report['limitations'] = ['One broker and one day; proposed strategy is not proven profitable.',
        'Historical tail follows earlier research on overlapping data; not a new independent blind test.',
        'No account margin, bankruptcy, news exclusion, pending limit queue or partial-close model.',
        'Trend, breakout and range modes are fixed hypotheses; no parameter selection on these outcomes.',
        'Paper-only: fixed .01 lot equivalent, one position; maximum structural risk 10 price units.',
        'Stop gaps and delayed exits can lose more than planned; no fixed TP is installed.']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
