# Independent exit review

Reviewed `gold_adaptive_exit.py`, `gold_profit_lock.py`, `gold_micro_flow.py`
and `exit_review_20261029.json`. Read-only: no live orders or strategy changes.

## What the data establishes

- 131 completed positions: net -56.06 USD, 34 wins/97 losses, median hold37.955s.
- 69 broker stop exits: net -77.11, median hold20.562s, median initial stop0.90.
- Three-source vote: 77 positions, net -35.62, 55 stops totaling -47.74;
  median holding time27.899s, median initial stop0.86 price units.
- One-dollar profit lock: 16 positions, net+13.02, 15 wins/1 loss,
  median hold55.805s. The one loss was -0.06.

These are grouped retrospective outcomes across changing strategies. Exit-group
selection is outcome-dependent, so the positive profit-lock group does not prove
that its settings maximize returns. Conversely, the data does not establish
that premature profit-taking caused the strategy's losses. Post-exit executable
markouts and same-entry alternative-exit replay are missing.

## Concrete mechanism worth testing

The per-ticket profit lock closes immediately at profit <=80% of observed peak,
after peak>=1USD. It has neither spread/ATR noise floor nor quote-event persistence.
At a1USD peak, a0.20USD executable drawdown can close a0.01-lot XAUUSD position.
If current spread is0.40–0.60 price units, this trigger sits inside contemporary
dealing noise. This is a plausible premature-exit mechanism, not proof of better
returns from delaying exits.

The adaptive-R giveback already has spread/ATR floors and fading-support logic,
but it is evaluated after the unconditional per-ticket lock, so it cannot keep
the small winner open once that earlier lock triggers. Profit lock is also
checked by independent fast protection; changing only adaptive_exit is incomplete.

## Candidate behavior for controlled comparison

For each ticket, convert peak and present executable price profit to USD using
that ticket's volume and contract size. Test a configurable allowance:

`giveback=max((1-retained_fraction)*peak, spread_multiple*spread*exposure,
              atr_multiple*ATR*exposure)`.

Use the spread/ATR enlargement only with fresh, same-direction supporting flow,
and cap it so the trigger retains a documented minimum positive/cost buffer.
Opposing flow can retain the tighter current lock. A short persistence condition
must be based on distinct broker tick timestamps, not repeated loop evaluations.
News, SL, stale-data handling, global risk exits and deeper adverse giveback must
remain independent and may close immediately. Never move or widen the broker SL.

No threshold should be advertised as optimal: freeze candidate values before
comparison, replay identical causal entries, then forward observe.

## Required regression tests

1. BUY and SELL use correct executable exit side and ticket volume.
2. Small winner with supporting fresh flow survives a drawdown inside noise;
   original mode still triggers at original20% boundary.
3. Sustained independent opposite ticks trigger, while repeated same timestamp
   loop reads never satisfy persistence.
4. Deep giveback/news/hard risk exit is not delayed by supporting-flow grace.
5. Missing/stale/nonfinite context does not silently grant extra hold time.
6. Adding/removing/partially closing tickets retains each old ticket's peak,
   scales only for changed volume and resets persistence for rebound/rebind.
7. No hard risk/SL widening, no new orders and no use of future ticks.
8. Replayed net outcome incorporates executable spread and separate assumed or
   measured commission/slippage; compare same entry cohort and exposure.

Recommendation: prioritize entry/regime/cost correction. Keep the existing
hard risk boundaries and test exit noise-awareness as a separate challenger.
