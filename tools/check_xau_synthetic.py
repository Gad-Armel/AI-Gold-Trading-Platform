"""Run the reviewed user simulator with isolated parameters; synthetic only."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.research.gold_simulation_parameters import run_isolated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--days', type=int, default=5)
    parser.add_argument('--seeds', type=int, default=2)
    parser.add_argument('--overrides', default='{}', help='Explicit JSON overrides; baseline restored for every run')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 3 <= args.days <= 60 or not 1 <= args.seeds <= 8:
        parser.error('--days must be 3..60 and --seeds 1..8')
    overrides = json.loads(args.overrides)
    if not isinstance(overrides, dict):
        parser.error('--overrides must be a JSON object')
    spec = importlib.util.spec_from_file_location('reviewed_user_xau_sim', args.source)
    simulator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(simulator)
    baseline = copy.deepcopy(simulator.P)
    report = dict(synthetic_only=True, validates_live_profitability=False,
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        baseline=baseline, overrides=overrides, days=args.days, results=[],
        limitations=['The supplied simulator is an OHLC synthetic diagnostic, not real tick execution.',
            'Its stop-gap fills, floating drawdown, virtual/real policy parity and broker constraints remain unvalidated.',
            'Random-walk losses do not prove absence of look-ahead, nor does a positive seed prove alpha.',
            'No pooled IID trade t-statistic is presented as statistical validation.'])
    for mode in ('regime', 'rw'):
        for seed in range(1, args.seeds+1):
            trades, equity, drawdown, stats = run_isolated(simulator, baseline, overrides,
                lambda: simulator.backtest(simulator.make_data(args.days, seed, mode)))
            values = trades.R.to_numpy(dtype=float)
            report['results'].append(dict(mode=mode, seed=seed, trades=len(values),
                mean_r=float(np.mean(values)) if len(values) else None,
                ending_equity=float(equity), realized_only_drawdown=float(drawdown),
                engines={name: dict(active=state.active, score=state.score()) for name, state in stats.items()}))
            print(mode, seed, report['results'][-1], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
