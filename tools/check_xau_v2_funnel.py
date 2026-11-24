"""Isolated diagnostics for reviewed user v2 simulator; no MT5 or orders."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.research.gold_simulation_parameters import run_isolated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--days', type=int, default=5)
    args = parser.parse_args()
    if not 3 <= args.days <= 10:
        parser.error('Smoke test requires 3..10 days; not a parameter search')
    sys.path.insert(0, str(args.source.resolve().parent))
    spec = importlib.util.spec_from_file_location('reviewed_xau_sim2', args.source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline = copy.deepcopy(module.X.P)
    parameters = copy.deepcopy(module.V5)
    report = dict(source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        synthetic_only=True, execution_enabled=False, parameters=parameters, results=[],
        limitations=['Supplied OHLC engine: not production policy or real tick fills.',
            'Accepted/queued labels are not fills; unresolved labels are censored, not wins.',
            'Raw denominator is affected by prequalification, merging and deduplication.',
            'Stops can be stretched and fixed TP moved; not permitted in the live main adaptation.',
            'No calibration, IID t-statistic or profitability claim.'])
    for mode in ('regime', 'rw'):
        result = run_isolated(module.X, parameters, {},
            lambda: module.run(module.X.make_data(args.days, 1, mode), copy.deepcopy(parameters)))
        logs = result['log']
        trades = result['trades']
        report['results'].append(dict(mode=mode, seed=1, days=args.days, raw=result['raw'],
            logged_decisions=len(logs), queued_or_accepted=sum(row[0] == 'acc' for row in logs),
            completed_simulated_trades=len(trades), unresolved_labels=sum(row[1] is None for row in logs),
            funnel=result['funnel'], ending_equity=result['eq'],
            realized_only_drawdown=result['mdd'], net_simulated_pnl=float(trades.pnl.sum()),
            mean_realized_r=float(trades.R.mean()) if len(trades) else None))
    assert module.X.P == baseline, 'Simulator globals were not restored'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(report['results'], indent=2))


if __name__ == '__main__':
    main()
