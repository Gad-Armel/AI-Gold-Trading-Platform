# Review of the end-to-end XAUUSD architecture

## Decision

Use this as a checklist of possible components, not evidence of a working or
profitable ensemble. It contains no trained weights, executable environment,
dataset provenance or validation results. Existing market feeds, macro adapters,
completed-candle features and adaptive exits already cover several proposed layers.

The concrete improvement adopted is durable adaptive-position state and explicit
adverse-excursion tracking. The two-position TOTAL limit, exact 0.01-lot entries,
$100 capital profile, $2 planned risk limit and $5 rolling loss threshold remain
in force. Advisor 1 is not modified.

## Implemented recovery

`services/research/gold_exit_state.py` persists the best and worst observed
price movement, monitoring start time, prior position IDs and the last-close
candle marker. The adaptive demo runner writes a checkpoint after each completed
cycle to `data/runtime/gold_adaptive_exit_state.json`.

Checkpoints are bound to an account/server identity hash, account mode, XAUUSD,
lane configuration and adaptive-exit parameters. Restored excursions are also
bound to each position's ticket, direction, entry price and volume. Another
account or a different trade cannot inherit the old trade's peak.

The monitoring clock now uses epoch seconds for portable restart timestamps.
Adverse-signal confirmation is deliberately reset when loading: downtime does
not prove an opposing signal persisted. Re-entry markers survive a restart,
while fresh entry confirmation still has to build again.

Malformed, nonfinite, future-dated, mismatched or more-than-seven-day-old state
is rejected. Recovery status is exposed in the runner's status JSON. Rejection
means starting fresh monitoring from actual broker positions; it does not
invent a previous excursion or automatically flatten a position. Broker-side
stops and existing loss controls remain independent. A checkpoint write failure
propagates into the runner's existing protective shutdown path.

This is recovery of the latest saved observations, not a reconstruction of prices
while the program was offline. It does not automatically restart Python or
reconnect a terminal. Controlled positions are still closed during an ordinary
demo shutdown under the existing setting; recovery mainly matters after an
unexpected process interruption or an incomplete close.

## Proposal decisions

| Proposal | Decision and reason |
|---|---|
| Maximum three positions | Rejected: user maximum is two across all lanes. |
| ATR/confidence-based lot increases | Rejected: every new entry must be exactly 0.01 lot. A setup that cannot fit the risk budget is skipped. |
| Partial 50% exits | Not enabled: half of 0.01 is 0.005, which requires broker minimum-volume and volume-step support. Keep whole-position exits for this profile. |
| Peak and adverse-excursion monitoring | Adopted, with restart-safe persistence and trade/account binding. |
| Automatic reconnection | Deferred until recovery can verify identity, pending orders and actual fills before any retry. Blind resubmission may duplicate exposure. |
| Multi-timeframe forward fill | Sound only after features become available at candle completion. Joining by the higher candle's opening time can leak its future close. |
| Five-year training, six-month validation/test | A proposed schedule, not a universal requirement or proof. Our M1/M5 archives do not establish five years of synchronized point-in-time macro and tick coverage. |
| Large LSTM, 500 depth-8 trees and HMM ensemble | Not installed without a validated dataset and improvement over simpler baselines. Architecture size is not evidence of predictive value. |
| Fixed 0.6 regime-dependent weights | Unsupported initial guesses. Require validation, including how regime probabilities were known at each decision time. |
| Walk-forward prevents overfitting | Too strong. It helps preserve chronology but repeated tuning, leakage and model selection can still overfit. |
| Holdings, ETF volume and institutional flows | Keep distinct. Exchange volume alone does not identify net institutional buying or ETF creations/redemptions. |
| Keyword bullish/bearish news lists | Research features only; words ignore negation, timing, expectations and what the market already priced. No new directional authority added. |
| Banks always hunt liquidity / a structure break means continuation | Unsupported universal statements. Existing gap and sweep fields remain observed candle patterns, explicitly research-only. |
| Fixed UTC session windows and optimal kill zones | Need daylight-saving-aware local exchange/session times and observed cost/return analysis. No automatic session-based risk boost. |
| OnTick automatically reads sockets | Incorrect as a general API description: OnTick handles NewTick events; a socket bridge requires additional implementation. Keep the existing Python bridge. |
| Exit only when profitable unless confidence exceeds 0.8 | Not adopted. Thesis invalidation and risk control cannot depend on first returning to profit; the supplied thresholds are uncalibrated. |
| Sharpe >1.5, PF >1.5, accuracy >60%, latency <100ms | Targets, not reported results. Profitability requires net payoff and costs; signal accuracy alone is insufficient. |
| Weekly/monthly automatic promotion | Rejected. Retraining is separate from execution approval; a new candidate must pass independent evaluation. |

## Validation

Tests cover excursion recovery, wrong-account isolation, new-ticket isolation,
resetting confirmation after downtime, corrupt/future/nonfinite checkpoints,
worst observed movement and persistence of flat-lane re-entry markers. The full
suite also retains global position-cap, fixed-size, broker-clock, risk-budget and
proposal-01 feature checks. Results are saved in
`data/research/xauusd_audit/validation.json`.

No trained ensemble was promoted and no order was sent for this review. Run
commands remain unchanged; recovery is automatic only for
`--mode demo --exit-policy adaptive`. Shadow runs never load or overwrite the
demo checkpoint.

## Sources

- Submitted `pasted-text.txt`, attachment `cae51ed2-ccf4-491a-8e23-a9de7c67f05d`.
- MetaQuotes, [symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants): volume minimum/step and broker contract metadata.
- MetaQuotes, [OnTick](https://www.mql5.com/en/docs/event_handlers/ontick): NewTick event handling, not an implicit socket protocol.
- pandas, [merge_asof](https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html): backward temporal matching; the application must provide truthful availability timestamps.
- Bailey et al., [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf): selection and backtest-overfitting concerns.

Primary sources checked September 10, 2026. Statements about this implementation
are supported by the code and tests, not by the supplied proposal's targets.
