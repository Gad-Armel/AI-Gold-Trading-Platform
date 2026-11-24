# XAUUSD SMC setup engine: implemented scope

## Status

The project now contains three deterministic setup detectors, a shared captured-input
replay path, a main-bot observation integration and an optional entry-only veto.
This is a tested strategy research component, not a completed replacement platform,
trained AI or a proven profitable system. It does not complete all milestones in
the master specification. Advisor 1 remains protected and unchanged.

The default is **observe**. New setups cannot originate an order, reverse a signal,
change lots, alter stops or force an exit. No running process was restarted during
this implementation. The existing process does not load these source changes
until its next controlled restart.

## Implemented strategies

### A. Sweep and reclaim with confirmed micro-structure break

Use a swing that was confirmed before the sweep. Price must penetrate its level
by a minimum ATR-normalized distance and close back inside. Within the configured
TTL, a later completed M1 must break the previously confirmed opposite swing,
with directional displacement and sufficient relative tick activity. A reclaim
alone, a wick alone or a forming candle cannot confirm a candidate.

The proposed stop lies beyond the entire observed sweep/reversal extreme plus
an ATR buffer. A failed reclaim or already-consumed trigger is not a fresh signal.

### B. Order-block continuation

A completed M5 displacement breaks a confirmed swing with sufficient relative
tick activity. The last opposite-direction candle in a bounded preceding search
window supplies the full-range zone. Its anchor time is separate from the later
BOS/zone confirmation time.

Only a first observed M1 retest after zone confirmation can qualify. It must
intersect the zone, close back beyond its near edge in the continuation direction
and meet relative-activity criteria. Prior touches, far-edge invalidation, age
expiry or missing M1 lifecycle coverage reject the candidate. Confirmed M5
direction must align. No order is backdated to the origin candle.

### C. Support/resistance flip and retest

A displacement and activity-confirmed break of an already-confirmed swing creates
a flipped level. A subsequent completed M1 must retest and hold it with a
directional body and sufficient activity. The first touch is consumed; subsequent
touches do not create repeated confirmations. TTL and invalidation apply.

## Common safeguards and limits

- All detectors are mirrored for BUY and SELL; the system does not hedge them.
- Structural calculations use completed M1/M5/M15/H1 input, with explicit clocks,
  freshness, finite prices/activity, duplicate and continuity checks.
- Swings use strict two-sided extrema and become known only after right-side
  confirmation. Tied extrema are not interpreted as confirmed pivots.
- ATR and volume baselines exclude the candidate bar. Relative volume is a
  trailing broker tick-activity ratio, not a 20-day seasonal baseline or aggressor
  volume. Absorption, exchange delta and institutional intent are not inferred.
- Contrary confirmed higher-timeframe structure rejects candidate eligibility.
  This is a simple BOS-direction context, not a fully validated ADX/regime model.
- The opposing level is the nearest known swing beyond the executable price,
  limited by configurable age. It is contextual room, not a fixed broker TP.
- No opposing level, inadequate stop/spread separation, missing cost assumptions
  or insufficient cost-relative room prevents eligibility.
- Estimated friction = current spread + explicitly configured round-trip
  commission price equivalent + round-trip slippage price allowance. These
  assumptions must come from the actual broker/account and measured execution.
  Do not enter money amounts or points where price distances are required.
- Neither favorable geometry nor cost feasibility is positive expected value.
  Expected value and calibrated probability are deliberately None.
- Confirmed structures/candidates are cached by completed OHLC **and tick-volume**
  fingerprints. Quotes and cost feasibility are re-evaluated, not cached as fills.
- Errors are isolated from the existing main's protective-position management.

The defaults (two-bar swing confirmation, displacement 0.6 ATR, RVOL 1.2,
three-M1 TTL, six-spread stop separation and 0.2 cost/R limit) define an exploratory
candidate, not optimized or profitability-validated settings. Inspect SmcConfig
for all parameters. Override its fields via SCALP_SMC_CONFIG in the isolated main
settings, without editing Advisor 1 dependencies.

Strict continuity can make the engine unavailable around broker maintenance,
weekends or incomplete history. Such periods are not filled synthetically or
treated as a validated market regime. This can reduce observation coverage.

## Main integration and optional filter

decision.smc_strategy records context, model, stable setup identity, anchor/known
times, proposed stop, opposing level, activity ratio, costs and rejection reasons.
The forward recorder records candidate transitions; accepted order context also
includes the report. Rejected candidates are not discarded from these reports.

--smc-policy observe leaves the previous entry decision unchanged.
--smc-policy filter only adds a veto after existing position/exit management.
The default unknown commission/slippage values make filter startup fail explicitly
before the runtime lock/MT5 connection. Do not set them to zero merely to make it run.

When configured, the filter requires a fresh cost-feasible candidate matching an
already-authorized direction. It cannot make an unauthorized decision tradable.
Existing M1 3/5/6 stages, fixed 0.01 lots, same-direction profitable additions,
five-position cap, news, broker checks and exits remain in force.

Consequently a counter-direction retest may conflict with the existing consecutive
M1 entry rule. The filter does not bypass that rule. A standalone SMC replacement
would be a separate strategy promotion after full replay and prospective validation.
Its proposed setup SL is journalled but is NOT substituted for the active advisor
SL. Existing broker checks continue to evaluate the actual requested order.

No new percentage sizing, partial exits, fixed TP, automatic training, daily-loss
policy change, native EA deployment or real-money enablement is introduced here.

## Read-only capture and replay

Capture the connected demo's bars and quote, without any order API:

    .\.venv-audit\Scripts\python.exe -B tools/audit_gold_smc.py --capture-demo --output data/research/smc_20261019/live_audit.json

Replay the saved input/config through the same strategy implementation:

    .\.venv-audit\Scripts\python.exe -B tools/audit_gold_smc.py --input data/research/smc_20261019/live_audit.json --output data/research/smc_20261019/replay_audit.json

This is candidate-input replay, NOT a fill simulator or profitability backtest.
The initial live capture attempt was refused because the quote was stale or
inconsistent with the configured clock. The existing main status independently
reported DATA_UNAVAILABLE / no live XAUUSD price. No live parity or performance
result is claimed. The capture clock policy was not automatically changed.

## Launch the existing main, with new observations

Do not launch another instance while the main already runs.

    cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
    & ".\.venv-audit\Scripts\python.exe" -u -B ".\run_gold_consensus_bot.py" --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --smc-policy observe

Dashboard: http://127.0.0.1:8765
Ctrl+C attempts to close managed demo positions under the current stop setting.

## Validation before promotion

Synthetic tests cover all three entry models, causal swing confirmation, long/short
symmetry, first touches, invalidations, TTL, future-data independence, volume/cache
revisions, input quality, unknown costs, expired opposing levels, veto-only policy,
startup refusal and preservation of exit-management ordering. The audit uses the
same detector implementation as the main, with no trading side effects.

Next required evidence: fresh broker capture, frozen multi-session candidate
history, full bid/ask/delay/cost exit-policy replay, comparison with the existing
staged strategy and prospective demo validation. A passing unit suite is not
evidence that any setup has positive net expectancy.

Validation result: **141 tests and 5 subtests passed**, including 22 dedicated SMC
tests. Seven touched Python files pass syntax parsing. All 18 protected Advisor 1
files retain their baseline hashes. Evidence: data/research/smc_20261019/tests.xml
and advisor1_integrity.json.

The command-line audit was also exercised twice on an explicitly synthetic
fixture, producing one eligible flip/retest candidate and identical reports.
Files synthetic_capture.json and synthetic_replay*.json are test evidence only;
their fee/slippage numbers and prices are fabricated fixture inputs, not broker
measurements or historical results. No orders were sent.
