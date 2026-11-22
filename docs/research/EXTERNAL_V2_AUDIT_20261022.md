# External v2 proposals: audit and integration

## Reviewed material

Read the supplied `xau_sim2.py`, `XAU_RegimeScalper_AI_v2.mq5`, and all three
pasted proposals. They are design material, not authoritative instructions
to install a second executor or change the user's account/risk constraints.
Original downloads remain untouched. The EA was not compiled, installed or
attached to MT5. No claim of MQL5 compilation is made.

The proposals disagree: APE targets 80–85% acceptance; PLCE targets 15–20%.
Neither ratio demonstrates profitable expectancy. Changing the denominator
or excluding deferred/blocked signals can improve the displayed ratio
without improving trades. No frequency feedback loop forces either target.
Claims of tuned October 2026 thresholds and quoted vendor performance lack
supporting broker data and are not adopted as facts.

## Implemented adaptations

1. Explicit `MICRO` timeframe selection tries S1, S5, S15, S30 in order using
   existing entry checks, without fabricating candles or weakening freshness.
   The selected entry period is pinned while positions remain open. AUTO's
   existing S5/S15/S30 behavior remains unchanged. MICRO may still wait when
   no candidate qualifies; no strategy can promise continuous valid entries.
2. Unique-setup funnel separates evaluation cycles, directional candidates,
   local blocks, eligibility, request attempts, failures/unconfirmed execution
   and reported DONE. Eligible/queued requests are not counted as fills.
   It is a rolling 200-setup per-process view, not a lifetime broker ledger.
   Confirmed fill rate stays unavailable until separately reconciled.
3. Graded structural-plus-micro diagnostics combine observed sweep/gap,
   micro-flow ignition, fast candle quality and HTF alignment. They expose
   FULL/REDUCED/DEFER/NO_SETUP research tiers, not calibrated probabilities.
   No fresh order-block or exchange-volume delta is invented. Missing
   structural preconditions cannot be overridden just by a high score.
4. Fixed 0.01 lot is retained. A suggested 0.5 multiplier means 0.005 lot,
   unavailable at a 0.01 minimum: it is explicitly marked unrepresentable,
   not silently rounded up to full risk. Graded tiers do not place orders.
5. Bounded counterfactual trackers label both attempted and unattempted
   available directional setups, using subsequent executable-side quotes,
   350 ms modeled entry latency, 60-second horizon, 1.5R analytic upper barrier,
   structural lower barrier and 0.30 price-unit modeled round-trip cost.
   Stops gap at the observed quote, not the desired stop. The analytic upper
   barrier is NOT a fixed broker TP. Loop sampling misses intraloop paths;
   these correlated research labels are not live adaptive-exit returns.
   No online model is trained, hot-loaded or promoted on them.
6. Dashboard shows funnel and graded diagnostics with explicit NO ORDERS
   labels. Advisor1, fixed lot, four-position cap, mandatory SL, dynamic exits
   and the user's disabled session-loss/cost-veto settings remain unchanged.
7. Isolated v2 simulator runner restores shared `xau_sim.P` even on failure,
   avoids the supplied pooled IID t-statistic, and distinguishes raw counts,
   logged decisions, queued/accepted decisions, closed simulated trades and
   unresolved labels. The original simulator's other limitations remain.

## Findings not copied into live execution

### Supplied simulator

- `X.P.update(P)` leaks globals between reused runs without our wrapper.
- Raw counts are incremented before directional merging; merged triggers can
  disappear from the decision log. Dedup also changes the denominator.
- `acc` means queued, not filled; capacity/spread expiry and remaining pending
  orders need separate reporting. No fills must be inferred from acceptance.
- Stop stretching also moves the theoretical TP farther away. This is not
  evidence that a nearby liquidity target or expected edge increased.
- Fixed fractional lots in this project make its variable-risk downsizing
  incompatible. Shrinking position size cannot turn negative per-unit
  expectancy into positive per-unit expectancy.
- Synthetic OHLC with ideal stop fills, no real execution latency, realized
  drawdown only, and fixed-barrier virtual labels is not broker validation.
- Label completion and model updates are causal in the supplied loop, but
  overlapping labels and virtual/real exit differences still matter. An
  uncalibrated logistic output is not a reliable probability of profit.

### Supplied EA

- No demo-only guard; nongold symbols only warn. Defaults use percentage risk
  and two positions, unlike the required 0.01/four-position demo profile.
- `OpenTrade` still retries with `withStops=false` after invalid stops. Failed
  protection/close can leave naked risk. We do not import that fallback.
- PLACED and DONE_PARTIAL are treated as completed successes, and uncertain
  timeout/disconnect outcomes can be blindly retried. No such retry change.
- Position identifiers/order tickets are used as selectable position tickets
  in recovery/close paths. Fixed-lot `realRisk` is still nominal riskMoney,
  not the actual monetary SL risk.
- Opening ranges can be cached invalid with incomplete coverage and consumed
  at signal detection before cost/capacity/fill. Existing Python research
  handles complete coverage/retry and consumes ranges only on modeled fills.
- Pending processing does not fully repeat session/news/manual blackout checks
  and checks execution before expiry. Do not copy the minute-long queue into
  second-based scalping. Stale signals must not become executable later.
- Learning persistence is symbol/magic based, not account/policy bound, and
  label state differs from live outcomes. Calendar refresh clears state before
  success. Expiry resetting scores/DD peaks is not proof of strategy recovery.

### Routing proposal

Async submission is not guaranteed broker acceptance or execution. MT5's
documentation explicitly requires transaction tracking. FIX availability,
colocation latency and post-only orders depend on broker access; the pasted
claims do not establish they are available here. Slicing 0.01 lot into smaller
orders is incompatible with a 0.01 minimum. No terminal, VPS, FIX bridge,
paid dependency or duplicate EA is installed.

Official references:
- https://www.mql5.com/en/docs/trading/ordersendasync
- https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes
- https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants

## Validation

78 targeted Python tests passed before final timestamp regression recheck;
dashboard polling/recovery VM test passed. All 18 protected Advisor1 files
match baseline SHA256 hashes. See `data/research/external_v2_20261022/` for the
reviewed-source manifest and reproducible synthetic smoke output.

Five-day one-seed synthetic smoke: regime +196.92 on nominal 10,000 equity,
random walk -133.67. Regime raw 24 vs 22 logged; random walk raw 27 vs 26 logged.
These are diagnostic simulator outputs, not the main bot's profit or evidence
that any acceptance target works. No profitable strategy promotion follows.

## Start main with MICRO when stopped

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1 -ScalpTimeframe MICRO
```

The launcher opens the existing dashboard if a main process is already
running; it does not change that process's timeframe.
