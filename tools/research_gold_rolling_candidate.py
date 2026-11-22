"""Fixed-rule walk-forward challenger for nonstationary entry forecasts.

Every model trains strictly before its prediction block. No threshold tuning
or automatic promotion; repeated historical research is not a blind holdout.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import json
from pathlib import Path
import sys
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_gold_entry_patterns import ROOT, dataset, evaluate
from research_gold_bidirectional import entry_features


def main():
    frame = dataset()
    features = entry_features(frame)
    any_signal = (features[['m1_bias', 'm5_bias', 'm15_bias']] != 0).any(axis=1)
    n = len(frame)
    labels = {}
    for side in (1, -1):
        candidate = frame.copy()
        candidate['direction'] = np.where(any_signal, side, 0)
        labels[side] = dict(evaluate(candidate, 100, n, 'ANY_DIRECTION', 5, 1., collect=True))
    first = 50000
    predictions = {side: np.full(n, np.nan) for side in (1, -1)}
    folds = []
    for start in range(first, n, 5000):
        end = min(n, start+5000)
        counts = {}
        for side in (1, -1):
            # Purge the entire maximum outcome horizon before the block.
            indices = [i for i in labels[side] if start-30000<=i<start-7]
            model = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=15,
                min_samples_leaf=100, learning_rate=.05, l2_regularization=10,
                early_stopping=False, random_state=42)
            model.fit(features.iloc[indices], [labels[side][i] for i in indices])
            predictions[side][start:end] = model.predict(features.iloc[start:end])
            counts[str(side)] = len(indices)
        folds.append(dict(start=start, end=end, training_labels=counts,
                          first_prediction_broker_epoch=int(frame.time.iloc[start])))
    maximum = np.maximum(predictions[1], predictions[-1])
    gap = np.abs(predictions[1]-predictions[-1])
    frame['direction'] = np.where(any_signal & (gap>=.25),
                                  np.where(predictions[1]>predictions[-1], 1, -1), 0)
    results = []
    for period, start, end in [('ALL_WALK_FORWARD', first, n),
            ('EARLIER_WALK_FORWARD', first, int(n*.8)), ('LATEST_WALK_FORWARD', int(n*.8), n)]:
        for stress in (1., 1.5):
            results.append(dict(period=period, cost_stress=stress,
                **evaluate(frame, start, end, 'ANY_DIRECTION', 5, stress,
                           predictions=maximum, threshold=.5)))
    report = dict(results=results, folds=folds, live_approved=False, limitations=[
        'Frozen 30000-bar training window, 5000-bar update schedule, $.50 threshold and $.25 forecast gap.',
        'Models trained only on prior outcomes, with full five-minute label purge before each block.',
        'Historical periods already inspected with other hypotheses; no claim of blind validation.',
        'Fixed time exit, $5 stop and simulated costs; fees, financing, news and production exits omitted.',
        'No model from this experiment is exported or promoted for execution.'])
    (ROOT/'rolling_candidate_assessment.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(results=results, folds=len(folds)), indent=2))


if __name__ == '__main__':
    main()
