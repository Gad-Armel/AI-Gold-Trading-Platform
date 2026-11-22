"""Reproducible chronological candidate training; never promotes to real trading."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from services.research.gold_learned_policy import FEATURES, VERSION, feature_frame


def evaluate(frame, predictions, start, stop, horizon, cost_multiplier=1):
    """One-position forecast-only diagnostic; stop before target on ambiguous bars.

    This is not a replay of consensus/news or dynamic learned exits. Dollar
    returns assume one ounce (.01 lot * 100oz), include spread/slippage, not swap.
    """
    trades = []
    i = start
    while i+horizon < stop:
        spread = max(.28, float(frame.spread.iloc[i+1])*.01)*cost_multiplier
        cost = .10*cost_multiplier
        predicted = predictions[i-start]
        sign = 1 if predicted > 0 else -1
        # The following opening quote is observed at order time.
        op = float(frame.open.iloc[i+1])
        predicted_move = float(frame.close.iloc[i])+predicted-op
        if sign*predicted_move-spread-cost < .25 or spread > .5:
            i += 1
            continue
        entry = op+(spread if sign == 1 else 0)
        stop_price = entry-sign*2.0
        exit_i = i+horizon
        exit_price = float(frame.close.iloc[exit_i])+(spread if sign == -1 else 0)
        for j in range(i+1, i+horizon+1):
            adverse = float(frame.low.iloc[j]) if sign == 1 else float(frame.high.iloc[j])+spread
            if sign*(adverse-stop_price) <= 0:
                opening = float(frame.open.iloc[j])+(spread if sign == -1 else 0)
                exit_price = min(stop_price, opening) if sign == 1 else max(stop_price, opening)
                exit_i = j
                break
        trades.append(sign*(exit_price-entry)-cost)
        i = exit_i+1
    values = np.asarray(trades)
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    equity = np.r_[100., 100.+np.cumsum(values)]
    return dict(trades=len(trades), net_usd=float(values.sum()),
                profit_factor=gains/losses if losses else None,
                max_drawdown_usd=float((np.maximum.accumulate(equity)-equity).max()),
                win_rate=float((values > 0).mean()) if len(values) else 0.,
                minimum_equity_usd=float(equity.min()),
                note='Unconstrained diagnostic; no daily circuit breaker, margin, news or financing simulation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'data/research/xauusd_audit')
    parser.add_argument('--output', type=Path, default=ROOT/'data/research/gold_ai')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(created_at=datetime.now(timezone.utc).isoformat(), live_approved=False,
                  experiment='ONE fixed learner; 60/20/20 chronological split, 3-bar purge; no holdout tuning',
                  limitations=['Historical bars already explored in earlier research: not a new untouched holdout',
                               'Forecast-only diagnostic is not integrated strategy performance',
                               'No point-in-time news training; existing live news veto remains separate',
                               'Future announcements mean published schedules, not knowledge of future results'], frames={})
    for name in ('M5', 'M15', 'H1'):
        source = args.data_dir/f'{name}.csv'
        frame = pd.read_csv(source).sort_values('time').drop_duplicates('time').reset_index(drop=True)
        prices = frame[['open','high','low','close']].to_numpy(float)
        if len(frame) < 3000 or not np.isfinite(prices).all() or (prices <= 0).any():
            raise ValueError(f'Insufficient or invalid prices: {source}')
        if ((frame.high < frame[['open','close','low']].max(axis=1)) |
                (frame.low > frame[['open','close','high']].min(axis=1))).any():
            raise ValueError(f'Inconsistent OHLC: {source}')
        horizon = 3
        x = feature_frame(frame)
        y = frame.close.shift(-horizon)-frame.close
        a, b = int(len(frame)*.60), int(len(frame)*.80)
        usable = np.isfinite(x.to_numpy()).all(axis=1) & np.isfinite(y)
        train = usable & (np.arange(len(frame)) < a-horizon)
        model = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=7,
                 min_samples_leaf=80, l2_regularization=10., learning_rate=.05,
                 early_stopping=False, random_state=42)
        model.fit(x.loc[train], y.loc[train])
        predictions = model.predict(x.iloc[a:])
        validation = evaluate(frame, predictions, a, b, horizon)
        test = evaluate(frame, predictions[b-a:], b, len(frame), horizon)
        stress = evaluate(frame, predictions[b-a:], b, len(frame), horizon, cost_multiplier=1.5)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        model_id = f'gold-forecast-v{VERSION}-{name}-{digest[:12]}'
        artifact = dict(version=VERSION, features=FEATURES, symbol='XAUUSD', frame=name,
                        lot_size=.01, contract_size=100, model=model, model_id=model_id,
                        training_last_bar=int(frame.time.loc[train].iloc[-1]), forecast_bars=horizon,
                        minimum_edge_usd=.25, round_trip_slippage_usd=.10,
                        validation=validation, test=test, live_approved=False)
        joblib.dump(artifact, args.output/f'{name}.joblib')
        report['frames'][name] = dict(model_id=model_id, source_sha256=digest,
            training_rows=int(train.sum()), training_last_bar=artifact['training_last_bar'],
            validation=validation, test=test, cost_stress=stress,
            forecast_mae=float(np.abs(predictions[b-a:-horizon]-y.iloc[b:-horizon]).mean()),
            zero_forecast_mae=float(y.iloc[b:-horizon].abs().mean()))
        print(json.dumps({name: report['frames'][name]}), flush=True)
    (args.output/'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
