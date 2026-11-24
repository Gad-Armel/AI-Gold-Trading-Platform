"""Research BUY and SELL expected returns separately; no broker order capability."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import joblib
import hashlib
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_gold_entry_patterns import ROOT, dataset, evaluate


def entry_features(frame):
    atr = frame.M1_atr
    return pd.DataFrame(dict(
        m1_bias=frame.M1_direction, m5_bias=frame.M5_direction, m15_bias=frame.M15_direction,
        m1_extension=frame.M1_extension, m5_extension=frame.M5_extension,
        m15_extension=frame.M15_extension, body_atr=frame.body/atr,
        prior_body_atr=frame.prior_body/atr, range_atr=(frame.high-frame.low)/atr,
        atr=atr, cost_atr=frame.spread*.01/atr,
        m5_vol_ratio=frame.M5_atr/atr,
        hour_sin=np.sin(frame.time/3600*2*np.pi/24),
        hour_cos=np.cos(frame.time/3600*2*np.pi/24)))


def main():
    frame = dataset()
    features = entry_features(frame)
    any_signal = (features[['m1_bias', 'm5_bias', 'm15_bias']] != 0).any(axis=1)
    n = len(frame)
    train_end, valid_end = int(n*.6), int(n*.8)
    results = []
    for minutes in (5, 15):
        predictions, label_counts, models = {}, {}, {}
        for side in (1, -1):
            candidate = frame.copy()
            candidate['direction'] = np.where(any_signal, side, 0)
            labels = evaluate(candidate, 100, train_end, 'ANY_DIRECTION', minutes, 1., collect=True)
            model = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=15,
                min_samples_leaf=100, learning_rate=.05, l2_regularization=10,
                early_stopping=False, random_state=42)
            model.fit(features.iloc[[i for i, _ in labels]], [p for _, p in labels])
            predictions[side] = model.predict(features)
            models[side] = model
            label_counts[str(side)] = len(labels)
        maximum = np.maximum(predictions[1], predictions[-1])
        gap = np.abs(predictions[1]-predictions[-1])
        candidate = frame.copy()
        candidate['direction'] = np.where(any_signal & (gap>=.25),
            np.where(predictions[1]>predictions[-1], 1, -1), 0)
        validation = []
        for threshold in (0., .25, .5, 1.):
            base = evaluate(candidate, train_end, valid_end, 'ANY_DIRECTION', minutes, 1.,
                predictions=maximum, threshold=threshold)
            stress = evaluate(candidate, train_end, valid_end, 'ANY_DIRECTION', minutes, 1.5,
                predictions=maximum, threshold=threshold)
            validation.append(dict(threshold=threshold, base=base, stress=stress))
        eligible = [r for r in validation if r['base']['trades'] >= 100
                    and (r['base']['profit_factor'] or 0) >= 1.1
                    and r['stress']['trades'] >= 100
                    and (r['stress']['profit_factor'] or 0) >= 1.05]
        selected = max(eligible, key=lambda r: r['base']['mean']) if eligible else None
        latest = [dict(cost_stress=stress, **evaluate(candidate, valid_end, n,
            'ANY_DIRECTION', minutes, stress, predictions=maximum,
            threshold=selected['threshold'])) for stress in (1., 1.5)] if selected else []
        results.append(dict(minutes=minutes, training_labels=label_counts, validation=validation,
            selected_threshold=selected['threshold'] if selected else None, latest=latest))
        if minutes == 5:
            # Freeze this hypothesis for read-only prospective observation. The
            # sample-size validation failure remains in force; export is not approval.
            model_path = ROOT/'bidirectional_5m_observation.joblib'
            joblib.dump(dict(models=models, feature_columns=list(features.columns)), model_path)
            manifest = dict(policy='BIDIRECTIONAL_5M_OBSERVATION_V1', live_approved=False,
                threshold=.5, minimum_forecast_gap=.25, horizon_seconds=300,
                trained_through_broker_epoch=int(frame.time.iloc[train_end-1]),
                validation_through_broker_epoch=int(frame.time.iloc[valid_end-1]),
                validation=[r for r in validation if r['threshold']==.5][0],
                rejection='Validation trade count below the predeclared minimum of 100.',
                model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest())
            (ROOT/'bidirectional_5m_observation.json').write_text(json.dumps(manifest, indent=2))
    report = dict(results=results, live_approved=False, limitations=[
        'Separate BUY/SELL return forecasts; at least one non-neutral completed-candle view required.',
        'Frozen parameters and forecast gap $.25; thresholds chosen only on chronological middle 20%.',
        'Validation gate: >=100 trades, base PF>=1.1 and 1.5x cost PF>=1.05.',
        'Labels purged before next period; fixed 5/15-minute exits differ from production.',
        'Latest period was inspected with prior hypotheses; this is not blind forward validation.',
        'Sampled bid bars and assumed spreads/slippage; fees, financing and news omitted.',
        'No candidate is approved for live execution by this research script.'])
    (ROOT/'bidirectional_entry_filter.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
