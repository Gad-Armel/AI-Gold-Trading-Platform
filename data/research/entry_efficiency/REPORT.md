# Main demo bot entry-efficiency investigation â€” October 8, 2026

The entry problem is not solved. No tested challenger provides enough evidence
to claim reliable profitability or to replace the current live entry policy.
The main demo bot remains running; Advisor 1 was not edited.

## Changes deployed

- Corrected the paper account's obsolete $2 emergency stop to the configured
  $5 per position, and made its rolling loss circuit respect the same session
  setting as the main bot. Entry and exit quote freshness are tracked separately.
- Added an observation-only assessment of correlated entries. It checks whether
  existing same-direction exposure has covered dealing noise and whether a new
  completed M5 candle supports another lane. It records its recommendation inside
  each decision, but does not veto trades. A fill earlier in the same cycle is
  included in the following lane's assessment.
- Exposed normalized position opening times for that assessment.
- Reused the fresh per-lane position snapshot for the global capacity check,
  removing three duplicate MT5 position queries per loop. The broker still
  independently rechecks capacity immediately before placing an order.
- Restarted only the main demo process at 11:30:17 UTC. The pre-restart check
  verified a demo account and the existing position's broker SL.

Your existing $5 individual stop, 30-second post-exit analysis pause, continuous
session operation and two-M5-candle weakening confirmation remain configured.
The $5 stop is a planned risk amount: gaps, slippage and trading charges can make
the realized loss larger. The simulator preserves worse gap fills rather than
clipping losses to $5.

## Recorded trades and signal timing

The causal entry audit joined 37 closed trades to observations available before
their entry. This matched subset lost $24.08, with profit factor 0.635. It is not
the complete account/session result. SCALP lost $1.41 on 20 matched trades;
INTRADAY lost $16.18 on eight; SWING lost $6.49 on nine.

Simple risk, candle alignment, trend-efficiency and reward/risk filters did not
consistently improve that subset. Requiring analysis reward/$5 risk >=0.7 would
remove every matched SCALP trade; this restriction was not enabled.

Independent executable-quote markouts also show why a strong score is insufficient.
In the later five-hour record, six sampled SCALP signals >=85/100 averaged -$0.9533
after five minutes, including spread and $0.10 assumed round-trip slippage.
These are price outcomes with fixed holding periods, not actual trade profits.
Samples are small and partly dependent. Evidence scores are heuristic strength,
not calibrated probabilities of winning.

## Correlated-entry challenger

The quote-driven replay creates independent simulated positions and adaptive,
flow and candle-confirmation states. It compares baseline against staged additions.

| Recorded period | Policy | Closed trades | Realized | Floating at end | Profit factor |
|---|---|---:|---:|---:|---:|
| First 125 minutes | Baseline challenger | 7 | $5.72 | -$1.51 | 1.755 |
| First 125 minutes | Staged challenger | 7 | -$0.97 | -$1.51 | 0.923 |
| Later 305 minutes | Baseline challenger | 26 | -$11.20 | -$7.95 | 0.751 |
| Later 305 minutes | Staged challenger | 17 | -$8.61 | -$2.55 | 0.675 |

Staging reduces later exposure but fails to improve profit factor and worsens
the earlier period. Observation mode is therefore retained. This is not an exact
production replay: it omits conscience and SCALP churn controls,
  uses recorded context updates around every 15 seconds, and assumes $10 margin
per position in a $100 paper account. Both periods were already inspected, so
neither is a blind holdout. Sampled quotes can miss intragap stop touches.

## Broader historical research

Downloaded 90,000 closed M1, 30,000 M5 and 15,000 M15 broker bars. After feature
availability checks, the benchmark includes 88,992 M1 observations. Closed-bar
features become available at candle close; orders fill at the following open.
Paths crossing missing minute bars are excluded.

Four predetermined patterns were compared on chronological 60/20/20 segments:
directional candle body, M1/M5 alignment, pullback resumption and closing breakout.
All lost money in the latest segment at both five- and fifteen-minute exits,
including normal and 1.5x spread/slippage stress. For example, directional-body
five-minute entries had PF 0.7182; closing-breakout fifteen-minute entries had
PF 0.8770 at normal costs. These simplified fixed-exit tests do not reproduce
production exits, news or exact windowed Advisor 1 calculations.

A gradient-boosted return filter was then trained on the earliest 60%, with
labels ending before validation begins. Four forecast thresholds were assessed
only on the middle 20%. None met both the predeclared minimum 100 validation
trades and PF >=1.1. No threshold was promoted and no learned filter was enabled.
The latest segment was not used to rescue a failed validation result.

Repeated historical searches can overfit even when attractive simulations appear;
the [backtest-overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
supports treating these comparisons as research rather than profit guarantees.
Production money-risk checks use broker calculations in account currency, as
described by [MetaQuotes](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py).

## Validation and remaining work

163 relevant tests passed, including position-risk parity, adverse gap fills,
BUY/SELL cost accounting, completed-bar availability, entry coordination,
continuous operation, candle confirmation and the existing broker/exit suites.

The fresh read-only capture ran 11:30:50â€“11:40:52 UTC (41 observations). The bot
remained RUNNING with no advisor errors. One carried position closed for -$1.83;
main total P/L improved $0.50 as its initial floating loss was reduced. This is
not evidence of profitable new entries. Median loop processing was 172 ms,
p95 390 ms, and maximum status lag 0.76 seconds. All three lanes later became
neutral and the bot remained flat. Full evidence is under
`data/monitoring/20261008T113050Z`.

The main bot was restarted again at 11:41:03 UTC to load the tested query
reduction; the pre-restart demo check found zero controlled positions.

Higher precision remains unverified. Further promotion needs a faithful production
replay and new forward evidence after freezing a candidate. Adding trade frequency
or fitting more thresholds to the same losing session does not establish an edge.

Detailed artifacts: `recorded_audit.json`, `recorded_entry_features.csv`,
`signal_markouts.json`, `coordination_replay.json`,
`historical_entry_benchmark.json`, `learned_entry_filter.json`.

## Continued investigation after 11:41 UTC

An exit-only audit tested the original analysis stop against subsequent executable
quotes, excluding paths with quote gaps longer than ten seconds. For the 20 matched
SCALP trades, hypothetical analysis-stop exits worsened net results from -$1.41 to
-$10.08. This does not model changed re-entry opportunities and uses journal
requested prices as approximate fills. It does not support tightening the
emergency stop; the main bot's $5 stop remains configured.

The replay now has an optional production-controls profile. It reconstructs
micro-flow from quote history, runs quote-only protection before entry analysis,
uses the production conscience and SCALP churn/cooldown functions, and tracks its
own fills. It still uses sampled historical source decisions and lacks exact
warm-start state, so it is not a faithful reproduction of every original order.
Both profiles include current neutral-thesis adaptive exits.

| Period | Production-controls replay | Realized | Floating | Profit factor |
|---|---|---:|---:|---:|
| Earlier | Baseline | $6.60 | $0.81 | 1.762 |
| Earlier | Staged | -$0.68 | $0.81 | 0.950 |
| Later | Baseline | -$16.06 | -$8.04 | 0.675 |
| Later | Staged | -$8.26 | -$2.64 | 0.684 |

This remains mixed evidence. Staging is still observation-only.

A separate two-direction return model was trained using only the earliest 60%
of the historical data. Unlike the initial trend filter, it estimates BUY and
SELL outcomes independently. At a $0.50 forecast threshold and $0.25 directional
forecast gap, its five-minute validation comparison produced 92 trades:
normal-cost net $52.75/PF 1.2967; 1.5x cost net $26.31/PF 1.1354. It failed the
predeclared minimum 100-trade requirement. The threshold was frozen for prospective
observation, not approved for execution. The artifact's `live_approved` is false.
The latest historical segment was not used to rescue failed validation.

The first observer started 11:47:14 UTC and recorded only WAIT signals, with no
hypothetical positions. It was explicitly replaced at 11:57:51 UTC to correct
execution timing: forecast timestamps now reflect completed analysis, and any
hypothetical entry uses a fresh broker quote obtained afterward. Its old output
is marked replaced, not left appearing live. The replacement runs for twenty
minutes and sends no orders. It uses one hypothetical .01-lot position, a $5
stop and five-minute time exit; its approximate three-minute re-entry pause
belongs to this isolated experiment, not the main bot's 30-second pause.

Prospective output: `prospective/20261008T115751Z`. Independent main-bot evidence
capture started 11:58:26 UTC under `data/monitoring/20261008T115826Z` for twenty
minutes. Results are pending; WAIT observations alone cannot establish precision.

Paper quote handling was further corrected so entry-price inactivity can block
new entries while fresh broker ticks still permit protective exits. The main
demo execution path is unaffected. Older continuous-SCALP tests were corrected
to verify the current $5 risk, 30-second cooldown and bounded broker clock jitter;
legacy flow-primary tests explicitly select their legacy configuration.
The expanded relevant suite now passes 184 tests.

Additional artifacts: `analysis_stop_audit.json`,
`coordination_production_controls.json`, `bidirectional_entry_filter.json`,
`bidirectional_5m_observation.json` and the matching research-only model.

## Further evidence and deployed speed improvement â€” 12:19 UTC

The frozen two-direction candidate was subsequently tested on the later historical
segment without retraining or changing thresholds. It failed: 62 trades, -$41.12,
PF 0.6543 at normal costs; -$45.60/PF 0.6261 under 1.5x costs. Its earlier
validation daily-cluster bootstrap 95% interval for mean profit was
[-$0.4505, $1.7223], also including losses. The model remains unapproved and its
manifest now explicitly records the later failure. This additional falsification
assessment does not erase the original sample-size failure. The period is model
out-of-sample but was already inspected with other hypotheses.

A fixed rolling challenger trained only on the preceding 30,000 bars and updated
every 5,000 bars, with a full label purge before each prediction block. It also
failed: 439 non-overlapping walk-forward trades lost $236.74, PF 0.7552 at normal
costs. No rolling models were exported or enabled.

The replacement prospective observer completed at 12:17:52 UTC. It recorded 21
minute forecasts, all WAIT, zero hypothetical trades and zero hypothetical P/L.
This cannot establish accuracy or profitability. Its final error field was null;
not every transient error was retained in a historical error log.

The main-bot evidence capture completed at 12:18:29 UTC after 20.06 minutes and
81 observations. Two closes lost $6.51 realized; total main P/L changed -$2.84
after accounting for starting floating losses. No advisor-error samples were
recorded. The trading edge remains unproven.

Completed-candle exit statistics are now cached in the main bot. Each lookup still
checks candle completion and clock freshness. Any completed OHLC correction,
newly completed bar, broker-offset change or stale-clock boundary invalidates the
cache; callers receive independent copies. Forming-bar prices do not affect
completed-bar statistics. Seven new cache tests and the expanded relevant suite
passed (191 tests before deployment).

A paired read-only benchmark on current broker candles measured all three context
calculations at median 53.077 ms fresh versus 14.245 ms cached (73.16% less time
for that component), with exact output parity. The main was restarted at
12:07:09 UTC after verifying the demo account and its one protected position;
adaptive state restored successfully. The ongoing live capture showed median
loop processing 172 ms before versus 125 ms afterward, with p95 344 versus
266 ms. This comparison is observational and affected by changing CPU load and
market conditions; the isolated paired benchmark is stronger attribution evidence.
It is a processing-speed benefit, not proof of better trade predictions.

A separate replay applied M1 exit context to INTRADAY/SWING while preserving entry
signals, confirmation durations and $5 stops. Both adaptive/conscience and
quote-protection context were changed consistently. The earlier period was
unchanged. In the later period, unstaged realized results improved from -$16.06
to -$11.77 (PF 0.675 to 0.732), with the same -$8.04 terminal floating result.
Staged results improved from -$8.26 to -$7.42 (PF 0.684 to 0.716). These results
remain negative and are not blind validation; live secondary exit frames have
not been changed. An intermediate adaptive-only run is separately labeled.

Historical executable bid/ask coverage was verified with a bounded one-hour
MT5 probe for October 7, 11:00â€“12:00 UTC: 25,341 usable ticks, median spread
$0.32, maximum quote gap 25.323 seconds. This provides a basis for testing
tick/candle features and actual spread paths rather than relying solely on
minute OHLC and approximate asks. Historical ticks are quote observations,
not aggressor identities or an order book.

New artifacts: `exit_context_latency.json`, `frozen_candidate_assessment.json`,
`rolling_candidate_assessment.json`, `coordination_fast_secondary_exits.json`,
`tick_probe/manifest.json`, and the live capture's `latency_comparison.json`.

## October 8 update: executable ticks and official calendar

The read-only MT5 export completed for September 8 through October 7 UTC:
10,555,739 usable bid/ask observations, with no unavailable source days.
The causal tick/candle study retained 293,885 complete examples, using whole-day
chronological splits and 176,135 training examples. Tick features become known
at second end; execution assumes 100 ms latency, actual bid/ask paths, $0.05
slippage per side, a $5 planned stop, 180-second exits and 30-second re-entry
pauses. Adverse stop gaps are charged at the observed quote rather than clipped.
This research simulator is not a reproduction of the main bot's adaptive exits.

All four validation thresholds failed. At thresholds 0, 0.25, 0.5 and 1.0,
base validation results were respectively 434 trades / -$185.37 / PF 0.688;
240 / -$128.49 / 0.651; 154 / -$73.24 / 0.704; and
56 / -$42.34 / 0.579. Stressed costs also lost money. No threshold was selected,
the later holdout was not used to rescue the candidate, and no model was
exported or connected to trading. More data and faster features have not yet
established a positive trading edge. Artifacts: `historical_ticks/manifest.json`
and `tick_entry_assessment.json`.

The live news context omitted today's scheduled initial claims release.
A main-only supplement now reads the actual
[New York Fed calendar](https://www.newyorkfed.org/research/calendars/i-oct26.html),
with Eastern daylight/standard time conversion. The source verifies the
schedule; MEDIUM is our watch classification, not an official impact rating.
It respects the existing setting that medium-impact events do not block entries.
Wrong-month pages, unknown formats and expired caches cannot invent events.
Refresh runs in the background; the shared calendar and standalone Advisor 1
were not changed.

The relevant suite passed 214 tests. Deployment at 12:37:52 UTC verified the
demo account and zero owned positions before replacing only the main process.
At 12:38:12 UTC the main reported RUNNING, no advisor errors, and initial
claims as verified, active and non-blocking. The existing $5 per-position
planned risk and continuous-run settings remain in place. Calendar completeness
improves context, but is not evidence of improved profitability.

A fresh read-only 30-minute observation began at 12:38:25 UTC in
`data/monitoring/20261008T123825Z`; results are pending.

Calibration diagnostics isolate a generalization failure in the tick challenger.
For forecasts between $0.50 and $1.00, realized mean labels were +$3.06 on
training examples but -$0.445 on validation examples; validation predicted mean
was +$0.680. Even forecasts above $2.00 averaged -$0.036 on validation.
These are overlapping three-minute outcome labels, not independent trades or
portfolio returns. They demonstrate why raising this model's confidence threshold
is not supported. The diagnostic used only training and validation days; the
later holdout remains untouched. No production score is treated as a calibrated
probability of profit, and the tick challenger remains disabled.

## Earlier M1 entries and tick agreement

Four fixed rules tested the user's faster-SCALP hypothesis without fitting a
model: completed-candle majority, early M1 direction, and each with matching
6-second and 30-second executable quote movement. Whole-day validation results
were respectively 1,021 trades / -$444.72 / PF 0.619;
1,160 / -$541.52 / 0.597; 896 / -$395.05 / 0.613; and
1,007 / -$488.50 / 0.592. All failed the existing acceptance gate and lost
more under stressed costs. Early M1 alone increased entries and losses;
the simple tick agreement filter did not improve profit per trade.

This compares approximate full-history EMA directions with $5 tick-path stops,
180-second time exits and 30-second pauses. It omits production strength scores,
news filters and adaptive exits, so these figures are not main-bot backtest
returns. Validation dates were previously inspected; this is exploratory
evidence, not blind confirmation. Final holdout days remain untouched and no
rule was enabled. Artifact: `tick_alignment_audit.json`.

At 12:41:55 UTC the main was still RUNNING with zero positions and unchanged
realized P/L since this observation began. All lanes reported no usable
directional evidence at the configured 15/100 floor. No new trade result can
yet be attributed to the calendar deployment.

## Processing-stage measurements and cross-market reuse

Main-only stage timing was added to identify wall-clock delays without changing
decision order or cadence. The first 120-second capture sampled 220 unique
cycles (`loop_profiles/20261008T124535Z`). Median processing was 140 ms, p95
641 ms, maximum 1,453 ms. The slowest cycle spent 1,266 ms in source polling
and candle preparation. Other spikes appeared in exit-context preparation and
cross-market calculations, so a single component cannot explain all stalls.
These initial measurements used the Windows monotonic clock's coarse resolution;
the deployed stage measurements now use the high-resolution performance clock.

The cross-market collector recomputed completed-candle transmission statistics
on every loop. It now reuses these statistics only when all relevant completed
time/close observations are unchanged. Instrument identity, quote freshness and
completed-bar age are checked on every call. Historical corrections and new
completed bars invalidate the cache; forming-bar changes do not. Returned
results are independent copies. Standalone Advisor 1 does not use this collector
and was not edited.

A paired frozen-broker benchmark alternated fresh and cached calculations:
50 samples each, identical outputs, median 24.711 ms fresh versus 9.426 ms
cached (61.86% less component processing). Live quote-age checks were patched
only inside this isolated timing benchmark; separate tests verify stale quotes
and stale bars still invalidate usable context. Artifact:
`cross_market_cache_latency.json`.

The expanded relevant suite passed 230 tests. The cache and high-resolution
timings were deployed at 12:49:21 UTC after demo-account verification and
confirmation of zero owned positions. At 12:49:42 UTC the main was RUNNING,
stderr was empty, and no advisor errors were reported. A second 120-second
read-only stage capture is in progress. This is a measured component speed
improvement, not evidence of better trade precision or profitability.

The post-deployment 120-second profile completed with 215 unique cycles
(`loop_profiles/20261008T124931Z`). Cross-market median wall time was 17.750 ms;
whole-loop median was 125 ms versus 140 ms in the preceding capture. However,
p95 processing was 687 ms versus 641 ms and maximum 1,641 ms versus 1,453 ms.
Thus the observed median improved, but tail delays remain unresolved. The paired
component benchmark provides better attribution than these sequential windows.
Four transient status-read failures occurred; sampling may miss cycles.
Source/candle preparation, tick refresh, snapshot retrieval and context/macro
processing each contributed to different slow cycles. Further optimization must
preserve quote protection and use measurements rather than assuming one cause.

At 12:50:11 UTC, the ongoing broader live capture covered 11.78 minutes with
zero new trades, no main P/L change, and no advisor-error samples. It cannot
validate entry accuracy while no directional setup is authorized.

## Actual entry-delay audit and readiness reporting

`entry_delay_audit.json` matched 35 closed entries to preceding observations:
16 SCALP, 9 INTRADAY and 10 SWING. After excluding left-censored signal runs,
median observed signal age was 34.56 / 65.38 / 50.11 seconds respectively.
Median price travel between the first observed unoccupied directional signal
and actual entry was +$0.15 / -$0.20 / -$0.47 in trade direction. Positive means
the entry came at a worse price; negative means a better price. These small,
selected samples do not establish that delays cause losses. Runs include valid
confirmation/cooldown/cost waits and 15-second sampling cannot measure precise
onset or order latency. No qualifying opposing strong source was present in
these matched pre-entry samples; other times and rejected entries are excluded.

Four entries had preceding samples labeled timing-ready. Their recorded
`last_execution` showed an absolute-spread COST_BLOCK for INTRADAY and analysis
RISK_REWARD_BLOCKs for three SCALP cases (reported ratios 0.69, 0.60, 0.69).
They were explicit execution rejections, not evidence that the loop ignored an
accepted order. The main now sets reported timing readiness false and appends
the actual rejection reason after an unsuccessful current attempt. It still
reevaluates normally next cycle. This changes reporting, not entry permission,
stop sizing, cooldowns or order execution. The 89 relevant checks passed.

There is a separate deterministic configuration mismatch: Advisor 1 SCALP
uses a 0.45 ATR first target and 0.65 ATR analysis stop, yielding 0.6923 nominal
analysis reward/risk, below the main's 0.70 minimum. The selected main SCALP
target is tp1. Rounding and price movement between analysis and execution can
occasionally permit entry, but consistent exact rebasing exposes this mismatch.
This analysis ratio differs from the actual $5 broker stop and adaptive exits.
Using the already-produced tp2 would yield 1.1538 nominal analysis reward/risk,
but changing the reference would also relax the spread-to-target gate and open
more trades. Existing candle-majority tick validation lost money, so no target
switch or lowered guard has been enabled merely to produce activity. This
remains an unresolved entry-policy limitation requiring supported validation.

Readiness reporting was deployed at 12:57:04 UTC, after the restart helper
verified one owned demo position with an existing broker SL. At 12:57:17 UTC
the main was RUNNING, adaptive state reported RESTORED, and stderr was empty.
The observation at 12:57:12 UTC contained SCALP SELL ticket 58821566589,
entry 4116.61, broker SL 4121.60 (approximately $4.99 planned risk for this
0.01-lot contract), floating -$1.40. The trade is open and no profitability
conclusion follows from this interim observation. The existing entry policy
opened it; no research candidate or target-selection change was enabled.

## Fixed advisory-duration exits on the actual entries

A read-only export at 13:00:28 UTC retrieved 216,656 executable bid/ask ticks
from today's UTC midnight. An exit-only diagnostic held each recorded filled
entry for its original advisory horizon (SCALP 5 minutes, INTRADAY 30 minutes,
SWING 120 minutes), retaining a $5 planned stop and charging $0.05 exit slippage.
Actual first adverse quote fills charge stop gaps in full. Four numerical tests
verify gap losses, ask-side SELL stops, pre-entry causality and incomplete
horizons; the research/parity group passed 15 checks.

Of 52 closed entries found in recorded histories, 48 had complete paths with
maximum quote gaps no greater than 10 seconds; two incomplete horizons and two
larger-gap paths were excluded. All-period actual versus hypothetical net
outcomes were SCALP 27 trades -$13.75 versus -$15.70; INTRADAY 12 trades
-$20.63 versus -$31.87; SWING 9 trades -$6.49 versus +$1.61. Overall actual
-$40.87 versus hypothetical -$45.96. Later-period SCALP worsened from -$12.97
to -$17.40 and INTRADAY from -$14.45 to -$25.32. These findings do not support
replacing current exits with simple longer holds to fix the losses.

The nine SWING labels are insufficient evidence for promotion, and their
hypothetical holds can overlap positions whose later entries might not exist
under changed capacity or re-entry timing. These sums are not realizable
portfolio backtest returns. Samples use actually closed trades, exclude open
positions, mix deployed policies and reuse previously inspected chronological
periods. Tick records may omit broker-server events; hypothetical fees and
financing are omitted. No exit policy was changed. Artifact:
`actual_entry_horizons/20261008T130028Z/report.json`.

At 13:01:28 UTC the ongoing live capture covered 23.05 minutes with 92
observations, no closed trades and floating main change -$2.74. Maximum
observed equity drawdown was $4.23; no advisor-error samples were recorded.
The open trade and interim loss do not establish the result of the revised
reporting or the processing cache.

## New closed trades and staged-entry comparison

The 12:38:25-13:08:29 UTC capture completed after 30.08 minutes and 120
observations. All three same-direction entries closed at a combined realized
loss of $14.97 (zero wins, three losses). Maximum observed equity drawdown
was $15.16. The bot remained running after the individual stops, with no
advisor-error samples; this verifies continued operation, not entry quality.

The previously defined staged-entry rule was compared on this newer capture
with independent paper positions and production conscience/quote-protection/
micro-flow/churn controls. Unstaged replay: three closes, -$15.31 realized,
zero terminal floating, maximum drawdown $18.32. Staged replay: one close,
-$5.09 realized, zero terminal floating, maximum drawdown $6.29. Both lost;
this episode supports reducing correlated additions, not a profitable signal
edge. The actual result differs from replay because of sampled contexts,
execution assumptions and state reconstruction. Sixteen quotes used stale
contexts and were skipped. The policy remains observation-only pending further
evaluation of continuous SCALP access and the earlier period's lost upside.
Artifact: `prospective_coordination_123825_interim.json` (the captured replay
window happened to include all three closes despite the interim filename).
The first launch was rejected by automatic approval review timeout; its one
authorized read-only retry completed successfully.

The main's candle-fingerprint preparation now bypasses repeated normalization
only for finite numeric candles with unique ordered timestamps. Other inputs
use canonical Advisor 1 cleanup. Signal computation, completed-bar selection,
quote rebasing and Advisor 1 standalone code are unchanged. Two added tests
cover malformed/unsorted inputs, duplicate times and completed-bar rollover.
All 236 relevant checks passed. A paired alternating benchmark of 50 samples
each preserved complete signal outputs: median canonical 32.448 ms versus
validated fast path 26.260 ms (19.07% less component time). Artifact:
`main_candle_signature_latency.json`.

The fingerprint optimization was deployed at 13:09:38 UTC after verifying a
demo account with zero owned positions. A fresh read-only 60-minute capture
began at 13:09:01 UTC (`data/monitoring/20261008T130901Z`), extending the
overall observation span toward ten hours. Its results are pending.

## SCALP-priority allocation evaluated and deployed

The allocation variant exempts SCALP from this additional gate, preserving its
normal signal/quote/cost/capacity/risk checks. INTRADAY and SWING same-direction
additions wait until existing positions have profit above twice dealing spread
and a new completed M5 candle confirms the direction. First independent setups
and opposite-direction setups remain eligible. This is allocation control,
not an altered Advisor 1 forecast or a proven positive trading edge.

The fixed comparison across three periods produced:

| Capture | Unstaged realized / floating | SCALP-priority staged realized / floating | Unstaged / staged maximum drawdown |
|---|---:|---:|---:|
| 04:02-06:07 UTC | +$6.60 / +$0.81 | -$0.68 / +$0.81 | $8.54 / $12.79 |
| 06:08-11:13 UTC | -$16.06 / -$8.04 | -$1.19 / -$2.64 | $34.09 / $17.98 |
| 12:38-13:08 UTC | -$15.31 / $0.00 | -$5.09 / $0.00 | $18.32 / $6.29 |

SCALP entry counts were unchanged at 7, 16 and 1 respectively; zero SCALP
candidate quote checks were vetoed by the allocation gate. Secondary additions
were reduced in later periods. Counts of blocked candidate quote checks are
repeated quote observations before final simulated order checks, not independent
signals or attainable trades. Changed secondary exits can still affect shared
cooldown timing. The earlier period lost upside and had higher drawdown; the
two later periods lost substantially less. All periods were inspected before
deployment, so these are exploratory comparisons rather than blind confirmation.
Mixed recorded source policies, sampled contexts, initial state differences,
assumed margin/slippage and missing fees limit attribution.

The variant was frozen at 13:13:20 UTC, with a prospective boundary at
13:14:20 UTC. Research artifact: `coordination_scalp_priority_assessment.json`;
definition hashes: `coordination_scalp_priority_frozen.json`. That frozen record
states the approval state at freezing time. A separate deployment record marks
main-demo risk allocation enabled, with positive edge explicitly unproven.

All 238 relevant checks passed, including tests that SCALP access remains
available while losing peers exist, other order authority is unchanged, and
secondary additions still require profit/fresh follow-through. Deployment at
13:17:46 UTC verified a connected demo account and two owned positions with
broker SLs. At 13:18:15 UTC the bot was RUNNING, adaptive state RESTORED,
mode SCALP_PRIORITY, with no advisor errors and empty stderr. The original
positions were preserved; $5 planned risk per position, three-position cap,
30-second analysis pauses and standalone Advisor 1 remain unchanged.

`coordination_scalp_priority_baseline.json` records the first captured state
after activation. Its carried INTRADAY/SWING entries predate the allocation
change; their subsequent returns cannot demonstrate improved entry selection.
New entries and new closed-trade outcomes must be reported separately before
any precision or profitability claim.

## Structure-feature challenger and live outcome attribution

An offline feature challenger added completed M1/M5/M15 candle geometry to the
tick/candle model: prior 20-bar extrema, price distance versus the fixed $5 stop,
wick fractions, two distinct completed candle bodies, sweeps, three-bar gaps,
broker tick-volume intraday averages and range/ATR. These are causal price
heuristics, not verified institutional order flow. Four tests check future-data
independence, M5 availability only after completion, prior-extrema sweep logic
and two-candle succession. The combined research group passed 13 checks.

The challenger retained all 293,885 examples and the same chronological days,
model parameters, threshold grid and acceptance gate. Source hashes and the
before-fit definition are in `structure_entry_hypothesis.json`. Validation at
thresholds 0 / 0.25 / 0.5 / 1.0 produced respectively 515 / 299 / 195 / 84
non-overlapping trades, net -$295.84 / -$175.80 / -$103.01 / -$55.95, PF
0.572 / 0.597 / 0.631 / 0.610. Stressed costs also lost money. None qualified;
no threshold, model export or execution promotion occurred, and this study did
not evaluate its later holdout. It does not support adding structure complexity
to the live predictor. Validation dates were already inspected, so this is
exploratory rejection evidence, not blind confirmation. Artifact:
`structure_tick_entry_assessment.json`.

`tools/audit_gold_policy_outcomes.py` now separates actually observed new and
carried entries by normalized UTC fill time. At 13:27:05 UTC, 36 captured
post-activation samples contained zero new entries, one carried INTRADAY close
for +$1.12 and one carried SWING position floating +$3.14. Neither carried
outcome proves the new allocation rule improves entry selection. No SCALP
allocation veto, unprotected observed position or advisor-error sample occurred.
Repeated SWING allocation denials occurred while that lane was occupied; they
are not evidence of prevented executable additions. Live artifact:
`data/monitoring/20261008T130901Z/policy_outcomes.json`.

## API candle age corrected while reports are cached

Source inspection confirmed that the external candle adapter uses a separate
OANDA v20 feed (with Twelve Data as the other configured adapter), rather than
silently substituting MT5. Both candle advisors apply the same trend algorithm;
agreement is feed consistency, not established statistical independence. New
main status provenance labels the provider and feature family explicitly.

A concrete freshness defect was found: consensus checked the API's numeric
`source_bar_age_seconds` measured when its report was built, without advancing
that underlying candle age while the report remained in memory. A report
generated 60 seconds ago could pass its 90-second envelope limit while a candle
already 150 seconds old at generation incorrectly passed the 180-second bar
limit. Its true candle age would be 210 seconds.

Consensus now derives current bar age from the actual source bar timestamp.
Legacy reports without that timestamp advance their recorded bar age by elapsed
report time. Invalid or materially future bar timestamps cannot vote, and the
provider's cached report is not mutated. Main freshness displays and source
diagnostics use the effective current age; report freshness and candle freshness
are shown separately. The existing freshness limits and source-specific main
entry policy remain unchanged; fresh primary SCALP evidence is still evaluated.
Standalone Advisor 1 was not edited.

Four new regression tests cover a fresh envelope hiding a stale candle, legacy
cached age progression, immutable cached reports and invalid/future timestamps.
The expanded suite initially exposed two older feed-test assumptions: exits
were tested against the entry-age ceiling, and a fixture returned artificially
future request endpoints while expecting past-only incremental overlap. Those
fixtures now exercise the existing exit-age ceiling and isolate deduplication
from separately tested clock jitter; no exit or tick-history production policy
was weakened. The expanded relevant suite passed 257 tests, followed by 25
focused checks after adding explicit `bar_fresh` diagnostics.

Deployment at 13:35:20 UTC verified one owned demo position with broker SL;
at 13:36:10 UTC the main was RUNNING, exit state RESTORED, with no advisor
errors and empty stderr. Its unchanged API report was 41.975 seconds old while
the underlying candle correctly showed 69.721 seconds of age, derived from its
timestamp. The API provider reported OANDA v20 XAU/USD OHLC.

At 13:35:08 UTC the attribution audit had observed two post-allocation entries:
one new SWING close lost $5.12, and a second new SWING position floated +$2.88.
The stop was planned near $5; the actual stop fill lost more during price movement,
as the executable-quote research explicitly permits. The two carried closes
earned +$2.78 and are kept separate. No observed position lacked a broker SL,
no SCALP allocation denial or advisor-error sample occurred, and the new entries
remain too few to establish improved profitability. This result predates the
API-age correction and cannot measure that correction's effect.

Captured runtime verification reused the exact report generated at
13:35:27.745926 UTC: candle age advanced from 38.702 to 53.766 to 68.612 to
83.779 seconds across four observations between 13:35:38 and 13:36:23 UTC.
This confirms that cached-report candle age now advances in live operation.

### Horizon validity and paired replay correction — 13:48 UTC

Deployed at 13:41:56 UTC: expired or missing horizon validity now makes that
advisor's horizon unusable for main entry voting and levels. Previously expiry
was recorded in consensus notes but could still be counted by the main horizon
policy. Unrelated fresh horizons remain eligible. Contributor diagnostics now
include valid_until and validity_reason. Standalone Advisor 1 is unchanged.
The relevant production suite passed 260 tests; restart preserved one owned
position with a broker SL, and main status remained RUNNING with restored state.

The growing-capture replay had a separate research input race: each variant read
observations at a different time. The interim artifact
coordination_scalp_priority_future_interim.json is superseded and must not support
performance conclusions. The replay now freezes complete observation lines once,
reads quotes once, and passes the same bounded immutable window to both variants.
Two regression tests cover later appends and partial trailing writes; 19 focused
research checks passed. This changes the replay engine hash, not the frozen
allocation policy helper. No production restart was needed for the research fix.

Corrected artifact: coordination_scalp_priority_future_fixed_window.json.
Window 13:09:01–13:46:55 UTC, 151 observations, 4,153 identical quotes per run;
quote SHA256 9f6a6fe1dcaac35ecadbd738ddeafcf3aa203773bffd9f2c1a646590c13c8489.
Baseline: six closes +$3.61, floating -$3.75, maximum drawdown $10.18.
Staged SCALP-priority: five closes +$2.95, floating -$3.75, maximum drawdown
$10.18. Thus this later comparison shows $0.66 less realized profit with staging,
not an improvement. SCALP had one entry in each and no allocation denials;
264 repeated INTRADAY candidate checks were blocked. This is a sampled-context
challenger comparison, not an exact production replay or independent holdout;
it also includes data preceding allocation deployment and subsequent source fixes.

Live attribution through 13:47:25 UTC: six observed post-allocation entry tickets;
four closed for +$0.69 (one -$5.12 stop and three wins totaling +$5.81), two open
floating -$4.10, combined -$3.41. The two carried entries closed +$2.78 separately.
No sampled position lacked a broker SL and no advisor-error sample occurred.
These sparse outcomes do not establish a positive edge or isolate the later
freshness fixes. Main remained RUNNING at 13:47:40 UTC and monitoring continues.

### Entry-time execution evidence — deployed 13:50:22 UTC

Main horizon order journals now include the decision-time executable bid/ask,
quote age and broker epoch, source contributors with validity, candle confirmation,
momentum blocks, allocation decision and analysed levels/cost ratios. The broker's
reported execution price and volume are stored separately from the requested price;
missing broker fields remain null. This addresses attribution uncertainty caused
by the monitoring capture's 15-second sampling. It does not change predictions,
entry permission, requests, position sizing, stops or exit behavior.

Two tests verify preservation of requested versus different reported prices and
that missing reported prices are not invented. The focused broker/session/paper/
allocation suite passed 52 tests. Restart at 13:50:22 UTC preserved two broker-
protected owned positions; status at 13:50:41 remained RUNNING and stderr was empty.
No post-deployment order had yet occurred at that check, so live journal validation
remains pending. Monitoring handle 84557 was confirmed running by direct polling.

### Short-term direction versus execution cost — cached tick audit

Read-only tool tools/audit_gold_entry_reaction.py produced entry_reaction.json
inside actual_entry_horizons/20261008T130028Z using that existing frozen tick
capture and its selected actual entries. It marks direction at 30/60/180 seconds
separately using signed mid-price movement and executable bid/ask versus the
original actual fill. Missing endpoint coverage and internal gaps over ten seconds
are excluded separately per endpoint. Three tests passed for sell-side ask usage,
future-quote invariance and incomplete/gapped coverage.

At 60 seconds, SCALP had 27 covered entries: 10 favorable mid-price movements,
seven positive executable marks, median signed mid move -$0.645 and median
executable mark -$1.07 at the configured 0.01-lot gold contract. Across all lanes,
17/51 had favorable mid movement and 13/51 positive executable marks; medians
were -$0.585 and -$1.01 respectively. Therefore costs compound a directional
problem in this inspected sample; spread alone does not explain the losses.

Among the 13 eventual SCALP winners, only six had favorable mid movement at
60 seconds, increasing to nine at 180 seconds. An automatic early loss exit or
simple reversal therefore cannot be justified from these outcome-selected labels.
The analysis does not fit/promote a strategy, does not simulate stop survival or
changed re-entry, and is not chronological out-of-sample validation. Marks can
occur after actual exits; selected closed trades and mixed deployed policies
limit generalization. The newer live allocation period is not in this cached
13:00 tick capture and is monitored separately.

Live audit validation at 13:53:20 UTC: main RUNNING, two positions, zero advisor
errors. New SCALP ticket 58822930407 requested BUY 4131.24 and broker reported
4131.21 at 0.01 lots (quote age 0.284s); SWING ticket 58822937269 requested SELL
4130.65 and reported 4130.70 at 0.01 lots (quote age 0.227s). Both journals include
three source contributors and execution context. These two favorable reported
price differences verify the distinction is captured; they do not establish
systematic favorable slippage or a profitable prediction model.

### Broker deal corroboration — 13:54:41 UTC

Read-only tools/audit_gold_entry_execution.py cross-checks returned deal IDs with
captured MT5 history and saves data/monitoring/20261008T130901Z/entry_execution_audit.json.
Both post-instrumentation entries matched deal prices exactly: SCALP BUY 4131.21
and SWING SELL 4130.70. Reported volume was 0.01 in each. Mean adverse requested-
to-deal price displacement was -0.04 (negative means favorable); median quote age
was 0.255s and entry deal commission/swap/fee totaled zero. No journal deal was
missing from this capture. Closing charges, other fills and partial-fill totals
are outside this narrow check. Two favorable fills cannot establish execution
quality generally or predictive profitability; no strategy or risk change follows.

### Independent currency-feature challenger — rejected 13:58 UTC

Tested completed EURUSD and USDJPY M1 returns over 1/5/15 bars and a volatility-
scaled five-bar return, with explicit availability flags. The design was recorded
before collection/fitting in currency_challenger/hypothesis.json; capture metadata
and CSV hashes are in currency_challenger/capture.json. Instrument currency
identities and current quote ages (EURUSD 0.593s, USDJPY 0.252s) verified the
configured broker clock convention. Historical offset constancy is an assumption.
33,117 EURUSD bars and 33,112 USDJPY bars were returned for Sept 7–Oct 8.

The same 293,885 gold examples, 176,135 training examples, 15 training UTC days,
five middle days and six final days were retained. Missing currency features are
zero plus an availability flag, without dropping/reassigning days. Availability
is recorded per day. All five validation days had EURUSD coverage 100%; feature
continuity and source gaps are explicitly checked. Three causal tests passed:
bar-close availability, future-change invariance and gap exclusion.

No model/hyperparameter, label, threshold-grid or acceptance-gate change was made.
All validation candidates failed, recorded in currency_tick_entry_assessment.json:

| Predicted threshold | Base trades | Base net | Base PF | Stressed trades | Stressed net | Stressed PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 481 | -279.16 | 0.5821 | 483 | -397.37 | 0.4639 |
| 0.25 | 252 | -144.57 | 0.6145 | 255 | -221.52 | 0.4885 |
| 0.5 | 144 | -87.68 | 0.6090 | 147 | -133.16 | 0.4885 |
| 1 | 58 | -23.52 | 0.7378 | 59 | -46.07 | 0.5725 |

The final dates were not performance-evaluated, no model was exported, and main
execution was unchanged. The middle dates have been inspected in earlier studies;
this is exploratory chronological validation, not an independent new holdout.
Neither more indicators nor confidence thresholds produced a demonstrated edge.
Main remained RUNNING at 13:58:19 UTC; live capture handle 84557 remained active.

Reference for API history limits and timezone handling:
https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py
The API documentation describes UTC bar times; this broker's measured offset
convention is handled explicitly and recorded rather than assumed from the docs.

### Operating requirements audit — 14:01 UTC

Authoritative process inspection found exactly one main Python process (35112),
launched with --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0,
and the existing standalone Advisor 1 process (32920), --interval-seconds 60.
Both launch syntaxes were verified with --help without starting another process.
Standalone Advisor 1 files were left as found; their pre-existing git differences
are not changes made by this improvement work.

Runtime config confirms fixed 0.01 lot, three positions total, one per lane under
adaptive exits, $5 maximum planned risk, session-loss-stop disabled, 30-second
post-exit analysis and SCALP_PRIORITY allocation. All live lane decision thresholds
were 15/100; SCALP entry_mode was ADVISOR1_PRIMARY. Both observed open positions
had broker SL. These checks establish configured operation and observed protection,
not perpetual uptime or guaranteed maximum realized losses during gaps.

A captured-history/journal audit (reentry_pause_audit.json in the current monitor
folder) matched ten post-allocation entries with a preceding same-lane close. The
shortest acknowledgement-to-prior-close interval was 30.693 seconds; the latest
SCALP re-entry waited 33.427 seconds. Longer waits reflect other eligibility
conditions and need not be execution delays. This uses bounded captured history
and journal acknowledgement timestamps, not exact broker fill timestamps.

Verified commands for future starts from the project directory (both are already
running; these were documented, not launched again):

```powershell
python -u -B run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0
```

Advisor 1, matching its current refresh setting:

```powershell
python -u -B run_gold_advisor.py --interval-seconds 60
```

The advisor also supports --interval-seconds 15 (its default) and --once. No change
to the existing separate advisor process was made. Main unlimited duration is
controlled by --max-minutes 0; Ctrl+C deliberately stops it and invokes its
configured shutdown position handling.

### Observed score and payoff audit — through 14:03:12 UTC

observed_score_outcomes.json joins accepted main order journals to captured closed
histories by broker position ticket: 68 matched Oct 8 closed trades. No new cutoff
was fitted and no live policy changed. Scores are heuristic strengths, not proven
win probabilities. Historical source/entry modes and deployed settings differ,
market exposures overlap, and open/unmatched positions are excluded.

| Entry score | All-lane closes | Wins | Reported net | SCALP closes | SCALP net |
| --- | ---: | ---: | ---: | ---: | ---: |
| 15–<40 | 0 | 0 | 0.00 | 0 | 0.00 |
| 40–<60 | 13 | 9 | +11.30 | 6 | +0.35 |
| 60–<75 | 41 | 18 | -57.47 | 18 | -4.18 |
| 75–<85 | 13 | 4 | -27.17 | 8 | -10.58 |
| 85–100 | 1 | 0 | -5.05 | 1 | -5.05 |

The 68 closes netted -$78.39: 31 wins, 37 losses, mean win $2.03, mean loss
$3.8195, profit factor 0.4453. Given those observed payoffs, the arithmetic
break-even win fraction is about 65.3%, versus the observed 45.6%. This illustrates
both direction and payoff imbalance; it does not estimate an independent future
win probability. Existing tighter-stop and fixed-hold studies did not establish
a better realizable portfolio, so these numbers do not justify forcing a new
exit rule. Strong-score observations are especially sparse, and apparent gains
in the lower band must not be selected as a new profitable strategy from this
same inspected sample. Confidence calibration remains unproven.

### Combined regression and late-session check — 14:06 UTC

All 270 combined relevant checks passed after the last production journal change
and offline tools were added (including replay-window, reaction and currency
causality tests). The 56.44-minute capture through 14:05:27 UTC contained 225
observations, no advisor-error samples, maximum status lag 3.83s, median loop
110ms and p95 469ms. These live latency summaries are observational across
changing market conditions and do not prove profit or a causal speed gain.

Whole-capture closed outcomes were eight wins/five losses, +$15.15 gains versus
-$21.18 losses (net -$6.03, PF 0.715), maximum observed account equity drawdown
$11.13. Separately, the post-allocation attribution audit later reported ten
closed new entries totaling -$7.69, with no remaining new positions at that
sample. The two carried entries closed +$2.78. Different time cutoffs explain
why whole-capture totals include other earlier closes and do not equal the
post-deployment attribution subtotal. No improvement in predictive profitability
has been demonstrated. Monitoring handle 84557 remained running; main was not
stopped when it became flat.

### Completed monitoring window and paired replay — 14:10 UTC

Monitor handle 84557 completed normally with exit code zero. Final capture ended
14:09:13 UTC after 60.197 minutes. It contains 241 JSON observations, of which
240 have usable account/status/candle data for the summary/replay. One observation
at 13:26:20 had a transient Windows PermissionError reading the status file;
this is a capture read error, distinct from the zero advisor-error samples.

Final whole-capture net -$6.03, eight wins/five losses, PF 0.715, maximum observed
account equity drawdown $11.13. Post-allocation new-entry attribution separately:
ten closed new trades -$7.69, no remaining positions; carried closes +$2.78.
Maximum sampled positions two, no observed unprotected owned ticket. Four repeated
unoccupied-directional INTRADAY allocation-denial samples were observed, with no
SCALP allocation denials. These are sampled checks, not four independent lost
opportunities. The bot remained active after the capture ended.

Completed paired artifact: coordination_scalp_priority_completed_window.json.
Both variants used 240 identical complete observations and 6,588 quotes; quote
SHA256 159ec0a775d068a0937f5d40d236c79b0d525c253328af39f5078706be353366.
Baseline: 12 closes -$5.30, floating zero, PF 0.742, maximum drawdown $11.68.
Staged SCALP-priority: 11 closes -$5.96, floating zero, PF 0.710, same drawdown
$11.68. SCALP entries four in both; SWING seven in both; INTRADAY one versus zero.
The allocation rule thus cost $0.66 in this window and did not improve drawdown;
earlier windows showed mixed results. It remains a demo exposure rule, not a
validated profitable strategy. The same replay limitations, historical/source-
policy changes and absence of warm-start positions apply.

monitoring_coverage.json inventories six capture folders: first 04:02:08 UTC,
last 14:09:13 UTC, span 10.118 hours, merged recorded intervals 9.178 hours.
Between-capture gaps and within-capture sampling mean this is not an uninterrupted
ten-hour quote record. All requested prediction/efficiency aspirations are not
yet achieved: engineering checks pass and measured component costs improved,
but no positive after-cost predictive edge has been demonstrated.

### Prospective unchanged-configuration capture — 14:14 UTC

A separate read-only 120-minute capture started at 14:12:11 UTC in
 data/monitoring/20261008T141211Z; handle 52839 was confirmed running by direct poll.
The main and standalone Advisor 1 processes were not restarted or altered.

prospective_main_20261008T141211Z.json freezes 72 Python source/configuration files
at 14:13:46.909857 UTC and sets the evaluation cutoff to 14:14:46.909857 UTC,
sixty seconds later. Earlier capture rows are excluded from prospective claims.
The plan records runtime settings and initial snapshot time, separates carried
positions by actual opening UTC, and requires any production/source change to
interrupt this frozen-version evaluation rather than pool different versions.
Two hours is an operational observation; it cannot establish a statistically
reliable positive edge by itself. Future replay comparisons must restrict both
observations and quotes to the same completed post-cutoff window.

The read-only outcome audit now accepts --start-utc without relabeling the actual
deployment time. Two tests passed, including boundary-time entry classification,
carried versus new fill attribution, unchanged default deployment attribution,
and no premature samples. File handles are explicitly closed and those tests
also passed with ResourceWarning treated as an error. No production policy change
or new forecast model was deployed for this evaluation.

Prospective replay cutoff verification at 14:16 UTC: the paired replay now accepts
--start-utc and excludes both observations before that time and observations whose
underlying status snapshot predates it. It requires an explicit timezone offset.
A new regression test covers stale status in a later observation, exact boundary
inclusion and rejection of naive cutoff times; 22 focused replay/paper/allocation/
outcome checks passed. This is a research-tool change outside the 72 frozen main
source/config files, which all remained unchanged. No production restart occurred.

Actual capture validation selected six complete observations from 14:14:56 through
14:16:11 UTC and excluded eleven earlier rows. Metadata and hashes are saved in
prospective_capture_validation.json in the new capture folder. This validates
window selection only; no performance conclusion or new strategy was drawn.
Handle 52839 was again confirmed running by direct polling.

### Volatility-pause ablation in progress — 14:20 UTC

The frozen prospective main remains unchanged. A separate research-only replay
flag temporarily disables SCALP_BLOCK_VOLATILITY_EXPANSION within that isolated
Python process, using a scoped settings patch restored after each capture. It
does not edit config files, connect to order execution, or change the running main.

Two replay jobs were launched on completed 04:02, 06:08 and 13:09 captures: default
guard control (handle 40036) and allow-expansion challenger (71400). Both allocation
variants are retained in each, and both use frozen observations/quote windows.
Results will compare realized net, drawdown and SCALP entries with matching window
hashes. More entries alone is not improvement. This ablation is exploratory on
previously inspected data and cannot by itself authorize a profitable-edge claim
or a change to the frozen prospective version. All three process handles, including
live prospective capture 52839, were confirmed running by direct polling.

### Prospective volatility-guard comparison frozen — 14:23:16 UTC

Before the historical guard-ablation jobs produced results, a separate paper-only
comparison was frozen in prospective_volatility_ablation_20261008.json. Its future
cutoff is 14:24:16.768553 UTC. It records the main's 72 source hashes and current
replay engine hash, keeps staged SCALP-priority allocation fixed, and compares
volatility-pause on versus off on identical completed post-cutoff inputs.

Primary reporting is total marked P/L and maximum drawdown, with entry counts,
realized and floating results separate. Hash/version mismatches invalidate the
comparison. No threshold fitting, production-policy change or profitable-edge
claim is authorized by a small two-hour paper sample. This adds future evidence
without retuning the running main. At 14:23:12 the earlier main prospective cohort
had 34 captured samples and no new entries or advisor errors; absence of entries
is not evidence of profitability. The historical jobs remain live by direct poll.

### Volatility-pause ablation completed — 14:25 UTC

Both historical jobs completed normally. Observation metadata and quote hashes
match exactly across guarded and unguarded runs in all three captures (7,843,
28,917 and 6,588 quotes). volatility_guard_comparison.json records both allocation
variants. For deployed staged SCALP-priority allocation:

| Capture | Guarded marked P/L | Expansion allowed marked P/L | Guarded max DD | Allowed max DD | SCALP entries guarded/allowed |
| --- | ---: | ---: | ---: | ---: | ---: |
| 04:02 | +0.13 | -4.07 | 12.79 | 16.46 | 7 / 8 |
| 06:08 | -3.83 | -2.63 | 17.98 | 16.20 | 16 / 16 |
| 13:09 | -5.96 | -11.04 | 11.68 | 15.74 | 4 / 5 |

Marked P/L includes terminal floating value. Unstaged results likewise worsened
by $4.20 and $5.08 in the first/last windows and improved $1.78 in the middle.
More entries therefore did not consistently improve efficiency. No production
change was made; the volatility pause remains enabled. Existing default control
outcomes also reproduced the earlier baseline artifacts. This is exploratory
sampled-context paper evidence, not proof of future risk reduction or positive edge.

Freeze metadata correction: the historical challenger artifact's file timestamp
is 14:22:53 UTC, before the prospective plan's 14:23:16 freeze. It had not been
inspected when the future comparison was frozen, but the earlier statement that
results were not yet available was inaccurate. The plan retains its original
rules and cutoff plus an explicit audit clarification. No comparison parameter
or future cutoff changed; future-data scoring still starts at 14:24:16 UTC.
