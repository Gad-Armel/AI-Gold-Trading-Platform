"""Predeclared chronological comparison; never connects to MT5 or sends orders."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from services.research.gold_regime_scalper import feature_table, RegimeConfig
from services.research.gold_causal_replay import replay, ReplayConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=Path('data/research/strategy_20261021/capture'))
    parser.add_argument('--output', type=Path, default=Path('data/research/strategy_20261021/replay.json'))
    args = parser.parse_args()
    ticks = pd.read_parquet(args.capture/'ticks.parquet')
    metadata = json.loads((args.capture/'metadata.json').read_text())
    features = feature_table(ticks, pd.read_parquet(args.capture/'M1.parquet'),
        pd.read_parquet(args.capture/'M5.parquet'), offset=metadata['broker_offset_seconds'])
    start, end = float(ticks.timestamp.min()), float(ticks.timestamp.max())
    split = start+.6*(end-start)
    candidates = features[features.feature_epoch <= end].to_dict('records')
    report = dict(read_only=True, strategy_config=asdict(RegimeConfig()), split_epoch=split,
                  selection_rule='No parameter search: two fixed families, 60/40 chronological split.', results=[])
    for latency, cost in ((.35, .3), (.15, 0.), (.5, .3), (.35, .08), (2., .3)):
        for name, lower, upper in (('DEVELOPMENT', start, split), ('HOLDOUT', split, end)):
            for family in ('TICK_2_TO_5', 'REGIME_PULLBACK_V1'):
                config = ReplayConfig(latency=latency, round_trip_cost=cost,
                    maximum_hold=30. if family == 'TICK_2_TO_5' else 180.,
                    cooldown=0. if family == 'TICK_2_TO_5' else 5.)
                result = replay(ticks, candidates, start=lower, end=upper, config=config,
                                tick_sequence=family == 'TICK_2_TO_5')
                report['results'].append(dict(family=family, segment=name, config=asdict(config), **result))
                print(name, family, latency, cost, result['summary'], flush=True)
    report['limitations'] = ['Single broker, approximately one day, not representative of all market regimes.',
        'Normalized unit-position experiment, not a funded account: no margin, bankruptcy or balance stopping model.',
        'One concurrent 0.01 lot position; four simultaneous positions are not independently validated.',
        'News, broker rejections, rate limits and production exit policy are not replayed.',
        'Costs measured later are sensitivity only, not a historical out-of-sample estimate.',
        'Broker stops fill at the first observed executable quote; no invented stop-price fills.',
        'Dataset-end open positions are censored and excluded from closed-trade P/L.',
        'A holdout is not reusable for choosing thresholds or claiming sustained profitability.']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
