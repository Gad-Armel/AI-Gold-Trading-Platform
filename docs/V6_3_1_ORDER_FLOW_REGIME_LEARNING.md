# V6.3.2 Order-Flow Regime Learning

This release selectively incorporates useful ideas from two external AI proposals without copying unsafe code.

## Added

- Quote-flow imbalance proxy derived from signed bid/ask quote changes. This is explicitly a proxy because MT5 top-of-book ticks do not expose queue sizes.
- Micro-regimes: IMPULSE, REVERSAL, ROTATION, STALLED and DISLOCATED. They are learning features only and cannot bypass the candidate gate.
- A conservative GradientBoostingClassifier challenger, calibrated and evaluated under the same purged chronological walk-forward process as existing models.
- One-sided Wilson lower bound for selected OOS win rate. The point estimate must still reach 59%, and the confidence-aware lower bound must remain above the configured floor.
- Selected-trade stability across chronological folds, limiting the number of negative folds.
- Out-of-sample permutation importance measured by Brier-score degradation. It is diagnostic only and never mutates thresholds automatically.
- Champion compatibility lock: strategy ID, artifact format and exact feature schema must match the running version.

## Explicitly rejected

- Recursive hyperparameter mutation until a 59% backtest appears.
- Lowering STRICT thresholds without independent evidence.
- Random train/test splits for time-series trades.
- Self-training on LEARNED-lane outcomes.
- Majority-of-checks gates that can ignore hard spread, news, freshness or structural failures.
- P&L formulas that multiply a standard 0.01-lot XAUUSD move by 100.

The release remains shadow-first. No model or approval is included.
