# Demo resumption — 28 October 2026

At this continuation, MT5 was on build 6292 and returning fresh quotes across
the sampled XAUUSD/EURUSD/GBPUSD symbols. The earlier malformed/sparse-feed
condition was not reproduced in the initial current readback. This does not
prove that a terminal build change alone caused recovery.

The main bot was STOPPED and our temporary network-rescan hold still existed.
Verified the same USD demo against the approved provisional cost identity;
the cost profile was about 15.34 hours old, inside its existing 24-hour limit.
There were no open positions or pending orders. Removed only our maintenance
hold and resumed one main AUTO demo worker, preserving existing risk limits.

## Cursor fix

A tick within the existing five-second future-skew tolerance could move the
incremental request cursor into the future, producing negative request_seconds.
The cursor now uses min(latest_tick_epoch, observation_epoch) minus the normal
one-second overlap. Tick timestamps and freshness limits are not rewritten or
relaxed. A regression test reproduced the issue before the fix. All 104 focused
tests pass after it, including rejection of excessive future timestamps.

## Verification

- Fresh tick-history health returned available=True with about 5,900 cached
  ticks; request_seconds was nonnegative after the fix.
- Broker order_check returned retcode 0 for protected 0.01-lot BUY and SELL
  requests. These were checks only: neither was submitted or filled.
- A five-minute observation, 23:27:08–23:32:11 Africa/Lagos, recorded 61 status
  samples, no collection errors, stable demo identity and **zero broker deals**.
- Directional samples: WAIT 56, SELL 5. Six-second follow-through was rejected
  in 60 samples and the cost screen in 38; counts overlap.
- The account was flat at both observation endpoints. No actual trade or
  profitable high-frequency performance is established by these checks.

The executor/feed path is functioning again, but strategy authorization still
limits entries. An open market alone does not guarantee an exploitable setup.
No random entries, synthetic live ticks, freshness bypass, extra positions or
lot increases were used to manufacture a trade count.

Artifacts: `data/research/gold_resumed_20261028T2226/report.json` and its adjacent
`samples.jsonl`. Advisor1 source files are unchanged. The inverse was not started
as part of this main-only resumption.

Self-check: accuracy 4/5 (tested fix/readbacks, no trade-performance claim);
completeness 3/5 (continuous trading goal not demonstrated); clarity 4/5
(separates feed readiness, preflight and fills); actionability 4/5 (AUTO running,
strategy gates still apply); conciseness 4/5 (small cursor fix and focused tests).
The remaining gap needs validated entry-policy work, not a fabricated live fill.
