"""Falsification and daily-cluster uncertainty for a frozen research candidate."""
import hashlib
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd

ROOT_PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import gold_consensus_settings as settings
from benchmark_gold_entry_patterns import ROOT, dataset, evaluate
from research_gold_bidirectional import entry_features


def clustered_uncertainty(trades, days, *, draws=5000):
    daily = {day: dict(net=0., gains=0., losses=0., count=0) for day in days}
    for trade in trades:
        day = pd.Timestamp(trade['entry_epoch']-settings.MT5_SERVER_UTC_OFFSET_SECONDS, unit='s', tz='UTC').strftime('%Y-%m-%d')
        row = daily[day]
        p = trade['profit']
        row['net'] += p
        row['gains'] += max(0, p)
        row['losses'] += max(0, -p)
        row['count'] += 1
    values = np.array([[r['net'], r['gains'], r['losses'], r['count']] for r in daily.values()])
    rng = np.random.default_rng(42)
    samples = values[rng.integers(0, len(values), size=(draws, len(values)))].sum(axis=1)
    means = samples[samples[:, 3]>0, 0]/samples[samples[:, 3]>0, 3]
    pf = samples[samples[:, 2]>0, 1]/samples[samples[:, 2]>0, 2]
    return dict(days=len(days), daily=daily,
        daily_cluster_bootstrap_draws=draws,
        mean_profit_95_interval=np.quantile(means, [.025, .975]).round(4).tolist() if len(means) else None,
        profit_factor_95_interval=np.quantile(pf, [.025, .975]).round(4).tolist() if len(pf) else None,
        bootstrap_fraction_net_positive=round(float((samples[:, 0]>0).mean()), 4))


def main():
    manifest = json.loads((ROOT/'bidirectional_5m_observation.json').read_text())
    path = ROOT/'bidirectional_5m_observation.joblib'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['model_sha256']
    frozen = joblib.load(path)
    frame = dataset()
    n = len(frame)
    train_end, valid_end = int(n*.6), int(n*.8)
    assert int(frame.time.iloc[train_end-1])==manifest['trained_through_broker_epoch']
    assert int(frame.time.iloc[valid_end-1])==manifest['validation_through_broker_epoch']
    features = entry_features(frame)[frozen['feature_columns']]
    buy, sell = (frozen['models'][side].predict(features) for side in (1, -1))
    any_signal = (features[['m1_bias', 'm5_bias', 'm15_bias']] != 0).any(axis=1)
    frame['direction'] = np.where(any_signal & (np.abs(buy-sell)>=manifest['minimum_forecast_gap']),
                                  np.where(buy>sell, 1, -1), 0)
    maximum = np.maximum(buy, sell)
    results = []
    for label, start, end in [('VALIDATION', train_end, valid_end), ('LATEST_FROZEN_RESEARCH', valid_end, n)]:
        days = sorted(set(pd.to_datetime(frame.time.iloc[start:end]-settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                                        unit='s', utc=True).dt.strftime('%Y-%m-%d')))
        for stress in (1., 1.5):
            kwargs = dict(predictions=maximum, threshold=manifest['threshold'])
            metrics = evaluate(frame, start, end, 'ANY_DIRECTION', 5, stress, **kwargs)
            trades = evaluate(frame, start, end, 'ANY_DIRECTION', 5, stress, return_trades=True, **kwargs)
            results.append(dict(period=label, cost_stress=stress, **metrics,
                                uncertainty=clustered_uncertainty(trades, days)))
    report = dict(model_sha256=manifest['model_sha256'], results=results, live_approved=False,
        limitations=['Candidate, thresholds and parameters frozen before this assessment; no refitting.',
                     'Latest period is chronological model-out-of-sample, but was inspected with other hypotheses.',
                     'This further falsification test does not erase the original validation sample-size failure.',
                     'Daily cluster bootstrap is an uncertainty diagnostic, not a probability of future profitability.',
                     'Fixed time exits and simulated costs differ from production; fees, financing and news omitted.'])
    (ROOT/'frozen_candidate_assessment.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(results=[{k:v for k,v in r.items() if k!='uncertainty'} | {
        'mean_profit_95_interval':r['uncertainty']['mean_profit_95_interval'],
        'profit_factor_95_interval':r['uncertainty']['profit_factor_95_interval']} for r in results]), indent=2))


if __name__ == '__main__':
    main()
