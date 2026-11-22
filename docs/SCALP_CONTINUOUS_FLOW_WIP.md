> **Reviewed September 15, 2026:** The unfinished implementation below has now
> been repaired and expanded. The suite passes 210 tests. See
> [the completed review and measured results](CONTINUOUS_SCALP_REVIEW.md).
> Performance remains unproven; the new research model failed its baseline.
> The rest of this file is retained as the original handoff, not current run guidance.
# WIP: continuous-flow scalper — resume here

Written for: the next session continuing this work (Claude or a developer).

**Status: INCOMPLETE. Do not run the bot from this state.** The code compiles
and imports, but 8 tests fail and 2 error. All of them are expected fallout
from deliberate behaviour changes, but they must be worked through one by one —
each needs a judgement about whether the *test* encoded old behaviour or the
*change* is wrong.

Baseline before this work started: **190 tests green.**
Current: **10 failing/erroring, 171 green.**

---

## Why this work was done

User asked for: scalping as close to continuous as possible; take profit the
moment flow risks reversing regardless of size; immediately re-enter whatever
flow suggests next; the smartest possible live "conscience".

## What the measurements showed (all from repo data, reproducible)

From `data/research/gold_forward/decisions_*.jsonl` (2,420 SCALP cycles,
2026-09-10..15) and `data/research/gold_sources/XAUUSD_M5.csv` (15,000 bars):

1. **The three advisors emit evidence on incompatible scales.** Directional
   medians: `MT5_CANDLES` 75.0, `API_CANDLES` 75.3, `MT5_TICK_FLOW` **53.8**
   (p90 71.8, observed max 91.5). A single 82 bar let the candle advisors
   qualify in ~15% of directional cycles and the tick advisor in **1.6%**.
2. Because SCALP *requires* `MT5_TICK_FLOW` strong, the lane was entry-eligible
   in **1 of 2,420 cycles (0.04%)** — while its own weights say tick flow is
   60% of the decision. The shared threshold inverted the lane's design.
3. In **88%** of strong-flow moments **no candle advisor agreed** with the
   flow direction, so SCALP levels cannot be borrowed from an agreeing
   advisor — they must be derived from ATR.
4. Simulated FLOW_PRIMARY gate at flow bar 60 / veto 72 → ~9% of cycles
   entry-eligible (vs 0.04%). That is the basis for the chosen thresholds.

## Honest caveat that must reach the user

Frequency is not profitability. There is **no labelled outcome data** in this
repo to show the tick-flow signal has edge after the $0.24 median spread — the
only recorded positions (83 cycles) are all INTRADAY. This build makes the lane
*able* to scalp and *safe* to scalp; whether it *should* is an empirical
question that needs a paper-trading run. Do not tell the user this will make
money.

---

## What is already done

### New files
- `services/research/gold_micro_flow.py` — `MicroFlow` rolling quote buffer;
  multi-window (3/10/30s) graded read; `reversal_risk` 0..1 for a held
  direction; `fast_profit_take()` with a cost floor. **Has no tests yet.**

### Config (`config/gold_consensus_settings.py`)
- SCALP continuous-flow profile: `SCALP_FLOW_ENTRY_EVIDENCE=60`,
  `SCALP_OPPOSING_VETO_EVIDENCE=72`, `SCALP_LEVEL_TARGET_ATR=0.60`,
  `SCALP_LEVEL_STOP_ATR=0.80`.
- Re-entry: `SCALP_REENTRY_COOLDOWN_SECONDS=12`, `SCALP_ALLOW_DIRECTION_FLIP=True`.
- Churn guards: `SCALP_MAX_TRADES_PER_HOUR=30`,
  `SCALP_MAX_CONSECUTIVE_LOSSES=4`, `SCALP_LOSS_COOLDOWN_SECONDS=900`,
  `SCALP_MAX_SPREAD_USD=0.35`, `SCALP_BLOCK_VOLATILITY_EXPANSION=True`.
- Cost floor: `SCALP_MIN_PROFIT_TAKE_SPREADS=2.0`, `SCALP_MIN_PROFIT_TAKE_USD=0.30`,
  `SCALP_REVERSAL_RISK_EXIT=0.70`.
- `MICRO_FLOW_*` settings.
- `HORIZON_LANES`: SCALP gains `entry_mode="FLOW_PRIMARY"`, `exit_frame="M1"`;
  INTRADAY/SWING explicitly `CONSENSUS_2_OF_3` with `M15`/`H1`.
- `ADAPTIVE_EXIT_CONFIG` gains `fast_flow_exit_risk` (0.70 / 0.85 / None).
- `CONSCIENCE_WEIGHTS` re-balanced to include `micro_flow` 0.20 and `regime` 0.08.

### Changed
- `gold_horizon_policy.py` — `flow_primary_levels()`, `_flow_primary_decision()`,
  `entry_mode` branch, `market_context` parameter, per-mode `signal_band` and
  `required_strong_advisor_count`.
- `gold_adaptive_exit.py` — `exit_frame()` makes the candle frame per-lane
  configurable (SCALP → M1); `micro_flow` parameter; fast cost-floored
  profit-take placed after the breakeven ratchet, before the giveback trail.
- `gold_position_conscience.py` — `_micro_flow_vote`, `_regime_vote`,
  dispersion penalty, asymmetric smoothing (falls fast, rises slow) via new
  `state`/`now` parameters. Policy string now `CONSCIENCE_V2`.
- `run_gold_consensus_bot.py` — `MicroFlow` instance; contexts built *before*
  decisions so SCALP can derive levels; `_scalp_churn_blocks()`; re-entry
  cooldown replacing the new-bar wait for FLOW_PRIMARY; exit/entry bookkeeping
  (`last_exit_at`, `last_exit_direction`, `entry_times`, `consecutive_losses`);
  extra lane telemetry in the status payload.

---

## NEXT STEPS, in order

### 1. Fix the 2 errors (highest priority — likely real)
```
test_gold_proposal_features.ProposalFeatureTests.test_gap_uses_only_completed_candles_and_is_research_only
test_gold_proposal_features.ProposalFeatureTests.test_sweep_requires_reclaim_of_previous_range
```
Run `python -m unittest test_gold_proposal_features -v` and read the traceback.
Almost certainly these build an **M5** fixture and call
`market_exit_context(snapshot, 'SCALP')`, which now reads **M1**. If so the fix
is in the test fixture (supply `M1` bars, or assert against a lane that still
uses M5). **But confirm it is a fixture issue and not `exit_frame()` reading
the wrong key** before editing the test.

### 2. `test_gold_adaptive_exit.test_forming_candle_is_excluded`
Same root cause — M5 fixture, SCALP now M1. Update the fixture to `M1` with
`freq='1min'`, keeping the test's actual intent (a forming candle must not
change the result).

### 3. The five `test_gold_horizon_policy` failures
These encode the **old** SCALP consensus behaviour. Work through each:
- `test_two_strong_advisors_override_one_heavily_weighted_advisor` — this one
  is the deliberate inversion. Under FLOW_PRIMARY tick flow decides and two
  candle advisors no longer override it. **Rewrite it to assert the veto
  instead**: two candle advisors opposing at ≥72 must block the flow entry.
  Keep an equivalent override test pointed at INTRADAY, which is unchanged.
- `test_each_horizon_uses_a_different_atr_target` — SCALP targets now come from
  `flow_primary_levels`, needing `market_context={'SCALP': {'atr':…, 'close':…}}`.
- `test_stale_optional_api_does_not_disable_scalp`,
  `test_strong_bias_can_enter_when_action_is_wait`,
  `test_strong_fresh_economic_conflict_blocks_swing_not_scalp` — update the
  SCALP expectations to the flow-primary path; the INTRADAY/SWING halves of
  these tests must keep passing unchanged (that is the regression guard that
  the slower lanes were not touched).
- `test_intraday_and_swing_require_both_independent_candle_feeds` — should be
  unaffected by design. **If this one still fails after the others, that is a
  real bug in the `entry_mode` branch — investigate, do not edit the test.**

### 4. `test_gold_position_conscience.test_full_agreement_scores_high_with_full_coverage`
Coverage is 0.72 not 1.0 because the fixture does not supply the two new
sources. Add `micro_flow=` and a `structure_research.regime` to the `agreeing()`
fixture.

### 5. Write the missing tests (none exist yet for the new work)
- `MicroFlow`: out-of-order and repeated quotes rejected; gap clears the
  buffer; `reversal_risk` rises as flow opposes; both quote sides must agree
  (one-sided spread widening scores zero); `fast_profit_take` refuses below the
  cost floor **and** refuses when risk is under threshold.
- `flow_primary_levels`: TP/SL on the correct side for BUY and SELL; empty on
  zero/negative ATR.
- `_flow_primary_decision`: blocks when flow unusable / non-directional / below
  bar; blocks on strong opposing structure; allows with agreeing or silent
  structure.
- `_scalp_churn_blocks`: rate limit, loss cooldown expiry, spread ceiling,
  volatility-expansion pause.
- Conscience: asymmetric smoothing (a drop applies immediately, a recovery is
  damped); dispersion pulls a +1/-1 split toward neutral.
- Re-entry: cooldown blocks, then clears; direction flip allowed when
  `SCALP_ALLOW_DIRECTION_FLIP`.

### 6. Re-validate
```powershell
python tools/validate_gold_changes.py      # must reach 190+ green
```
Then replay the recordings as a behaviour check:
`python - <<PY` … load `decisions_*.jsonl`, rebuild decisions with
`market_context`, and confirm the SCALP entry-eligible rate lands near the
simulated ~9%, not 0.04% and not ~100%.

### 7. Still outstanding from the previous round
- `_lane_risk_usd` for SCALP returns the **cumulative** $4.00. With
  `max_positions` effectively 1 in adaptive mode that is fine, but confirm it
  is still the intended R now that the lane trades far more often.
- Dashboard shows `conscience` but not the new `micro_flow` / `entries_last_hour`
  / `consecutive_losses` lane fields — add them to `conscienceLine()` or a new
  panel in `services/dashboard/gold_consensus_web.py`.
- `docs/EXIT_AND_CONSCIENCE.md` predates this round: its "SCALP almost never
  trades / left untouched deliberately" section is now **out of date** and must
  be rewritten to describe FLOW_PRIMARY.

### 8. Unchanged constraints to respect
- `run_gold_advisor.py` (v1) and its dependencies must not be modified.
- The zip archives at the repo root are the only copy of Economic Advisor V6.
- The current-generation bot is **untracked in git** — consider committing
  before further large changes.
