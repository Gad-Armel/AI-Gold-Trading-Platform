# Displayed source allocation and quicker profit lock

User requested strictly one position for one strong displayed source, two for
two agreeing, more for all three. Implemented 75/100 heuristic strength threshold
for MT5_CANDLES, API_CANDLES, MT5_TICK_FLOW, counting each once and excluding
unusable/expired sources. Majority by source count wins; equal opposing counts
wait. Allowance is 1/2/3, bounded by the existing three-slot cap. Existing orders
are not forcibly liquidated merely because support count drops. Opposite votes
must persist one second to request close-before-reentry.

This replaces fast-candle direction/continuation entry vetoes in main fast mode.
Fresh quote/ATR, news, account identity, cost-profile validity, broker permissions,
SL grid/dollar risk, spacing, hourly/loss cooldown and total capacity remain.
Source-vote allocation may add a second position before the first is profitable;
each existing position still needs a valid SL and additions cannot exceed votes.
This is explicit source-count allocation, not loss-recovery martingale.
Orders remain sequential with fresh broker checks. ATR-derived analysis targets
support existing cost/risk checks; broker TP remains zero (dynamic exits).

Per-position profit lock now arms at $1 rather than $6, requests close after 20%
giveback, and leaves SL/flow/news exits intact. Peak P/L is executable price P/L,
not a guaranteed net profit after fees or slippage. No claim of improved returns.

Validation: 94 focused tests passed, including vote counts, opposing ties,
unusable/expired/duplicate sources, addition cap, missing SL, execution and exit
regressions. Safe demo restart verified one protected position beforehand.
Rollback: THREE_SOURCE_VOTE_ENABLED=False; profit_lock_arm_usd=6.0; safe reload.
Advisor1 code unchanged. Self-check: scoped main policy, tests of safety/behavior,
explicit demo activation, performance and live fill limitations stated.
