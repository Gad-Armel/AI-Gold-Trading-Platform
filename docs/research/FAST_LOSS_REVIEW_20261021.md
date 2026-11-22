# Fast strategy loss review and exit coherence correction

## Actual broker cohort

Read-only broker audit at 10:01 Lagos on 21 October 2026:
`data/research/demo_20261021/loss_review.json`.
Trades opened after the range/cost-veto removal at 07:17:35 UTC:

- 50 fully closed trades: net -21.44 USD, 13 wins, 36 losses, one flat.
- Average winner +0.5769, average loser -0.8039, profit factor 0.2592.
- S5: 17 trades / -3.11; S15: 16 / -8.65; S30: 17 / -9.68.
- 25 trades held at most 15 seconds, net -8.94.
- Broker SL: 12 trades / -14.89; confirmed thesis invalidation: 23 / -7.28.
- 23 entries opposed Advisor 1 at entry, net -7.28. These retrospective groups
  are not independent experiments and do not establish a profitable alternative.

## Concrete inconsistency corrected

Fast entries use independent S5/S15/S30 directional decisions, but the main loop
explicitly supplied the original Advisor 1 decision to adaptive exits and position
conscience. Thus an entry could legitimately oppose Advisor 1 and subsequently
be invalidated by that same slower thesis. This was a policy mismatch, not a
demonstration that all losing exits were incorrect. Holding those trades longer
might also have produced worse outcomes; the audit cannot determine that.

The exit directional thesis now uses the current active entry policy decision.
Advisor 1 remains available in `advisor1_context`, but its opposing direction
alone is no longer an independent fast-thesis reversal. Original M1 structural
context, ATR, broker SLs, quote-flow protection, trailing, news and global circuit
breakers remain. Adaptive exit telemetry records the thesis source.

91 targeted tests passed. New regression tests demonstrate that opposing
Advisor 1 context does not close an otherwise valid S5 BUY, an actual confirmed
fast SELL reversal still closes it, news protection survives and decision inputs
are copied without mutation. Advisor 1 protected code is not edited.

## User's proposed two-to-five sequence

Clarification requested: actual individual quote ticks versus closed S5 candles.
Neither two-position bursts nor a new entry/exit sequence is activated here.
Existing 3/5/6 progression, profitable-only additions, 0.01 lot and four-position
cap remain. Two same-direction quote updates are not by themselves evidence of
an executable profit after spread. Counter changes must use distinct completed
events rather than count repeated loop evaluations.

A proposed sequence needs chronological bid/ask replay with latency, no duplicate
entries per sequence, clear reset/reversal rules, broker SL and separate gross
and net exits. Re-entering twice merely because the last sequence won can increase
correlated exposure and repeated spread payments. No guaranteed profit claim.

This fix does not restore the range/cost veto removed explicitly by the user.
It corrects a specific execution-policy mismatch, not proven profitability.
