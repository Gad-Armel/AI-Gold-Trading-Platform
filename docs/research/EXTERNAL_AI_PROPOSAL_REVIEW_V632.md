# External AI Proposal Review — V6.3.2

Two external AI proposals were reviewed line by line. Neither codebase was copied directly.

## Useful ideas retained

1. **Order-flow / quote-flow imbalance**
   - Added as a normalized signed bid/ask quote-change proxy.
   - It is not called true OFI because the MT5 top-of-book feed does not expose queue sizes.

2. **Micro-regime classification**
   - Added IMPULSE, REVERSAL, ROTATION, STALLED and DISLOCATED regimes.
   - Regimes are model inputs only; they never bypass hard gates.

3. **Non-linear challenger**
   - Added a shallow, regularized Gradient Boosting challenger.
   - It must pass the same purged chronological OOS, calibration, expectancy and drift controls as every other model.

4. **Feature diagnostics**
   - Added out-of-sample permutation importance using Brier-score degradation.
   - Diagnostics never mutate thresholds automatically.

5. **Stronger walk-forward reliability**
   - Added a one-sided Wilson lower bound for the selected OOS win rate.
   - Added selected-trade stability across folds and a cap on negative folds.

## Ideas rejected

- Lowering STRICT score, margin, microstructure and persistence thresholds merely to create more trades.
- Recursive parameter mutation until a backtest displays 59%. This is optimization-to-the-test and can loop indefinitely.
- One 70/30 split presented as walk-forward validation.
- Labels based only on a future return while ignoring spread, TP, SL and actual exit outcomes.
- Training on LEARNED-lane outcomes, which creates a self-reinforcing feedback loop.
- Majority-of-checks gates that allow hard safety failures to be outvoted.
- Returning 0.50 probability when the model is absent and then accepting it.
- Dynamic no-progress exits that do not check elapsed time.
- The proposed XAU P/L multiplication by 100 for 0.01 lot. Under the project contract assumptions, a $1 XAU price move is approximately $1 P/L at 0.01 lot.
- Feature-importance-driven automatic threshold changes. Feature importance does not identify the correct threshold or causal direction.

## Release principle

V6.3.2 remains shadow-first. A model is allowed only to abstain from an already safe candidate. It cannot repair a failed spread, news, quote-freshness, structure or account check.
