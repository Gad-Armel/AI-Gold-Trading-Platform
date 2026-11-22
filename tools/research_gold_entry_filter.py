"""Offline frozen chronological regression challenger; never approved for live use."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_gold_entry_patterns import ROOT, dataset, evaluate


def main():
    frame = dataset()
    direction = frame.direction
    atr = frame.M1_atr
    features = pd.DataFrame(dict(
        m1_alignment=direction*frame.M1_direction,
        m5_alignment=direction*frame.M5_direction,
        m15_alignment=direction*frame.M15_direction,
        m1_extension=direction*frame.M1_extension,
        m5_extension=direction*frame.M5_extension,
        m15_extension=direction*frame.M15_extension,
        body_atr=direction*frame.body/atr,
        prior_body_atr=direction*frame.prior_body/atr,
        range_atr=(frame.high-frame.low)/atr,
        atr=atr, cost_atr=frame.spread*.01/atr,
        m5_vol_ratio=frame.M5_atr/atr,
        hour_sin=np.sin(frame.time/3600*2*np.pi/24),
        hour_cos=np.cos(frame.time/3600*2*np.pi/24)))
    n = len(frame)
    train_end, valid_end = int(n*.6), int(n*.8)
    results = []
    for minutes in (5, 15):
        # Training labels finish before validation starts; validation positions
        # finish before latest-period evaluation starts.
        labels = evaluate(frame, 100, train_end, 'DIRECTIONAL_BODY', minutes, 1., collect=True)
        indices = [i for i, _ in labels]
        target = [p for _, p in labels]
        model = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=15,
            min_samples_leaf=100, learning_rate=.05, l2_regularization=10,
            early_stopping=False, random_state=42)
        model.fit(features.iloc[indices], target)
        predictions = model.predict(features)
        validation = [dict(threshold=t, **evaluate(frame, train_end, valid_end,
            'DIRECTIONAL_BODY', minutes, 1., predictions=predictions, threshold=t))
            for t in (0., .25, .5, 1.)]
        eligible = [r for r in validation if r['trades'] >= 100
                    and r['net'] > 0 and (r['profit_factor'] or 0) >= 1.1]
        selected = max(eligible, key=lambda r: r['mean']) if eligible else None
        # If validation fails, report failure; do not choose using latest results.
        latest = [dict(cost_stress=stress, **evaluate(frame, valid_end, n,
            'DIRECTIONAL_BODY', minutes, stress, predictions=predictions,
            threshold=selected['threshold'])) for stress in (1., 1.5)] if selected else []
        results.append(dict(minutes=minutes, training_labels=len(labels), validation=validation,
            selected_threshold=selected['threshold'] if selected else None, latest=latest))
    report = dict(results=results, live_approved=False, limitations=[
        'Offline entry challenger; fixed time exits and approximate candle views differ from production.',
        '60/20/20 chronological split with label-boundary purging; no random train/test split.',
        'Four thresholds selected only on middle period, minimum 100 trades and validation PF >=1.1.',
        'Latest historical period was previously inspected with other hypotheses; not a blind holdout.',
        'No historical point-in-time news, fees or financing. Simulated spread/slippage and $5 stops.',
        'Forward validation and faithful production replay remain mandatory before any deployment.'])
    (ROOT/'learned_entry_filter.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
