"""Read-only real-quote A/B/C comparison; independent paper outcomes per engine."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.research.gold_multiengine_research import multi_features, multi_candidates
from services.research.gold_engine_paper import evaluate_engines, ABC_REPLAY_CONFIG


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=ROOT/'data/research/strategy_20261021/corrected_capture')
    parser.add_argument('--output', type=Path, default=ROOT/'data/research/external_regime_20261021/abc_replay.json')
    args = parser.parse_args()
    metadata = json.loads((args.capture/'metadata.json').read_text())
    ticks = pd.read_parquet(args.capture/'ticks.parquet').sort_values('timestamp', kind='stable')
    one = pd.read_parquet(args.capture/'M1.parquet')
    features = multi_features(pd.read_parquet(args.capture/'M5.parquet'),
        pd.read_parquet(args.capture/'M15.parquet'), offset=metadata['broker_offset_seconds'])
    stamps = ticks.timestamp.to_numpy()
    events = {engine: [] for engine in 'ABC'}
    for row in features.to_dict('records'):
        index = int(np.searchsorted(stamps, row['feature_epoch'], side='left'))
        if row['feature_epoch'] < stamps[0] or index >= len(stamps):
            continue
        quote = ticks.iloc[index]
        report = multi_candidates(row, one, now=float(quote.timestamp), bid=float(quote.bid),
                                  ask=float(quote.ask), offset=metadata['broker_offset_seconds'])
        for engine in 'ABC':
            candidate = next((item for item in report['candidates'] if item['engine'] == engine), None)
            event = dict(feature_epoch=float(quote.timestamp), valid_until_epoch=row['feature_epoch']+30,
                direction='WAIT', stop=0., setup=f'ABC_{engine}', atr=float(row['atr']),
                trend_sign=int(row['trend_sign']))
            if candidate:
                event.update(candidate, feature_epoch=float(quote.timestamp))
            events[engine].append(event)
    start, end = float(stamps[0]), float(stamps[-1])
    output = dict(as_of=pd.Timestamp.now(tz='UTC').isoformat(), read_only=True, execution_enabled=False,
        strategy='ABC_REGIME_RESEARCH_V1', evaluation='OFFLINE_REPLAY_NOT_LIVE', config=asdict(ABC_REPLAY_CONFIG),
        source_sha256=hashlib.sha256((ROOT/'services/research/gold_multiengine_research.py').read_bytes()).hexdigest(),
        engines={}, limitations=['One broker, short overlapping historical sample; no profitability established.',
            'Each engine has its own paper path; outcomes are correlated, not a margin-aware combined portfolio.',
            'No broker orders, no automatic unpause, no trained probability and no selection on this reused sample.',
            'Sessions only define opening ranges; news and complete broker-session trading restrictions are not replayed.',
            'Cost/room ratio is diagnostic only, not a restored main entry veto.',
            'Opening ranges are consumed only after modeled fills, never merely by detecting a signal.'])
    output['engines'] = evaluate_engines(ticks, events, start=start, end=end)
    for engine, result in output['engines'].items():
        print(engine, result['summary'], result['score'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
