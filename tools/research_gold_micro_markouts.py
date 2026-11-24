"""Compare existing fast entry candidates using historical bid/ask markouts."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from services.research.gold_s30_shadow import s30_observation
from services.research.gold_tick_markout import executable_markout, validate_ticks
from services.utils.atomic_json import atomic_write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ticks', help='Headerless semicolon CSV: epoch milliseconds;bid;ask')
    parser.add_argument('--commission-price', type=float, required=True, help='Round-trip price equivalent')
    parser.add_argument('--slippage-price', type=float, required=True, help='Round-trip adverse price equivalent')
    parser.add_argument('--latency-seconds', type=float, default=.25, help='Applied at entry and exit')
    parser.add_argument('--output', default='data/research/gold_micro_markouts.json')
    args = parser.parse_args()
    if any(not math.isfinite(value) or value < 0 for value in (
            args.commission_price, args.slippage_price, args.latency_seconds)):
        parser.error('Costs and latency must be finite and nonnegative')
    frame = pd.read_csv(args.ticks, sep=';', names=['timestamp', 'bid', 'ask'])
    frame['timestamp'] /= 1000.
    frame = validate_ticks(frame)
    first, last = float(frame.timestamp.iloc[0]), float(frame.timestamp.iloc[-1])
    boundary = first+.7*(last-first)
    results = []
    for period in (1, 5, 15, 30):
        candidates = []
        for now in range(math.ceil(first+max(12, 4*period)), math.floor(last), period):
            history = frame.iloc[frame.timestamp.searchsorted(now-max(12, 4*period)):
                                 frame.timestamp.searchsorted(now, side='right')]
            observation = s30_observation(history, now=now, period_seconds=period,
                commission_price=args.commission_price, slippage_price=args.slippage_price)
            fast = observation.get('fast_candidate', {})
            if observation.get('available') and observation.get('direction') in ('BUY', 'SELL'):
                candidates.append((now, observation['direction'], not fast.get('blocks', [])))
        for horizon in (5, 15, 30):
            measured = []
            for now, direction, passed in candidates:
                mark = executable_markout(frame, now, direction, horizon_seconds=horizon,
                    latency_seconds=args.latency_seconds, commission_price=args.commission_price,
                    slippage_price=args.slippage_price)
                if mark is not None:
                    measured.append((now, passed, mark))
            for segment in ('development', 'holdout'):
                for filtered in (False, True):
                    marks = []
                    for now, passed, mark in measured:
                        if filtered and not passed:
                            continue
                        if segment == 'development' and mark['exit_epoch'] >= boundary:
                            continue
                        if segment == 'holdout' and now < boundary:
                            continue
                        marks.append(mark)
                    count = len(marks)
                    results.append(dict(period=period, horizon=horizon, segment=segment,
                        cohort='filtered' if filtered else 'raw_closed_sequence', observations=count,
                        main_mean_net_price=sum(mark['main_net_price'] for mark in marks)/count if count else None,
                        inverse_mean_net_price=sum(mark['inverse_net_price'] for mark in marks)/count if count else None,
                        main_positive_fraction=sum(mark['main_net_price'] > 0 for mark in marks)/count if count else None))
        print(f'S{period}: {len(candidates)} closed-sequence candidates evaluated', file=sys.stderr, flush=True)
    report = dict(role='OFFLINE_MARKOUT_DIAGNOSTICS_NOT_STRATEGY_BACKTEST',
        source=str(Path(args.ticks)), sha256=hashlib.sha256(Path(args.ticks).read_bytes()).hexdigest(),
        first_epoch=first, last_epoch=last, holdout_boundary=boundary, assumptions=vars(args),
        notes=['Observations overlap; no equity curve or independent-trade significance is claimed.',
               'No stop, trailing exit, position cap, margin, fill probability or live strategy replay.',
               'Historical timestamp offset is left unchanged; only relative timing is used.',
               'No model fitting or automatic parameter selection; holdout is diagnostic, not untouched after inspection.'],
        results=results)
    atomic_write_json(args.output, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
