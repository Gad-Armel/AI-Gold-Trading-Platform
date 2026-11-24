# XAUUSD manual scalp advisor

This is a new, read-only research variant. It does **not** modify `run_gold_advisor.py`,
Gold Advisor 1, or its dependencies, and it cannot place or manage orders. It
combines two existing XAUUSD views: completed-candle trend/context and the
separate MT5 short-window tick-flow research report. The output is actionable
only when both scalp views agree and quote/report quality gates pass; otherwise
it returns `WAIT`.

## Run

In the repository's configured Python environment, connect MT5 to the intended
XAUUSD broker account and run:

```powershell
python -B run_gold_manual_scalp_advisor.py --once
```

Continuous manual monitoring (one-second polling by default):

```powershell
python -B run_gold_manual_scalp_advisor.py
```

To display its live evidence in the unified Gold dashboard, keep the
continuous advisor running and start the unified dashboard:

```powershell
python -B run_gold_unified_dashboard.py
```

The dashboard's **Manual** tab refreshes independently. It
shows the candle/tick agreement, directional evidence scores, broker quote and
spread, validity, scenario levels, supporting reasons, and blocking cautions.
An absent report shows WAIT; an invalid, stale, or expired report is never
presented as a current BUY/SELL. The separate advisor process must be running
for fresh reports to appear. Gold Advisor 1 and the EA's own decision remain
separate and unchanged.

The latest JSON report is written to
`data/runtime/gold_manual_scalp_advisory.json`. Changed signal states are
appended to `data/research/gold_manual_scalp_advisory_history.jsonl`. The
history records signal-state changes immediately and repeats an unchanged state
at most every 15 seconds for prospective review. The instance lock prevents
starting a second copy of this advisor.

## Decision behavior

- Both the completed-candle SCALP action and short-window tick SCALP action must
  be BUY or SELL in the same direction.
- Reports must be recent and timezone-aware; the raw tick feed must be
  available, usable, and no older than the configured guard.
- The two report quotes must agree within a price tolerance; spread must stay
  below the conservative advisory ceiling.
- The candle model's scenario stop and TP1 must be on the correct side of the
  entry reference; TP1 must exceed spread and pass the minimum scenario
  reward/risk gate.
- The final score is the lower of two directional evidence scores. It is not a
  probability, expected return, or proven predictor of winning trades.
- A signal expires quickly (15 seconds by default). Recheck the live quote and
  recalculate; do not act on an expired report.

This combines broker-candle context with broker-quote changes, not independent
exchange data. The MT5 tick-flow output is not centralized trade aggressor flow,
and optional MT5 DOM is broker-specific. Scenario levels are estimates, not
guaranteed prices or personalized financial advice. Spread, slippage, gaps,
market closure, or a stale/disconnected terminal may make manual execution
unsafe. This advisory does not establish profitability.

## Validation and research limits

Run focused code tests:

```powershell
python -B -m unittest discover -s tests -p test_gold_manual_scalp_advisor.py -v
python -B -m unittest discover -s tests -p test_gold_manual_scalp_web.py -v
python -B -m unittest discover -s tests -p test_gold_scalp_web.py -v
```

These are deterministic software-invariant tests, not synthetic trading
performance evidence. The signal is not promoted or described as "good" until
prospective signals are logged, independently labeled outcomes are evaluated
with realistic spread/commission/slippage, and a chronological out-of-sample
review is completed. Continue using the existing demo/shadow protections; no
live execution is enabled by this advisor.
