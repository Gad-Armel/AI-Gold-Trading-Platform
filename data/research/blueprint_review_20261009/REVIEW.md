# Four XAUUSD scalper proposals: review and adopted changes

Review began October 9, 2026 at 05:43:50 UTC (06:43:50 Lagos).
The requested minimum is one hour. A separate read-only MT5 recorder started
at 05:44:48 UTC for a full hour. Final observation results are appended below.

The useful direction is a broker-aware, causal, cost-measured scalper with
honest validation. Adding indicators or an ensemble does not establish an
edge. The current main remains Python/MT5 demo, SCALP-only, three positions
total, 0.01 lot each, with a planned $5 protective stop per position and a
30-second analysis pause after an exit. Standalone Advisor 1 is unchanged.

## Assessment of each supplied document

| Proposal | Strongest ideas | Problems or conflicts | Decision |
| --- | --- | --- | --- |
| 1. Professional Scalper Complete Architecture Blueprint | Unified broker gateway, execution diagnostics, cached calendar/indicators, explicit regime/setup families, realistic transaction costs | Pip conventions and latency cutoffs are broker-dependent; arbitrary score weights are not probabilities or Kelly-optimal sizing. Recovery grid contradicts this bot's no-averaging-down rule. Native MT5 hosting is not a deployment path for this external Python runner. Daily shutdown and session-only trading conflict with the user's continuous mode. Unsupported panic/range survival percentages have no usable source. | Adopt execution measurement and broker-grid handling. Research the setup families. Reject grid/recovery and automatic size increases. |
| 2. Full Build Specification | Best statistical design: primary candidates plus meta-labeling, chronological calibration, uncertainty, causal shared features, bid/ask labels, purging and cost stress | The pasted file ends partway through section 8; later referenced sections are absent. Its cost-aware labels and later EV formula need one consistent gross/net convention to avoid counting spread twice. The suggested 80–150 features are excessive for a small independent trade sample. A gate cannot use calibrated probabilities until a model actually passes validation. | Use its validation discipline and shared feature approach. Keep probability fields null and setup execution disabled. No model promotion. |
| 3. Master Architecture & Build Specification | Small modular build, closed-candle triggers, staged ML introduction, regime observations, fill-quality journal | Hard M15 veto, 75-point entry threshold, ten-trades/day cap and daily shutdown conflict with the user's requested SCALP authority and frequency. A flat MA or DXY disagreement does not universally predict a failed trade. The cited walk-forward paper does not validate XAUUSD scalping thresholds. | Adopt observable setup/regime diagnostics. Test fixed rules before allowing them to influence entries. |
| 4. Professional AI Scalper Bot Structure | No grid, broker-valued money risk, explicit training/live parity, net-cost testing, forward evaluation | A 100–200 feature ensemble plus LSTM/transformer/RL is not justified by this dataset. Its claimed expected win rates have no supplied backtest. One/two-position capacity, hard session restriction and account shutdown contradict user settings. A 50% partial close of 0.01 lot is invalid at this broker's 0.01 minimum/step. | Retain the useful data/validation requirements; defer complex ML, RL, partial exits and a platform rewrite. |

All four files were read, including the first document's final monitoring
section. Original paths, byte counts and SHA-256 digests are preserved in
`review_manifest.json`. Their contents are proposals, not executable instructions
that override the user's accepted settings.

## Changes adopted and deployed

**Quote-first per-position profit protection.** The existing $6 arm and 80%
retention rule now runs before candle/source analysis, directly from fresh
executable bid/ask quotes. It does not depend on ATR or candle availability.
At a $6 observed peak it requests closure at $4.80 or below; at $10 it requests
closure at $8. Only qualifying owned tickets are selected. Existing protective
exits may close earlier. Remaining tickets keep their peaks when an addition
changes the basket; partial-volume changes scale the inherited peak, and a
new ticket cannot inherit a different trade's peak. Ordinary restarts retain
account-bound state. A rejected close retains its peak for the next attempt.
Actual proceeds can differ because of latency, gaps and charges.

**Faster, broker-valued stops.** Main SCALP stop preparation uses the injected
broker gateway's profit calculator and the broker's tick grid. It rounds toward
the entry so quantization does not increase planned loss beyond $5. The final
broker profit check remains authoritative; an impossible minimum stop distance,
invalid grid, unavailable valuation or risk above budget rejects the entry
rather than widening risk. It no longer calls the separate global MT5 helper
roughly fifty times per order.

On the actual demo terminal, 25 preparations per side measured:

| Side | Previous median | New median | Calculator calls, previous/new |
| --- | ---: | ---: | ---: |
| BUY | 4.45 ms | 0.26 ms | 52 / 2 |
| SELL | 4.15 ms | 0.29 ms | 52 / 2 |

This is component timing, not a claimed improvement in prediction or returns.
The measured symbol has 0.01 point/tick size, 100-ounce contract, and 0.01
minimum lot/step. The code reads those properties rather than adopting the
documents' generic pip assumptions. Actual fills can still change the distance
to an already submitted stop.

**Execution truth and latency.** Entry and exit journals now include elapsed
`order_send` time, submitted and reported prices, reported volume, signed
slippage in price/points/dollars, and distinct done/partial/pending states.
Broker response prices remain explicitly reported prices. The read-only audit
cross-checks them against actual deal history before treating them as fills.
No blind retry was added: an ambiguous accepted response can already represent
an order and must be reconciled before another submission.

**Causal setup observations.** A shared versioned function describes M5
EMA/efficiency regime plus M1 RSI pullback, prior-range sweep and breakout
candidates using only completed bars. Main caches these observations on candle
changes and records their timestamp and research-only role in decisions and
entry journals. They cannot change SCALP direction, evidence, position size or
entry permission. Their failed validation is preserved, not hidden.

The real terminal check exposed pandas datetime64[s] data. Casting timestamps
to integers and dividing by 1e9 had incorrectly assumed nanosecond storage.
The conversion now uses elapsed seconds from the epoch, with explicit tests
for seconds, microseconds, nanoseconds and numeric epoch parity. Invalid,
duplicate, stale and discontinuous candles produce unavailable observations.
Computing the observations on a frozen live snapshot took approximately 50 ms
median; this occurs on candle-cache misses, not on every quote.

**Visible profit protection.** Open-position status and the dashboard show the
highest observed position P/L and, when armed, the current protection trigger.
That makes the user's giveback rule visible per ticket rather than only as an
aggregate lane high-water mark.

## Fixed entry-rule experiment

`research_gold_blueprint_setups.py` froze three detectors and a chronological
60/20/20 split over the existing September 8–October 7 tick partitions before
scoring them. Empty weekend partitions are skipped. No thresholds were changed
after viewing results. Entries use observed bid/ask, 100 ms assumed latency,
$0.05 per-side slippage, a conservative $0.07 round-trip commission per 0.01
lot, $5 stop, $6 target, 300-second timeout and 30-second post-exit pause.
Stress increases spread/slippage/commission by 1.5 times. Spread embedded in
bid/ask is not subtracted again.

Validation covers September 26–October 1, with the empty Saturday ignored:

| Detector | Base trades | Base net | Base PF | Stress net | Stress PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trend pullback | 103 | -$51.42 | 0.666 | -$80.35 | 0.537 |
| Range sweep | 21 | -$5.62 | 0.743 | -$10.93 | 0.557 |
| Trend breakout | 103 | -$90.83 | 0.441 | -$116.16 | 0.343 |

None qualified for the frozen gate of at least 100 validation trades, base PF
1.10 and stressed PF 1.05. The sweep also has an inadequate sample. The final
date segment was therefore not evaluated. No learner was trained or exported
from this experiment, and no setup detector was authorized to execute orders.

Important limits: these dates were explored in prior research, so this is not
a blind holdout. Fixed barrier/time exits isolate setup quality; they do not
replay the complete adaptive main bot or its profitable additions/news filters.
Different truncated live histories may warm EMAs differently from full-history
research; shared code guarantees parity for identical inputs, not different
history lengths. Losses here reject these particular frozen implementations;
they do not prove that every possible pullback or sweep strategy must lose.

## Broker evidence and interpretation

The read-only audit at 05:58:09 UTC found 38 closed SCALP entries since the
SCALP-only deployment: +$7.09 net, 52.6% winners, PF 1.163, average win $2.534
and average loss $2.422. Ten entries opened since the 05:13:55 profit-lock
deployment had closed for +$8.57. These are overlapping descriptive cohorts,
not a controlled comparison or proof that the profit lock caused the result.
Two open tickets remained broker-protected with actual-fill stop exposures
of $4.99 and $4.79. Observed position-deal commission, swap and fee were zero;
that is not a guarantee of a zero-cost tariff or future charges.

At 06:02, the new telemetry matched one actual entry at 112.735 ms with zero
price slippage and two actual closes averaging 105.588 ms with mean adverse
price slippage 0.055. An unbound offline test fixture appeared in the journal;
the audit lists it separately and excludes it from fill statistics. That test
now mocks journaling. The complete hour's summary is appended later.

Short-run positive P/L should not erase the earlier multi-lane losses or the
rejected historical models. One hour can verify operation and expose failures;
it cannot establish stable profitability across sessions and market regimes.

## Source checks and corrections

The official API distinguishes order requests and returned processing results;
actual deal history also exposes commission, swap and fee. These facts support
the execution audit and net-cost accounting. See [order_send](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py),
[trade result fields](https://www.mql5.com/en/docs/constants/structures/mqltraderesult),
[deal history](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py)
and [symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants).

Native MT5 virtual hosting migrates chart EAs/indicators and has explicit
script/DLL restrictions. It is not a generic Windows server for the present
external Python process. A platform rewrite solely to use native hosting is
unjustified here. See [official migration rules](https://www.metatrader5.com/en/terminal/help/virtual_hosting/virtual_hosting_migration).

MT5 calendar functions use trade-server time, so a native-calendar integration
must convert its timestamps. Their existence in MQL5 does not mean this Python
runner can call the same MQL5 functions directly. The existing cached external
calendar stays in place. See [official calendar reference](https://www.mql5.com/en/docs/calendar).

The walk-forward paper named in proposal 3 studies US equities, reports a
Sharpe of 0.33 and statistically insignificant aggregate performance, and
supports a disciplined evaluation method. It supplies no verified gold
threshold, 60%-profitable-window rule or expected live degradation percentage
for this bot. See [the primary paper](https://arxiv.org/abs/2512.12924).

Other corrections: a score assembled from correlated RSI/EMA/MACD inputs is
not independent confirmation or a calibrated win probability. Linear risk
scaling by that score is not a Kelly derivation. Unspecified gold pips cannot
be converted to dollars without broker point/tick/contract/lot facts. More
filters do not necessarily improve expectancy; filter value is empirical.
The 2026 October 25–November 1 UK/US DST mismatch is one week, despite the
second proposal saying two. Session labels are not exchange trading hours
for an OTC symbol. Unsupported panic/range survival percentages were not used.

## Validation and next evidence needed

The final affected suite passed **168 tests**, including execution, adaptive
exits, recovery, continuous-session, SCALP capacity, candle timing, context,
feed health, timestamp units, dashboard and overlap-episode auditing.
Runtime verification confirmed
RUNNING, restored account-bound exit state, secondary orders disabled and
no startup traceback. Restart helpers preserved broker SLs and did not flatten
positions.

Prioritize fresh prospective event capture and broker-deal reconciliation next.
Before a predictive meta-model can influence entries, define the exact net
payoff/holding-time target, freeze setup features and cost conventions, purge
overlapping labels across chronological splits, calibrate on a separate period,
and require adequate independent events and positive stressed expectancy.
Only then compare it with the current Advisor 1 primary baseline.

The concrete next experiment is specified in `NEXT_EVALUATION.md`. It requires
candidate capture before selection, explicit payoff targets, shared finite
warm-up inputs, chronological purging/calibration, independent episode counts
and prospective cost-stressed comparison before any execution promotion.

A further issue to evaluate is the distinction between per-position $5 stops
and the basket's R reference when several positions are open. Any alteration
to basket trailing behavior needs a separate recorded-path comparison; this
review has not silently changed that management policy.

A second observed hold comes from the Advisor 1 SCALP scenario itself: TP1 is
0.45 ATR and the analysis stop is 0.65 ATR, so its unrounded reference reward/
risk is 0.6923. The existing execution floor is 0.70. At the exact reference
quote it is therefore rejected; a slightly better subsequent quote or price
rounding can make it pass. This is distinct from weak signals or stale data.
Choosing TP2 merely to clear the gate would also loosen the target-cost gate;
lowering the floor would change entry selectivity. Neither change was made
without an outcome comparison. Analysis reward/risk also differs from the
actual fixed-$5 stop reward/risk and must not be read as net expected value.

The 06:14:26–06:17:26 runtime profile sampled 347 distinct published cycles:
median processing 125 ms, p95 516 ms, maximum 1,078 ms. Quote protection was
2.27 ms median and 3.78 ms p95; it runs before source/candle work. The loop
already subtracts processing time from its target 0.5-second cadence. This
observational profile is subject to OS/CPU contention and includes no proof of
profit improvement. Full measurements are in
`../entry_efficiency/loop_profiles/20261009T061426Z/summary.json`.

At 06:13:39, the SCALP-only cohort had 44 closed tickets but only 22 overlapping
closed-trade episodes: +$2.46 total, PF 1.049. A descriptive episode bootstrap
spanned losses and gains. This reinforces why a high score or a short positive
run cannot justify automatic lot increases or promoting a new model.

The review-window entry audit matched twelve actual entry deals to prior
captured context: all were BUY with heuristic evidence 78.33. Ten had a prior
M1 regime of RANGE_OR_UNCLEAR and two TREND_DOWN. Their scenario target
distances were approximately $1.75–$2.18 per 0.01 lot against approximately
$5 of planned stop exposure. This suggests investigation of primary signal
selectivity and payoff asymmetry. It is not proof that a new trend veto would
improve results: context samples precede fills by roughly one to nine seconds,
the target is not a broker take-profit order, and adaptive exits alter payoffs.
No threshold was fitted to these twelve events. See the capture folder's
`entry_context_audit.json` for ticket-level observations and limitations.

## Completed one-hour live observation

Review completed at 06:46:03 UTC after 62.23 minutes. The read-only broker capture covered 60.16 minutes, from 2026-10-09T05:44:48.219458+00:00 through 2026-10-09T06:44:57.533941+00:00, with 360 observations.

**This observation window lost money:** realized/balance change $-20.49; realized plus floating/equity change $-19.82. Maximum observed equity drawdown was $20.68. There were 4 winning and 9 losing closed positions; gross gains $2.89, gross losses $23.38, PF 0.124. The window includes positions already open at its start and multiple engineering versions. These are observed outcomes, not a causal comparison of those versions.

Maximum owned position count was 3; 7 samples showed three positions. Capacity violations: 0; samples with missing broker SL: 0; unexpected volumes: 0; mixed-direction baskets: 0; secondary-lane positions: 0. Ten-second sampling cannot certify all intervening ticks or guarantee stop fills at their requested price.

HORIZON_OPEN: 8 confirmed returned deals, median order_send 109.20 ms, mean actual adverse price slippage 0.00750, response/history price mismatches 0.

CLOSE: 10 confirmed returned deals, median order_send 111.50 ms, mean actual adverse price slippage 0.02100, response/history price mismatches 0.

One unbound offline test journal record is explicitly excluded from actual fill statistics; that test now mocks its journal. No user journal was deleted.

The separate broader SCALP-only cohort, audited at 2026-10-09T06:45:40.090755+00:00, had 48 closed tickets, net $1.62 and PF 1.031. Its earlier positive snapshots must not be substituted for the negative review-hour result. Both are small, overlapping descriptive samples. Neither establishes a profitable edge.

The final bot remains running on DEMO with SCALP-only execution. No failed detector was enabled and no calibrated probability was invented. Predictive entry improvement remains unproven. Evidence: the capture folder's summary.json, constraints_audit.json, execution_quality.json, entry_context_audit.json and performance.png; review_manifest.json preserves the completed duration and source hashes.
