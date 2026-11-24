# SMC micro-scalping specifications: project-specific review

Date: 19 October 2026. Scope: review and design, not strategy deployment.

## Review record

- Review started: 2026-10-19 22:11:49 UTC / 23:11:49 Africa/Lagos.
- Review completed: 2026-10-19 22:42:03 UTC; elapsed review window: 1814 seconds.
- The requested minimum 30-minute window was respected before writing this report.
- All three attachments were read in full: 357 + 125 + 866 = 1,348 lines.
- No trading source, live configuration, running process or broker position was changed for this review.
- Targeted baseline: 109 tests and 5 subtests passed. This is not the entire historical suite and not a profitability test.
- Advisor 1: all 18 protected files still match their stored reference hashes.

Inputs, identified by attachment directory and SHA256:
1. 4731ad13-c69a-4ac7-8de9-5b10d60d2463/Pasted text.txt
   bf6d155b55005b0716c1004465301b2fdedb4267200578eaa5f89096585637f8
2. 203cd135-d550-462e-904f-0e9c15cadbe0/Pasted text.txt
   5c882e2301cb77fe0b75295b5288a7320678c851956544517852cfdc48d45d14
3. 7a6cb9fc-0a23-4ae7-a335-cf175b0f562e/Pasted text.txt
   ac2d6eb269a6a2e75b61273068df6b09b510adfeb8cd37bae795feeef78cf4dd

## 1. Recommended governing interpretation

Use document 1 as the architectural and validation backbone. Use document 3 as
the defensive execution and operational checklist. Document 2 supplies strategy
examples, not authority to introduce fixed TP, other instruments or automatic
real-money execution.

The documents are useful specifications, not evidence that SMC has an edge.
Order blocks, liquidity pools and absorption must be treated as objectively
defined price/activity patterns. Broker quotes do not reveal institutional
intent or prove that stops were deliberately hunted.

Preserve the existing project and Advisor 1. Do not scaffold a second complete
trading platform merely to match example filenames. Keep one order authority.
The active Python main is the initial integration target; existing native MQL5
code is a separate implementation, not proof of Python/native strategy parity.
A future native port requires its own explicit deployment and parity gate.
Never attach it alongside the Python executor to the same controlled exposure.

The rule that only a gateway imports MetaTrader5 cannot be imposed globally on
protected Advisor 1 modules without violating their isolation. Apply the new
ownership boundary to the migrated main path, document legacy exceptions, and
schedule legacy broker calls on that owner where feasible. Do not silently edit
protected modules or claim the entire repository already satisfies that rule.

## 2. Conflicts that must not be silently applied

| Topic | Conflict | Review disposition |
| --- | --- | --- |
| Instrument | Documents 2/3 allow FX and indices; current mandate is gold only | Orders exclusively on verified XAUUSD; other feeds may remain context |
| Entry sequence | Existing 3/5/6 consecutive M1 rule versus sweep/retest with a counter-direction bar | Keep current reference; evaluate SMC as an alternative, not contradictory mandatory filters |
| Position cap | Five slots but master says maximum three in the same direction | With opposite exposure prohibited, the latter is effectively a three-position cap; do not silently replace the approved five-position policy |
| Setup independence | Master requires a fresh independent setup per position; current stages add to one directional campaign | Record setup/campaign identity and compare marginal additions before changing allocation |
| Sizing | Fixed 0.01 lot versus fractional equity risk and score scaling | Do not increase lots; a budget that cannot accommodate 0.01 must reject, not round up |
| Model fallback | Half-size fallback versus a possible 0.01 minimum/step | 0.005 may be untradeable; no fake half-risk mode |
| Partials | 40–50% closes versus 0.01 position/minimum lot | Disable impossible partials; ticket-level exits are a different strategy, not equivalent partial closes |
| Take profit | Documents 2/3 request fixed RR targets and mandatory TP fields | Retain broker TP=0 and dynamic exits; opposing zones can inform decisions, not impose a fixed maximum TP |
| Stops | Document 3 allows an emergency exception to widening | Reject widening/removing a protective stop after entry |
| Loss stops | New mandatory daily/weekly/DD controls versus earlier disabled session-loss policy | Explicitly unresolved for activation; recommend a protected new profile, never pretend those controls are already active |
| Account type | Master requires hedging; document 3 requests netting support | Independent positions require hedging; keep netting blocked rather than simulate five independent positions |
| Pending orders | Limit/stop orders proposed; active strategy uses market entries | Market-first; pending support only after reservation, expiry, cancellation and reconciliation tests |
| Entry cadence | Proposed 15 s and 1 h loss pause versus existing timing/cooldowns | New profile proposal, not an untested global configuration replacement |
| Platform | Python-first master versus MQL5-preferred examples | Reuse Python first; a native port is a later decision, not concurrent execution |
| Real mode | Examples include manual real enablement | Keep real execution unavailable in this work; validation never promotes automatically |

These are not reasons to discard the specifications. They are policy decisions
to settle in the consolidated design before changing execution.

## 3. Corrections required in the master specification

### 3.1 Tick identity and completeness

Do not deduplicate on time_msc alone. The official Python example contains two
different prices with the same millisecond timestamp. Preserve raw fields,
source ordering and multiplicity. Reconcile overlapping downloads without
collapsing distinct same-time events. Even identical field tuples can represent
separate events; overlap reconciliation must state its assumptions.

symbol_info_tick returns the latest state, not a lossless event stream.
Fast polling alone cannot establish complete tick coverage. Use bounded history
catch-up, overlap accounting, cursor tests and backpressure/overflow reporting.
The existing quote recorder samples the main loop and is not a full tick tape.

Native OnTick is also not a guarantee of one callback per broker tick. It can
coalesce updates while a handler is busy. A native implementation likewise needs
history catch-up if all events matter.
Sources: [copy_ticks_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py),
[symbol_info_tick](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py),
[OnTick](https://www.mql5.com/en/docs/event_handlers/ontick).

### 3.2 Clock contracts

The official Python API documents UTC, while the current broker adapter
deliberately applies a measured +3-hour server offset. Do not add another
unconditional conversion and shift the same tick twice. Keep raw broker time,
receipt UTC, normalized event UTC, clock-policy identity and monotonic durations.
Verify the mapping against actual terminal data before replacing it.

Use London/New York local session definitions with DST-aware timezone conversion
when the intention is their local opens. Fixed UTC windows are legitimate only
when explicitly intended as fixed UTC windows. Test the weeks when US and UK
DST transitions differ. Native economic-calendar times use server time, which
must not be confused with Python API UTC.
Source: [MQL5 calendar](https://www.mql5.com/en/docs/calendar).

### 3.3 Single owner and watchdog

A single serialized MT5 command owner is a reasonable safety design; the reviewed
documentation does not establish a blanket guarantee about Python thread safety.
An independent watchdog cannot promise to flatten through the very command queue
that is hung. Calling MT5 directly from a second thread contradicts single ownership.
Python CPU/GIL stalls and terminal/network failure further limit local guarantees.

Design a bounded priority command channel and explicit owner-health state.
During a genuine owner failure, block new work, alert, preserve server-side SLs,
and reconcile before restarting. Any independent native safety component needs
a separately reviewed protocol. No architecture can guarantee an immediate close
when the broker or connection is unavailable.

### 3.4 Latency budgets

Separate feature-computation time, data-fetch time, queue delay, send/ack duration,
broker-reported fill time and end-to-end delay. Report tails (p95/p99), backlog and
maximums, not just averages. An acknowledgement is not a confirmed deal.

A <5 ms compute target does not promise a <5 ms fill. The native timer documentation
also describes practical timing limits; reducing a sleep interval is not proof of
better fills or a better trading edge.
Sources: [OnTimer](https://www.mql5.com/en/docs/event_handlers/ontimer),
[OrderSendAsync](https://www.mql5.com/en/docs/trading/ordersendasync).

### 3.5 Cost accounting and expected value

The proposed p_win formula is insufficient for the proposed dynamic exit policy.
P(+1R before -1R) describes one barrier event, not the distribution of final
results with partials, early exits, runners, gaps and timeouts.

Estimate policy-specific net expectancy including time-barrier outcomes and
average losses, which need not equal exactly 1R. If fills/P&L already use executable
bid/ask, the spread is already in those prices: do not subtract it a second time.
Use explicit conventions for per-side versus round-trip commission, lot scaling,
entry/exit slippage, swap and account-currency conversion.

A heuristic evidence score is not p_win. Missing/unreliable edge estimates cannot
be replaced with an invented probability or arbitrary historical average.
Until validated statistics exist, a new SMC candidate remains shadow-only.
A gross favorable distance greater than costs is necessary, not sufficient proof
of positive expectancy.

### 3.6 Fixed lots versus small-account risk

Illustration only, not freshly measured broker metadata: at a contract size of
100 and volume 0.01, a 1 USD gold-price move is approximately 1 USD of P/L in a USD
account. On a 100 USD account, 0.35% risk is 0.35 USD. A structural stop wider than
0.35 price units cannot fit that budget before additional costs.

At an illustrative 0.24 spread, the master's six-spread minimum stop is 1.44 price
units, already incompatible with that 0.35 USD budget under these assumptions.
The correct result is no trade, not an artificially tightened invalidation stop
or increased risk. More restrictive risk can legitimately produce very few trades.

Use broker-valued loss via order_calc_profit and margin checks. Planned stop risk
is not an absolute bound on realized loss during gaps/slippage.
Sources: [symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants),
[order_calc_profit](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py).

### 3.7 Volume terminology

Tick count, quote rate, signed tick-rule imbalance, candle-direction-assigned
volume and real trade volume are different variables. Do not label a green
candle's entire activity as observed aggressive buying. Repeated unchanged fields
in MqlTick must not be summed as new volume without checking flags/semantics.

A broker-local activity profile is not a consolidated exchange volume profile.
Where actual trade volume is unavailable, label POC/VAH/VAL and VWAP-like measures
as activity-weighted proxies. Same-time-of-day RVOL needs historical session/DST
alignment and sufficient days; 24 hours cannot supply a 20-day seasonal baseline.
Source: [CopyTicks field and flag semantics](https://www.mql5.com/en/docs/series/copyticks).

### 3.8 Zone causality

Store both anchor_at and known_at. An OB candle may precede the displacement,
but the zone is not available for trading until displacement/BOS confirmation.
A fractal requires its right-side bars; a three-bar FVG requires the third bar.
BOS must use a swing already confirmed at the decision time.

Likewise, do not use a session's eventual high/low as if known at its opening.
Persist zone identity and lifecycle rather than repainting history after retests.
Test prefix invariance, future perturbations, ties and exact confirmation times.
Shuffling bars is not by itself an anti-lookahead proof.

### 3.9 Entry fills and intent lifecycle

A limit order is not automatically superior: it can miss the move or fill when
the price is moving adversely. Replay placement time, bid/ask trigger, expiry,
partial fills, gaps and cancellation/fill races. Do not count a historical touch
before order placement as a fill, or infer within-bar event order from OHLC.

Reserve both slots and planned risk for pending AND in-flight requests. A timeout
does not prove an order was not executed. Reconcile orders, positions and deal
history before a retry; comments can assist attribution but are not a guaranteed
broker idempotency key. Ambiguous execution should pause further entries.

OrderCheck success does not guarantee execution. Native async requests require
transaction handling; one request can generate multiple out-of-order events.
Sources: [OrderCheck](https://www.mql5.com/en/docs/trading/ordercheck),
[OnTradeTransaction](https://www.mql5.com/en/docs/event_handlers/ontradetransaction),
[return codes](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes).

Broker policy is a separate prerequisite: symbol metadata cannot establish all
contractual scalping permissions or minimum holding-time restrictions. Check the
broker's documented terms and account conditions rather than inventing a terminal
capability that discovers them automatically.

### 3.10 Risk controls cannot inhibit protection

A spread cap, friction budget, daily halt, ML timeout or stale calendar must not
silently disable protective management of an already-open position. Distinguish
block-new-entries, cancel-pendings, manage-existing, requested-flatten and confirmed-flat.

Persist daily/weekly baselines across process restarts, account changes and
deposits/withdrawals. Specify bot-only versus account-wide accounting. Do not fund
new risk with unconfirmed floating profits or assume a break-even stop eliminates
all commissions and gap risk.

A STOP.txt proposal must not silently replace the existing
data/EMERGENCY_STOP.flag integration, especially because shared components and
Advisor 1 are protected.

### 3.11 ML validation

Calibration should be required when probabilities drive a cost gate, but isotonic
need not be mandatory. It can overfit smaller samples; compare sigmoid/isotonic
on independent chronological calibration data, with Brier/log loss and reliability
analysis. No model training or calibration may use the final untouched test set.

Triple-barrier labels need timeouts and right-censoring, executable prices,
fold-boundary purging and campaign/event overlap accounting. The exit model must
be validated under the entry/exit policy that generates its samples. Retraining
is separate from deployment; weekly scheduling does not authorize promotion.
Source: [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html).

### 3.12 Evidence thresholds are gates, not proof

Four weeks/300 trades, PF >=1.4 and DD <8% are proposed qualification gates, not
statistical guarantees. Five correlated tickets are not five independent bets.
Use campaign-aware/block-based uncertainty and stress testing, multiple regimes,
parameter plateaus and a complete record of attempted variants.

Trade shuffling alone destroys serial dependence and does not reproduce the live
risk path. A shared strategy core reduces divergence but does not guarantee replay
parity: event receipt order, state, data revisions, calendars, fills and simulator
rules must match too. Never optimize live based on a handful of recent outcomes.
Method reference: [Probability of backtest overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## 4. Existing implementation mapped to the request

| Existing asset | What can be reused | What is not yet established |
| --- | --- | --- |
| run_gold_consensus_bot.py | Demo main, phased timing, early quote protections, shadow diagnostics | Not one event/intent core shared with a full simulator |
| gold_consensus_demo_broker.py | Demo identity, hedging check, 0.01 lot, server SL, cap/rechecks, order_check, result metrics | Not a complete pending/in-flight reservation and idempotent retry ledger |
| gold_tick_history.py | Incremental bounded tick history, freshness/error reporting | Not a lossless durable raw event tape with full multiplicity/receipt ordering |
| gold_research_recorder.py | Forward decisions, loop quotes and rejection context | Loop quotes are sampled; blocking JSONL writes are not a 5 ms hot-path design |
| gold_scalp_setups.py | Causal pullback/sweep/breakout research observations | No full confirmed-swing BOS/CHoCH plus persistent OB/FVG lifecycle engine |
| gold_entry_structure_features.py | Geometry, wick, sweep and local volume-weighted research features | Not institutional order flow or validated volume-profile edge |
| gold_retest_shadow.py | Closed-bar retest candidate, expiry/invalidation, no order authority | Not a complete SMC setup or live-approved entry rule |
| gold_m1_quality.py / gold_s30_shadow.py | Cost/extension geometry and S30 observations | Neither supplies calibrated profitable-entry probability |
| gold_exit_state.py | Account/policy-bound recovery and selected cooldown state | Not the complete proposed order/zone/risk state machine |
| gold_main_event_calendar.py | Isolated schedule supplement, provenance and timezone handling | Not a guarantee of complete unscheduled-news protection |
| gold_learned_policy.py | Experimental local forecast/filter interface | Not the specified calibrated tick-level barrier/hold models; main defaults off |
| mql5/Experts/GoldScalpAI | Existing native execution, entry, safety, telemetry and test assets | Separate strategy/version; must not be mistaken for active Python parity |

The present main cost check compares spread to an analysis-derived target and
checks reward/risk. It is NOT the master's all-in calibrated EV gate. SCALP uses
ANALYSIS stops, so its legacy fixed USD risk budget is not enforced by that mode.
The existing SESSION_LOSS_STOP_ENABLED flag is False. These facts must remain
visible when comparing the current bot with the safer proposed architecture.

Dependencies inspected in .venv-audit:
MetaTrader5 5.0.6231, numpy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1, pyarrow 26.0.0.
LightGBM, numba and pydantic are not installed there. No packages were installed.
Do not claim the ML stack or a numba hot path is ready merely because it appears
in a proposed requirements list.

## 5. Consolidated implementation sequence, not executed in this review

### M0 — Freeze policy and baseline

Resolve the conflicts above, version the candidate specification, retain the
current strategy as the comparator and inventory protected dependencies.
Acceptance: explicit policy table, account/instrument scope, source hashes,
baseline tests, rollback and no second active executor.

### M1 — Data and event foundation, without orders

Introduce deterministic events/intents and one bounded main-only broker access
boundary. Add raw tick capture, overlap reconciliation, incremental bars,
clock policy, feature readiness and structured buffered logging.
Acceptance: synthetic stream fixtures including same-ms distinct ticks, duplicates
from overlap, late data, restart cursors, empty intervals, market-closed periods,
queue overload and clock discontinuities. Then collect at least 24 market hours.
A 30-minute review cannot certify 24-hour operation or 20-day RVOL readiness.

### M2 — Causal analytics

Confirmed swings/BOS/CHoCH, objective OB/FVG lifecycle, sweep versus accepted break,
clustered S/R and explicitly labelled activity-volume features.
Acceptance: hand-labelled long/short fixtures, known_at timestamps, invalidation,
retests, expiry, plots, prefix/future-perturbation tests and no order path.

### M3 — Rules-only candidates and costs

Implement setup A/B/C as separate alternatives, one at a time. Leave profile fade
and advanced delta/absorption as optional research until data supports them.
Separate confluence rank from probability. Add all-in cost diagnostics and a
fail-closed entry gate when estimates are unavailable.
Acceptance: accepted/rejected candidate logs and replay results, including negative
results and missed opportunities, with fixed-lot risk feasibility.

### M4 — Execution and risk state machine under mocks

Persist intents/reservations, handle partial/ambiguous responses, reconcile
restarts/manual interventions, enforce positions+pendings+in-flight caps and
monotonic SL updates. Preserve local protections and bounded emergency semantics.
Acceptance: concurrency, cancellation/fill races, no duplicate retry, volume/grid,
budget, daily reset/cash flow, news, kill-switch and disconnect fault-injection tests.
No new live order authority before these pass.

### M5 — Full replay and robustness

Replay the same decision engine with explicit fills, costs, delays and broker
constraints. Test signal/event parity and separately assess fill-model error.
Use campaign-aware resampling, chronological untouched periods, ablation and
parameter sensitivity. Record failed runs rather than tuning them away.
Acceptance: reproducible reports and diagnosis; no profitability assertion if
results are negative or the history is inadequate.

### M6 — Optional ML

Candidate-conditioned labels, purged chronological training/calibration/test,
versioned feature schema, drift and shadow challenger. No internet AI dependency
in emergency management and no automatic artifact promotion.
Acceptance: sufficient data, calibration evidence and incremental net benefit
over the frozen rules-only comparator; otherwise retain ML off.

### M7 — Shadow, then explicit demo promotion

At least a week of appropriate shadow coverage, then the proposed multi-week demo
qualification. Change the running main only after implementation gates and an
explicit chosen risk policy; preserve positions or wait flat for incompatible
state changes. Real-money activation remains outside this review and is not
provided as a launch option.

## 6. Baseline test command and limits

Executed successfully:

    .\.venv-audit\Scripts\python.exe -B -m pytest test_gold_retest_shadow.py test_gold_m1_quality.py test_gold_staged_s30.py test_gold_candle_input_health.py test_gold_consensus_demo_broker.py test_gold_feed_reliability.py test_gold_scalp_setups.py test_gold_tick_entry_research.py test_gold_entry_structure_features.py test_gold_exit_state.py test_gold_broker_clock.py test_gold_main_event_calendar.py -q

Result: 109 passed, 5 subtests passed in 29.71 s.

No new MQL5 code was compiled, no new backtest run was presented, no ML model was
trained and no 24-hour/weekly/monthly acceptance gate was claimed. Existing
native compile/test scripts were inspected only, not launched against MT5.

## 7. Current main-bot launch command

This launches the existing demo main, NOT the proposed SMC engine.
Do not run another instance if one is already active.

    cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
    & ".\.venv-audit\Scripts\python.exe" -u -B ".\run_gold_consensus_bot.py" --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0

Dashboard: http://127.0.0.1:8765
Ctrl+C stops the main and attempts to close its managed demo positions under the
current CLOSE_POSITIONS_ON_STOP setting.

