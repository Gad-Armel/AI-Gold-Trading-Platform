# Demo entry review — 26 October 2026

## Findings

- Of the last 100 successful main entries in the local execution journal,
  92 failed the recorded range-versus-cost screen and eight passed. The screen
  was configured as a warning, so it could not prevent those entries. This is
  an execution-quality finding, not proof that all 92 trades lost.
- Fresh MT5 XAUUSD tick timestamps were approximately 7,200 seconds ahead of
  UTC. The configured 10,800-second offset made fresh quotes appear one hour
  old after the broker's seasonal clock change. The quote freshness rejection
  was correct for its inputs; bypassing that safeguard would hide the problem.
- Fast direction is determined by completed tick-built candles and current
  follow-through, not by all advisors voting. Candle body/range evidence is a
  heuristic, not a probability of winning.

## Changes

- Broker offset corrected to UTC+2 for the currently verified demo terminal.
  Recheck it after another server/time change; no blind automatic correction.
- Existing fast-entry cost screen enabled: the median completed candle range
  must exceed three times spread plus configured commission/slippage price
  equivalents. AUTO can choose a slower supported period when the fastest
  candidate fails. This is a conservative affordability proxy, not predicted
  return, and may substantially reduce trading frequency.
- The inverse retains the main's exact accepted decision by reversing its
  confirmed fill, rather than running an independent, potentially divergent
  model. Source and inverse directions and this signal policy are now explicit
  in durable links/status. Main changes therefore propagate to future inverse
  entries automatically. Broker/risk checks can still prevent a mirror order.
- Source-linked close-decision notifications remain active; SLs can close a
  leg independently. Execution prices/times and net profits cannot be exactly
  inverted because both sides pay trading costs.

## Validation and limits

106 targeted tests pass, including both mirrored directions, decision-linked
closure, no re-entry after inverse SL, account isolation, cost veto defaults,
manual warning-only override, and fast timeframe selection. No profitable
out-of-sample backtest or forward result is claimed by this configuration change.
Cost estimates remain provisional demo estimates. Keep 0.01 lots, at most four
combined positions, broker SLs and demo-only execution. Advisor1 is unchanged.
