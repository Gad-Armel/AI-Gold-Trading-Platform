# HFT implementation task plan and handoff

## Mission and honest completion definition

Build a separate exchange-connected, event-driven trading system that may
eventually be integrated with the main bot's orchestration, without claiming
that a faster timer or an MT5 scalping mode is HFT. Completion means the chosen
venue's live market-data and order-entry contracts are implemented, observed
end-to-end performance is measured, risk and recovery controls pass, and the
system completes a staged rollout under its approved operating limits.

**This is a work plan, not an assertion that the current bot is HFT or ready for
live orders.** User direction is to use free options where practical and to
defer live API connection until the rest of the system is ready. An exchange,
instrument, broker/member, execution API, market-data entitlements, deployment
location, and operating limits have not yet been selected. Do not select or
infer these on the user's behalf. Without them, venue-specific integration and
valid latency/fill testing cannot be completed.

## Current repository baseline

- The main Python entry point is `run_gold_consensus_bot.py`. It obtains
  snapshots through `services/market_data/scalping_snapshot.py`, targets a
  250 ms loop (`config/gold_consensus_settings.py`), and sends demo orders
  through `services/execution/gold_consensus_demo_broker.py`.
- The Python bot uses MT5 XAUUSD top-of-book quotes; it does not have a
  centralized exchange order book or venue queue position. Its faster
  timeframe options change signal windows, not the underlying execution path.
- The native EA is `mql5/Experts/GoldScalpAI/GoldScalpAI.mq5`; its
  `OrderSendAsync` path does not remove terminal, broker, network, or matching
  latency. Its local tick-processing timing is not end-to-end execution timing.
- Existing limits that must remain until the user explicitly changes them:
  demo/paper by default, at most three positions account-wide, exactly 0.01 lot
  per new position, and no real-account execution. Do not run the Python bot
  and EA concurrently on the same account.
- `run_gold_advisor.py` (Gold Advisor 1) and its transitive local dependencies
  are protected. Never edit them. A parallel adapter/service is required if
  integration needs adjacent functionality.
- `services/hft/paper_replay.py` implements an offline, paper-only event replay
  for observed MT5 quote archives. `run_gold_consensus_bot.py` now exposes it
  through `--hft-paper-replay`, before any MT5 initialization. It models neither
  centralized depth nor queue-based fills and has no order-sending path.
- The `biquote` PyPI package is a free, unauthenticated MT5-backed quote feed
  with REST/SignalR interfaces according to its published docs. It is not an
  exchange order-entry API or full-depth exchange feed. It was not installed or
  connected. Its possible role is a later read-only feed adapter only.
- Focused replay tests cover event ordering, gaps, spread, assumed costs,
  slippage, and paper fills. They use small synthetic fixtures solely for code
  invariants; no empirical run on an observed archive is claimed.
- There are pre-existing unrelated worktree changes. Preserve them; inspect
  only task-scoped diffs and do not clean/revert other files.

## Current implementation status

| Area | Status | What is and is not included |
|---|---|---|
| Offline quote replay | Implemented | Uses observed MT5 quote archives, bid/ask crossing, configurable assumed latency/cost/slippage, spread and hourly caps, gap/stale handling; reports price units only. |
| Main-bot entry point | Implemented | `run_gold_consensus_bot.py --hft-paper-replay <archive>` and `run_gold_ai.py --hft-paper-replay <archive>` enter offline replay without selecting shadow/demo; trading flags are rejected in this mode. |
| Runtime data feed | Not connected | No API calls or external streaming sessions were started. Biquote may be assessed later as a read-only feed adapter. |
| Exchange order book | Not available | Current feed is MT5 XAUUSD top-of-book; no depth, venue sequence numbers, or queue position. |
| Order management/execution | Not implemented | Replay simulates one position and a delayed quote fill; it has no exchange orders, cancel/replace, acknowledgements, partial fills, or live execution path. |
| Main bot's MT5 demo mode | Preserved | Existing demo/scalping behavior and safety policies are unchanged. |
| Empirical strategy evidence | Not produced | No observed archive was collected or replayed; test fixtures only verify code behavior. |

## Stop conditions and invariants

1. If no exchange and supported API are selected, stop before venue adapter,
   live streaming, or order-entry implementation. Continue only on isolated
   replay, requirements, and simulation work that cannot be mistaken for live
   HFT.
2. Never substitute broker CFD quotes for an exchange order book, fabricate
   market data, infer queue position from top-of-book, or call a backtest/live
   run profitable without evidence.
3. Keep all order pathways paper-only until venue, account, legal/operational
   permissions, limits, and rollout are explicitly approved. Add independent
   environment/config gates; default every new live switch off.
4. Preserve all known user risk limits and Advisor 1 protections. Do not
   increase position count, lot size, leverage, or risk budget as a shortcut
   to greater trade frequency.
5. Any latency report must state precisely which intervals it measures:
   exchange timestamp, local receive time, decision, send, acknowledgement,
   exchange acknowledgement/fill, and clock uncertainty. Local handler time is
   not a substitute for end-to-end latency.

## Work breakdown

### Phase 0 — Select venue and approve operating requirements (BLOCKED for true HFT)

**Inputs required from user/venue provider**

- Exchange and exact instrument/contract, including expiry/roll treatment.
- Authorized broker/member, order-entry protocol and API documentation/version.
- Market-data product (top-of-book versus full depth), entitlements, symbol IDs,
  timestamp semantics, sequence numbers, and recovery/replay mechanism.
- Account environment (simulator/paper first), supported order types, cancel
  semantics, rate limits, throttles, session calendar, tick/lot sizes, fees,
  rebates, margin, and applicable permissions.
- Target host/region and whether co-location is available; clock-sync method and
  timestamp instrumentation supported by the venue.
- Approved maximum positions, order/message rate, gross/net exposure, loss
  limits, and manual/automatic kill procedures. These do not override existing
  limits until explicitly reviewed and approved.

**Tasks**

- Verify primary API claims against the selected provider's current official
  documentation; identify test/sandbox endpoints and terms.
- Produce a venue-specific requirements matrix, message-flow diagram, failure
  matrix, and explicit go/no-go list.
- Decide whether this is a completely separate service or a main-bot
  coordinator with a segregated execution process. Do not merge exchange
  execution into the MT5 connector.

**Exit criteria**

- All inputs above are recorded without secrets in a local configuration
  contract, each protocol choice is documented, and the user approves the
  scope. Never request or write API secrets into code, docs, or chat.

### Phase 1 — Data and execution boundary design

**Status:** partial. The offline replay accepts validated timestamped bid/ask
quotes and fails closed on ordering problems and prolonged gaps. Venue-specific
sequence numbers, depth snapshots/deltas, live event queues, back-pressure,
reconnect/resynchronization, and full event contracts remain unimplemented.

- Define typed, venue-neutral event interfaces for instrument definitions,
  trades, quotes, order-book snapshots/deltas, order acknowledgements, fills,
  cancels, rejects, and connection state.
- Preserve venue sequence numbers and timestamps; reject stale, duplicated,
  out-of-order, crossed, malformed, and sequence-gapped events. On a gap, mark
  the book invalid and resynchronize from an authoritative snapshot.
- Separate market-data ingestion, strategy, risk, order management, persistence,
  and operator controls. Avoid blocking network/disk/UI work in the
  latency-sensitive event handler.
- Define single-writer ownership, deterministic event ordering, bounded queues,
  back-pressure behavior, and explicit overload/drop alarms. Never silently
  drop order or fill events.
- Create an adapter contract and paper/simulator adapter before any live-capable
  implementation. Keep the existing Python/MT5 path intact.
- Define a versioned configuration format with validation, safe defaults,
  startup account/instrument checks, and explicit execution-mode display.

**Exit criteria**

- Interface and state-transition tests cover normal operation, invalid book,
  sequence gap/resync, reconnect, queue overflow, duplicate messages, and
  shutdown. Design review confirms no path can submit a live order by default.

### Phase 2 — Venue simulator and event replay

**Status:** basic offline paper replay implemented; venue-faithful simulator
remains blocked on selected venue rules and appropriate data.

- Extend or replace the standalone paper replay with a venue-faithful simulator
  only after Phase 0 provides the matching rules and message behavior.
- Store captured, authorized, unmodified market events with source, venue,
  contract, UTC/timebase, data-quality status, and checksums; use no synthetic
  market data to claim performance.
- Replay deterministically at source time and configurable speeds; support
  pause, seek, repeat, and event-by-event reproduction.
- Model order acknowledgement, cancel/replace, partial fills, rejects, queue
  priority if the data can support it, fee schedules, latency distributions,
  market impact uncertainty, session transitions, and outages.
- Label assumptions distinctly from observed data. If depth/queue data is
  unavailable, report queue/fill results as unknown rather than inventing them.
- Track gross and net results by trade, session, regime, and scenario; include
  costs and mark-to-market, drawdown, exposure, order-to-fill rate, and
  cancellation/message rates. Prevent look-ahead and survivorship leakage.

**Exit criteria**

- Repeatable deterministic replay and hand-computable fixtures pass. A
  chronologically separated out-of-sample evaluation includes all fees and
  adverse execution scenarios. No profitability claim without a separately
  reviewed empirical report.

### Phase 3 — Strategy research (paper/shadow only)

**Status:** not validated. The replay uses a deliberately simple midpoint
momentum signal as plumbing only; it is not promoted, tuned, or evidence of
edge.

- State a falsifiable market-microstructure hypothesis and define what observed
  data would disprove it before fitting parameters.
- Implement one small candidate strategy in an isolated module. Keep decisions
  explainable and make all thresholds configurable but bounded/validated.
- Use only supported book/trade fields. Do not treat broker tick volume or
  single-feed quote changes as global order flow.
- Compare against simple baselines and no-trade; account for fees, spread,
  latency, queue priority, adverse selection, impact, and rejected orders.
- Use chronological train/validation/test splits, walk-forward checks,
  sensitivity analysis, multiple-testing controls, and a frozen test set.
- Shadow live market data without order submission; reconcile strategy signals
  and simulated orders against the recorded feed and clock uncertainty.

**Exit criteria**

- Reproducible tests, causal-data audit, independently reviewable frozen
  evaluation, and stable performance under realistic costs and latency
  perturbations. Passing this phase is not live-trading authorization.

### Phase 4 — Risk engine and kill controls

**Status:** limited replay guards implemented (spread, gap, one open simulated
position, hourly entry cap, assumed fees/slippage). Exchange pre-trade risk,
account-currency conversion, durable OMS, operator controls, and fault
injection remain unimplemented.

- Enforce pre-trade checks for instrument/session status, fresh synchronized
  market data, book validity, position and order limits, exposure, buying power,
  price collars, order size, per-second message budgets, loss limits, and
  duplicate intent prevention.
- Add independent hard kill switch (operator and programmatic) that stops new
  orders, cancels eligible resting orders, reconciles uncertain requests, and
  follows approved position handling. Report partial failure explicitly.
- Make order intents idempotent and persist request IDs/state transitions so a
  restart cannot blindly duplicate uncertain entries.
- Test exchange rejects, timeouts, disconnect during send/cancel, partial fills,
  stale data, clock drift, process crash/restart, persistent-store failure,
  limit breach, and kill-switch failure.
- Add alarms for no market data, sequence gap, unexpected position, unknown
  order state, sustained latency breach, abnormal message rate, and loss limit.

**Exit criteria**

- Fault-injection suite demonstrates fail-closed behavior and deterministic
  reconciliation. Risk checks are independently reviewed and cannot be bypassed
  by a strategy signal or config parsing error.

### Phase 5 — Performance engineering and operational readiness

**Status:** not done. Replay handler timing is diagnostic for local code only;
no live, venue, or network latency has been measured.

- Measure distributions (not only averages) of market-data transit, event
  handling, decision, order send, acknowledgement, fill, and clock offset.
- Profile under representative peak market-message rates and recovery bursts.
  Bound allocations, serialization, locks, logging, garbage collection, and
  persistence on the hot path based on evidence, not assumed optimization.
- Define latency SLOs from selected venue/provider measurements; report p50/p95/
  p99/max, sample counts, dropped messages, clock uncertainty, and test hardware.
- Test host/network failure, provider maintenance, certificate rotation,
  credentials expiration, disk-full, CPU/memory saturation, restart and
  failover. Define supported operating system and deployment reproducibility.
- Add structured audit logs and a read-only dashboard. Keep UI, network control
  plane, and manual intervention out of the strategy's unbounded execution path.

**Exit criteria**

- Benchmarks are reproducible on the intended host and feed; measured
  end-to-end results meet approved venue-specific targets with uncertainty and
  failure behavior disclosed. No unsupported latency guarantee.

### Phase 6 — Controlled staged rollout (requires separate approval)

**Status:** not started. No live or connected paper endpoint is configured.

1. Unit/integration tests and offline historical replay.
2. Venue simulator with captured actual events.
3. Connected paper/sandbox order entry; reconcile every acknowledgement/fill.
4. Shadow operation using live feed, no orders.
5. Limited canary only if the venue supports it and the user explicitly
   authorizes live trading, legal/operational requirements are met, and all prior
   gates pass.
6. Increase scope only through reviewed change requests and measured evidence;
   maintain immediate rollback and a record of every config/version.

No phase transition is automatic. Do not enable live trading, change account
mode, or raise any user risk limit without explicit authorization.

### Phase 7 — Main-bot integration

**Status:** offline replay mode integrated. Live data/execution coordination,
account locking across venues, dashboards, and rollout gating remain blocked
until the standalone venue-specific system passes acceptance.

- Decide integration only after the standalone service passes prior phases.
- Expose a narrow typed coordinator API for health, approved signal intent,
  risk reservation, order state, and shutdown. Keep venue session and matching
  rules inside the adapter.
- Make current MT5 scalping and exchange execution mutually exclusive by
  account/instrument lock; never let both act on the same exposure.
- Preserve the existing bot's paper/shadow defaults, max-three-position and
  0.01-lot constraints unless the user approves a documented replacement.
- Do not modify Gold Advisor 1 or any protected dependency. Add a parallel
  adapter if its read-only advisory output is relevant.
- Add end-to-end tests for mode selection, credentials unavailable, venue
  unavailable, stale signal, account mismatch, risk rejection, cancellation,
  and clean shutdown. Ensure dashboards clearly identify instrument, venue,
  mode, data freshness, and real-vs-simulated status.

**Exit criteria**

- Integration changes are feature-gated off by default, have full regression
  coverage, preserve existing behavior in MT5 modes, and pass repository
  validation and venue-specific paper acceptance.

### Phase 8 — Documentation, audit, and maintenance

- Document exact setup, supported venue/API versions, permissions, contracts,
  configs, clocks, network requirements, failure recovery, risk controls, and
  kill procedure.
- Maintain a test matrix and runbook with an owner, last verified date, and
  rollback instructions. Never store credentials in the repository.
- Re-test provider API changes, exchange protocol changes, contract rolls,
  session-calendar changes, and dependency updates in paper mode before use.
- Record deviations, known limitations, and data provenance; clearly distinguish
  measured facts, assumptions, and hypotheses.

## Suggested next implementation sequence

1. Complete the remaining venue-independent event/replay and risk work in
   paper-only mode.
2. User supplies and approves Phase 0 venue/API/instrument requirements before
   any venue-specific streaming or execution adapter is built.
3. Implement adapter interfaces plus a deterministic protocol test harness.
   Test fixtures may exercise software invariants but must never be presented
   as market/performance data.
4. Implement the selected venue's paper/simulator adapter and capture pipeline.
5. Validate/replay real authorized venue data; report gaps and cost assumptions.
6. Research a candidate strategy and complete risk, fault-injection, and latency
   gates.
7. Integrate behind an off-by-default feature gate only after standalone
   acceptance; require a separate explicit live authorization for any real
   orders.

## Handoff state

- Main-bot paper replay: `run_gold_consensus_bot.py --hft-paper-replay <NPZ>`.
  Core: `services/hft/paper_replay.py`; wrapper CLI:
  `tools/gold_hft_paper_lab.py`; usage/limitations:
  `docs/research/GOLD_HFT_PAPER_LAB.md`.
- Focused unit file: `tests/test_gold_hft_paper_lab.py` (12 tests passed).
  Main-bot, `run_gold_ai.py`, and standalone-wrapper CLI smoke checks passed
  using a temporary software fixture; fixtures are not market evidence.
- No quote API, exchange API, order-entry adapter, new live order path, or
  existing demo path changes have been implemented. No real tick archive was
  collected or replayed by this task.
- Next action is to assess a free quote adapter only if desired, without
  confusing it for order entry; choose an exchange and order-entry provider
  before any execution adapter. Biquote's MT5-backed quotes are not an exchange
  HFT venue.
