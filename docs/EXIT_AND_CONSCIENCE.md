> **September 15 correction:** Current SCALP uses M1 and FLOW_PRIMARY, with fresh
> executable-price levels and 6/12/30-second micro-flow context. The per-trade
> risk unit is capped at $2 and bound to a smaller initial stop when available.
> Earlier $4 lane-risk examples below describe the prior design, not current R.
> Observe-only learned/dollar inputs no longer influence execution scoring.
> See [the completed review](CONTINUOUS_SCALP_REVIEW.md) for tests and measured results.
# Exit policy and the position conscience

Written for: whoever maintains the three-horizon bot (`run_gold_consensus_bot.py`).

This records why the adaptive exit is anchored to **R** rather than to ATR, and
what the position conscience is allowed to do. Read it before retuning any
threshold in `ADAPTIVE_EXIT_CONFIG` or `FLOW_EXIT_CONFIG`.

## The defect this replaced

Measured on this broker's XAUUSD in September 2026, from the bot's own
recordings (`data/research/gold_forward/decisions_*.jsonl`, 3,601 cycles) and
15,000 M5 bars:

| Lane | Frame | Live ATR(14) | Lane stop | Stop in ATR | Old trail armed at |
|---|---|---|---|---|---|
| SCALP | M5 | $5.71 | $4.00 | 0.70 | +$5.71 (1.4x the stop) |
| INTRADAY | M15 | $9.25 | $2.00 | 0.22 | +$9.25 (4.6x the stop) |
| SWING | H1 | $21.36 | $4.00 | 0.19 | +$32.04 (8.0x the stop) |

The profit trail was configured as a multiple of ATR (`trail_activation_atr`),
while risk was configured in dollars. Those two scales were never reconciled.
As gold repriced from roughly $2,000 to $4,270, ATR grew and the dollar stops
did not, until **the trail armed further away than the stop in every lane** and
therefore could never fire. The only exits that could still fire were the money
stop, the news block, structural thesis invalidation and the quote-flow
detector. That is the mechanism behind "the bot rides a winner back to its
stop".

Two related defects were found at the same time:

* **Protection disarmed itself in quiet markets.** `evaluate_adaptive_exit`,
  `protective_exit` and `learned_exit` all rejected a quote older than 2
  seconds, using a measure that counts *seconds since the quote last changed*.
  MT5 publishes no tick when nothing trades, so a quiet market looked identical
  to a dead feed. In the recordings, **27 of 83 position-cycles (33%) were
  unmanaged** for this reason — during exactly the slow drifts the logic exists
  to catch.
* **Flow thresholds were fixed dollars** (0.35 / 0.70 / 1.50) chosen at ~$2,000
  gold. By $4,270 they were ~0.06 ATR, i.e. dealing noise.

## R: the risk unit

`R` is the lane's money stop expressed as a price distance:

```
R_price = stop_usd / (volume * contract_size)
```

At 0.01 lot on a 100oz contract the exposure is 1oz, so a $4.00 stop is a $4.00
price distance. R is the right anchor because:

* It is **scale-free**. It does not drift when gold reprices, which is what
  broke the ATR formulation.
* It is **bounded by the risk actually taken**. A giveback of `0.35R` is
  meaningful whatever the timeframe; a trail can no longer be configured to arm
  beyond the stop. `test_every_lane_arms_inside_its_own_risk_budget` enforces
  this structurally.
* It makes lanes **comparable**. "Banked at +0.5R" means the same thing in
  SCALP and SWING.

ATR and spread survive only as *floors*, so a giveback is never set inside
dealing noise — never as the primary scale.

### The three rules

1. **Giveback trail.** Once peak profit reaches `trail_arm_r * R`, surrendering
   `trail_giveback_r * R` from the peak closes the trade — unless the conscience
   still supports it *and* momentum has not turned, in which case the winner is
   allowed to run.
2. **Breakeven ratchet.** Once peak profit reaches `breakeven_arm_r * R`, the
   trade may never return below entry plus a slippage buffer. A trade that has
   paid for itself is not handed back. Note `move` is measured against the
   executable exit side, so the entry spread is already deducted: `move == 0` is
   true breakeven, not gross.
3. **Conviction collapse.** If the conscience collapses below
   `CONSCIENCE_EXIT_CONVICTION` while the position is at least
   `CONSCIENCE_EXIT_MIN_PROFIT_R` in profit, and stays there for the lane's
   confirmation window, the profit is banked instead of waiting for a target.
   This **only ever acts on a position in profit** — it can never pre-empt the
   configured stop on a loser.

## The position conscience

`services/research/gold_position_conscience.py`.

Every resource the bot collects already voted on whether to *enter*. Nothing
re-asked once a position existed. The conscience asks on every cycle: each
source votes in `[-1, +1]` relative to the direction actually held, weighted,
and only when that source is genuinely usable.

| Source | Weight | Reads |
|---|---|---|
| `consensus` | 0.26 | advisor agreement, scaled between the lane's exit and entry thresholds |
| `structure` | 0.20 | ATR-normalised trend and momentum; prior swing broken against the trade |
| `quote_flow` | 0.20 | executable quote movement — the only source that sees between candles |
| `cross_market` | 0.12 | observed dollar transmission |
| `learned` | 0.10 | continuation forecast |
| `economic` | 0.08 | slow macro context |
| `news` | 0.04 | scheduled release proximity |

Output is `conviction` in `[0, 1]` (0.5 is no net opinion), plus the
**coverage** it was computed from, plus a per-source breakdown that is written
to the status payload so every close is auditable.

### Deliberate limits

These preserve the project's safety posture and are covered by tests:

* **Exit-advisory only.** It never authorizes an entry, never resizes a
  position and never moves or removes a broker stop.
* **Tighten freely, widen narrowly.** Falling conviction tightens protection at
  any coverage. Rising conviction may loosen it only above
  `CONSCIENCE_MIN_COVERAGE_TO_WIDEN` and only inside
  `ADAPTIVE_GIVEBACK_MAX_SCALE`. Thin evidence is never read as confidence.
* **Heuristic, not calibrated.** `calibrated_probability` is explicitly `None`.
  These are strengths, not probabilities.

## Feed age vs quote quietness

Two different measurements, no longer conflated:

* `ENTRY_MAX_QUOTE_AGE_SECONDS` (2.0s) gates **entries** and still uses the
  strict measure, including seconds since the quote last changed.
* `EXIT_MAX_FEED_AGE_SECONDS` (15.0s) gates **protective exits** and uses
  broker tick age only.

The asymmetry is intentional: being slow to close is the dangerous failure,
being slow to open is not. A future-dated tick is still rejected outright.

## Current scalp policy and outstanding evidence

SCALP has first entry consideration, uses flow evidence at 60 with a strong
opposing candle veto at 72, and requires fresh micro-flow agreement. Intraday
and swing retain their two-source requirements. Scalp re-entry uses a 12-second
cooldown, reconciled net fill history, a 30-entry hourly ceiling, a pause after
four consecutive losses, and spread/volatility guards. Broker-stop exits count;
failed close attempts do not count as completed losses. No source may increase
position size or the three-position cap.

This is an experimental frequency change, not evidence of higher returns. The
chronological quote forecast did not beat a zero-change baseline. Full-policy
forward paper evaluation remains necessary. The $100 capital profile can reject
trades whose required stop geometry does not fit the $2 planned exposure cap;
this review does not loosen that cap to force trading.
## Archived sources

The `AI_Gold_Economic_Advisor_*.zip` archives at the repository root are the
**only** copy of `gold_economic_advisor_v6.py`, its dashboard and its tests —
those files exist nowhere in the working tree, which ships V5. Do not prune the
archives until that is resolved.
