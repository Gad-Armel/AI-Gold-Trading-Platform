# V6.3.0 — Calibrated Self-Learning

## Objective

V6.3 treats a 59% win rate as an out-of-sample validation target, never as a guarantee. The model is allowed to abstain. It cannot weaken hard news, spread, quote-freshness, account, position-limit or structural-safety controls.

## Fourth shadow lane: LEARNED

`LEARNED` starts from an EXPLORATORY candidate and then applies a calibrated probability model. It is research-only and is explicitly ineligible for broker execution. A future controlled-demo order must still originate from the exact STRICT gate and must also pass an approved calibrated model.

## Training labels

Only closed STRICT, BALANCED and EXPLORATORY shadow trades are eligible for training. LEARNED outcomes are excluded to prevent a self-reinforcing feedback loop. Cross-lane simulations from the same 15-second/$0.25 market episode are de-correlated, retaining the strictest available observation.

## Models

The challenger process compares:

- regularized logistic regression;
- class-balanced logistic regression;
- random forest.

Every model is calibrated on a trailing chronological calibration block. Probabilities are assessed using Brier score and expected calibration error.

## Purged walk-forward validation

Training always precedes testing in time. A training trade whose outcome overlaps the first opening time in the test fold is purged. Promotion requires at least four valid chronological folds.

A threshold between 0.55 and 0.90 is selected only when the executed subset meets all of the following out of sample:

- win rate at least 59%;
- expectancy at least +$0.03 per selected trade;
- profit factor at least 1.15;
- minimum coverage and trade-count requirements;
- acceptable Brier score and calibration error.

Regime-specific thresholds are permitted only after enough independent out-of-sample observations exist.

## Champion/challenger controls

A challenger is saved for review. It replaces the champion only if it is approved and ranks above the current champion. The champion expires after seven days, is invalidated by settings changes and is blocked when multivariate population-stability drift exceeds the configured limit.

## Adaptive payoff geometry

V6.3 builds target and stop distances from actual spread and M1 ATR. The default ranges are:

- target: $0.90–$1.20;
- hard stop: $1.00–$1.20;
- minimum target/stop ratio: 0.80.

This makes a 59% hit rate compatible with positive gross expectancy before slippage, unlike a permanently asymmetric $0.85/$1.25 geometry. Two profit-lock stages reduce giveback after meaningful favorable movement.

## Safety boundary

The shadow import graph contains no `order_send` path. LEARNED, BALANCED and EXPLORATORY are never demo eligible. Controlled demo remains blocked unless:

1. STRICT passes the existing walk-forward approval;
2. a non-expired, settings-matched V6.3 champion is approved;
3. its current probability passes the global or regime threshold;
4. all existing MT5 demo, account, feed, spread, news and risk checks pass.

Real-account execution remains disabled.
