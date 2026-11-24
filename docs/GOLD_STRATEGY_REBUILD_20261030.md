# Main scalper redesign and deployment result

## Result

Engineering work is implemented and tested, but a profitable entry/exit
replacement has **not** been validated. Main analysis and protective exits run
on the approved MT5 USD demo. New entries remain explicitly held after negative
tests. The new trigger is shadow-only; the noise-aware exit remains disabled.
No profitable/HFT execution claim follows from passing unit tests.

## Diagnosis

The account-specific earlier audit grouped 131 closed demo positions: 34 wins,
97 losses, net -56.06 USD including recorded costs. Of those, 69 stop-outs lost
77.11 USD. Three-source allocation produced 77 trades, net -35.62, with 55
stop-outs. A high minute-scale candle score could repeatedly authorize the same
direction without a fresh market event. Multiple agreeing candle scores are
not independent evidence and multiplying positions multiplies correlated risk.

The $1 lock requests a close after a $0.20 pullback at its initial peak, which
can be inside the current spread. That is a plausible noise problem, not proof
that allowing a larger giveback improves outcomes.

## Prepared architecture

1. Three-source context supplies direction and a 1/2/3 exposure ceiling.
2. A pure executable-event detector evaluates completed S5 break/reclaim
   structure, both bid and ask, 3/12-second pressure, spread expansion, observed
   movement versus assumed costs and a structural SL within the $5 risk budget.
   It uses no future bars or fabricated volume/order-book data. Scores are
   heuristics; no trained AI probability is claimed.
3. Each structural event gets a stable identity. The account-bound durable
   ledger reserves an event before order submission, consumes it once, and
   distinguishes reported order acceptance from reconciled broker deals.
   Unknown/timeout outcomes block new requests instead of blindly retrying.
   The ledger is tested but is inactive while the trigger remains shadow-only.
4. An optional noise-aware per-ticket profit lock uses spread-aware giveback
   capped to retain a positive remainder. It never widens a broker SL. Its
   default is unchanged because the matched-entry comparison was unfavorable.
5. The dashboard exposes failed validation and shadow status. Display reset
   remains separate from broker history and risk controls. Inverse stays
   disabled. Advisor1's 18 protected hashes remain unchanged.

## Frozen evaluation

Capture: 73,113 bid/ask ticks plus M1 bars on the approved demo, October 29,
04:05:36–08:05:36 UTC (05:05:36–09:05:36 Africa/Lagos).
Files and SHA-256 hashes are recorded in the reports. Two predeclared profiles,
chronological halves, no parameter optimization, first-tick-after-delay fills,
350 ms modeled latency and .30 assumed additional round-trip cost. Quotes
already include spread. The replay is single-position, not full live source
voting/multiposition/margin/requote parity; boundaries censor open positions.

| Candidate | First half | Second half | Completed trades | Total modeled net |
| --- | ---: | ---: | ---: | ---: |
| One-bar S5 control | -85.94 | -125.28 | 287 | -211.22 |
| Executable-event challenger | -29.15 | -31.60 | 70 | -60.75 |

Lower aggregate loss reflects lower turnover. Challenger net per trade was
about -.868 versus -.736 for control; this is **not** a validated signal-quality
improvement. Both halves lost money after assumed costs.

Matched-entry exit comparison: 62 entries covered by usable quotes, unchanged
initial SL, 180-second horizon and delayed modeled closes. Control -57.86;
noise-aware -58.47; delta -.61 USD equivalent. Challenger improved three,
worsened six and left 53 unchanged. 15-second quoted post-actual-exit movement
averaged -.0282 USD. Excluded: 35 outside/incomplete horizon, 33 quote gaps,
one stale boundary. Other live adaptive/news/flow exits are omitted. These are
counterfactual research outcomes, not actual broker P/L or proof that any exit
is optimal. The earlier audit lacks an embedded fingerprint; this exit tool
therefore reports its identity-verification limitation, although the root's
capture and audit commands explicitly selected the approved terminal.

Artifacts:

- data/research/rethink_capture_20261029/
- data/research/rethink_entry_comparison_20261029.json
- data/research/rethink_noise_comparison_20261029.json
- data/research/exit_review_20261029.json
- data/research/exit_rethink_20261029/independent_exit_review.md

## Validation and operational state

100 focused Python tests passed, plus dashboard polling/render/offline-recovery
tests and runner syntax checks. Tests include future-quote exclusion, stable
event identity, sparse/stale/flat/opposite/costly input rejection, durable
reservation across restart, broker deal reconciliation, unresolved sends,
account mismatch, noise-lock defaults and retained floor, existing execution
and exit regressions. A regression test rejects duplicate candidate-enable
assignments; final live telemetry verified execution_enabled=false and SHADOW_ONLY.
No claim of speed improvement without live distribution
measurements. The optional noise mode does not affect active exits.

The previous provisional cost profile had expired. Renewed the same user-
approved .10 commission/.20 slippage assumptions on the exact fingerprint,
with an added expected-account option that refuses accidental rebinding.
These remain assumptions, not measured maximum costs, and still expire in 24h.

Main was reloaded on C:\Program Files\MetaTrader 5\terminal64.exe. The deliberate
entry hold is data/runtime/gold_entry_research_hold.flag; the visible reason is
data/runtime/gold_strategy_validation.json. It is a validation decision, not
an unexplained frozen program. Do not remove the hold or enable the candidate
and call it validated: no candidate passed. Future work needs a genuinely
unseen forward sample, measured costs, and positive after-cost expectancy with
uncertainty estimates across several regimes. Repeatedly optimizing this same
four-hour sample is not evidence of an edge.

Two-minute live observation (October 30, 00:37:02–00:39:02 Africa/Lagos):
25 samples, same approved demo identity at both ends, no open positions, no
new broker deals and no observation errors. The hold prevented entries in all
samples. Final readback after reload confirmed SHADOW_ONLY, RUNNING analysis
and FAILED_AFTER_COST_REPLAY validation state. This verifies operation and
isolation, not trading performance. Artifacts:
data/research/rethink_shadow_live_20261030/report.json and samples.jsonl.

## Primary research

- https://arxiv.org/abs/1011.6402 — order-flow imbalance in equity order books;
  requires suitable data and does not validate XAUUSD quote-only trading.
- https://arxiv.org/abs/1512.03492 — queue imbalance prediction in Nasdaq stocks;
  genuine queue depth is required. The demo returned no usable live depth.
- https://arxiv.org/abs/1409.2618 — state-dependent execution with order-flow
  imbalance; supports execution-aware design rather than a universal strategy.
- https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py — official
  tick API. Broker clock offset is handled explicitly and logged in capture.

Self-evaluation: correctness backed by boundary tests; risk and data freshness
guards retained; main-only scope; frozen negative results reported; meaningful
limitations stated. A profitable trading objective remains unresolved.
