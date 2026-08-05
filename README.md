# AI Trading Platform V6.3.6 — Tick-Horizon Fast Research

## V6.3.6 additions

- adds a research-only FAST lane built from raw MT5 ticks because MT5 has no
  native S1/S5 standard chart bars;
- requires aligned 1-second and 5-second tick direction/velocity, aligned
  3-second quote flow, tight spread, good data quality and safe regimes;
- caps FAST shadow positions at 15 seconds and keeps the lane ineligible for
  demo execution or promotion of the STRICT hypothesis.

## V6.3.5 additions

- STRICT entry now respects an explicit higher-level `NO_TRADE` regime and
  rejects an opposing directional regime;
- fixes the learner's verified ADX field from the nonexistent `adx` key to
  `adx_m5`;
- starts a clean strategy generation because the accepted-trade population and
  model feature values have changed.

## V6.3.4 additions

- fixes the production `1`/`3`/`5` micro-window schema mismatch in the V6 gate;
- requires reliable tick data and directionally aligned quote-flow pressure;
- blocks entries during rapid spread expansion and stalled/dislocated tape;
- records the new microstructure checks in gate telemetry and starts a clean
  strategy generation so older results cannot authorize the changed policy.

## V6.3.3 additions

- a `NO_PROGRESS_THESIS_EXIT` or adverse tape exit cannot re-enter the same
  direction after a one-cycle gate flicker; a genuine candidate-direction reset
  is required;
- the shadow console prints process-session P/L after closes and at shutdown;
- model training and lane reports exclude outcomes from older strategy IDs, so
  the changed policy receives a clean forward evaluation.
- an isolated `XAUUSD_LIVE_CANDLE_FADE_5S_V3` benchmark tests the inverse
  hypothesis “live green M1 candle → SELL; live red M1 candle → BUY”, with a
  $0.40 target, five-second maximum hold, immediate next-cycle re-entry, real bid/ask costs
  and no broker-order path.

## V6.3.2 additions

- model promotion now reserves the final chronological fold as an untouched
  holdout; probability cutoffs are selected only on earlier walk-forward
  predictions, and pre-holdout model artifacts are rejected;
- conservative target-fill accounting: target crossings are booked at the planned barrier;
- adverse stop gaps remain booked at the observed executable quote;
- observed quote P/L and polling overshoot are retained for diagnostics;

- quote-flow imbalance proxy from signed bid/ask changes;
- micro-regime features: IMPULSE, REVERSAL, ROTATION, STALLED and DISLOCATED;
- calibrated Gradient Boosting challenger;
- confidence-aware OOS win-rate lower bound;
- selected-trade stability across chronological folds;
- OOS permutation-importance diagnostics;
- no relaxation of STRICT execution thresholds.

See `docs/V6_3_2_CONSERVATIVE_SHADOW_FILLS.md`, `docs/V6_3_1_ORDER_FLOW_REGIME_LEARNING.md`, and `docs/research/EXTERNAL_AI_PROPOSAL_REVIEW_V632.md`.

A shadow-first XAUUSD scalping research system for MetaTrader 5. V6.3 aims for at least 59% out-of-sample win rate on the **selected trade subset**, while also requiring positive expectancy, profit factor and probability calibration. This is a validation target, not a promise.

## Default mode

**SHADOW ONLY.** Real-account execution is disabled. Controlled demo remains locked behind both STRICT walk-forward approval and an approved V6.3 calibrated model.

## Four shadow lanes

- `STRICT`: exact future demo hypothesis.
- `BALANCED`: broader structural counterfactual, research only.
- `EXPLORATORY`: wider non-opposed counterfactual, research only.
- `LEARNED`: EXPLORATORY candidate plus approved calibrated probability threshold, research only.

Only STRICT can ever become demo eligible. LEARNED cannot send an order.

## Safe self-learning

V6.3:

- compares logistic, balanced-logistic and random-forest challengers;
- calibrates predicted probabilities;
- uses purged chronological walk-forward folds;
- targets >=59% OOS win rate, >=+$0.03 expectancy and >=1.15 profit factor;
- excludes LEARNED trades from its own retraining data;
- de-correlates duplicate cross-lane market episodes;
- uses champion/challenger promotion, model expiry and drift blocking;
- abstains when confidence is insufficient.

## Adaptive exits

Targets and stops are derived from live spread and M1 ATR within controlled ranges. Target/stop ratio must be at least 0.80, with staged profit-lock exits.

## Commands

```text
python run_scalping_all_tests.py
python run_scalping_audit.py
python run_unified_news_update.py
python run_scalping_shadow_loop.py --max-minutes 0
python run_gold_advisor.py --once
python run_gold_advisor.py --interval-seconds 15
python run_medium_horizon_shadow_loop.py --max-minutes 0
python run_v6_lane_review.py
python run_v63_self_learning_review.py
python run_v63_model_status.py
python run_v6_walk_forward_review.py
```

## Minimum evidence

Model training starts only after at least 80 de-correlated closed base-lane episodes. Controlled-demo approval still requires the stricter walk-forward sample, including at least 200 closed STRICT shadow trades and an approved model.

See:

- `docs/V6_3_2_CONSERVATIVE_SHADOW_FILLS.md`
- `docs/V6_3_0_CALIBRATED_SELF_LEARNING.md`
- `docs/V6_3_1_ORDER_FLOW_REGIME_LEARNING.md`
- `docs/research/EXTERNAL_AI_PROPOSAL_REVIEW_V632.md`
- `docs/research/V6_3_RESEARCH_SYNTHESIS.md`
- `docs/ARCHITECTURE_AND_SAFETY.md`

No trading system can guarantee a win rate or profit.

## Medium-horizon shadow model

`run_medium_horizon_shadow_loop.py` is an isolated alternative to the scalper.
It derives 45-minute and 2-hour views from completed broker M15/H1 bars and
combines them with completed H1/H4 views. Entry requires at least three of four
directions to agree, an executable spread no wider than $0.30, a fresh quote,
and a non-overextended price. It uses a $1.50 target, $1.80 hard stop, four-hour
maximum hold, no daily entry cap, and at most two non-hedged shadow positions.
One completed M15 signal may enter only once. It has no broker-order path.

Historical validation subsequently rejected this first hypothesis. On two years
of broker candles with a conservative $0.30 assumed spread and pessimistic
same-bar barrier ordering, the episode-rearmed version produced 1,581 trades,
37.2% wins, -$0.573 expectancy and 0.49 profit factor; every quarterly fold was
negative. `SCALPING_MEDIUM_ENTRY_ENABLED` therefore defaults to `False`.
The runner may analyze conditions, but it cannot open new shadow positions.
Do not enable it by fitting thresholds to the same dataset.

Research commands:

```text
python run_medium_horizon_data_collection.py --days 730
python run_medium_horizon_backtest.py data/research/medium_horizon/XAUUSD/20240724_20260724 --spread 0.30
```
