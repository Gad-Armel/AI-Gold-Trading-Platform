"""Compare gold-only and currency-augmented forecasts on chronological blocks."""
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from services.research.gold_cross_market import aligned_returns


def main():
    root = ROOT/'data/research/gold_sources'
    frames = {name: pd.read_csv(root/f'{name}_M5.csv') for name in ('XAUUSD', 'EURUSD', 'USDJPY')}
    r = aligned_returns(frames)
    features = pd.DataFrame(index=r.index)
    for name in r:
        features[name+'_one'] = r[name]
        features[name+'_three'] = r[name].rolling(3).sum()
        features[name+'_vol'] = r[name].rolling(24).std()
    y = sum(r.XAUUSD.shift(-i) for i in range(1, 4))
    # Require uninterrupted observations for the entire features/label window.
    continuous = r.index.to_series().diff().eq(pd.Timedelta(minutes=5))
    valid = continuous.rolling(25).sum().eq(25)
    for i in range(1, 4):
        valid &= continuous.shift(-i).fillna(False).astype(bool)
    valid &= features.notna().all(axis=1) & y.notna()
    features, y = features[valid], y[valid]
    if len(y) < 3000:
        raise ValueError('Insufficient continuous aligned history')
    split = int(len(y)*.6)
    train_end = features.index[split]-pd.Timedelta(minutes=15)
    train = features.index < train_end
    report = dict(rows=len(y), first=str(features.index[0]), last=str(features.index[-1]),
        split_time=str(features.index[split]), models={}, execution_approved=False,
        note='Forecast diagnostic only; two fixed ridge specifications, no tuning or trading-profit claim',
        source_hashes={name: hashlib.sha256((root/f'{name}_M5.csv').read_bytes()).hexdigest() for name in frames})
    for label, columns in [('gold_only', [c for c in features if c.startswith('XAUUSD')]), ('gold_plus_currencies', list(features))]:
        model = make_pipeline(StandardScaler(), Ridge(alpha=10.))
        model.fit(features.loc[train, columns], y.loc[train])
        prediction = model.predict(features.iloc[split:][columns])
        actual = y.iloc[split:].to_numpy()
        baseline = np.abs(actual).mean()
        blocks = []
        for indices in np.array_split(np.arange(len(actual)), 4):
            blocks.append(dict(rows=len(indices), mae_bps=float(np.abs(actual[indices]-prediction[indices]).mean()*10000),
                               zero_mae_bps=float(np.abs(actual[indices]).mean()*10000)))
        report['models'][label] = dict(mae_bps=float(np.abs(actual-prediction).mean()*10000),
            zero_mae_bps=float(baseline*10000), direction_accuracy=float((np.sign(actual)==np.sign(prediction)).mean()), blocks=blocks)
    (root/'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
