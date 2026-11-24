# User-requested aggressive demo experiment

Main AUTO profile: one completed directional candle rather than two; recent
range must exceed 1.0 times estimated costs rather than 1.5; post-exit analysis
and same-direction re-entry wait shortened from five seconds to one.
Three-second executable bid/ask confirmation remains. No forced orders, loss
averaging or removal of SL, fresh-data, stop-risk, cost-expiry or capacity limits.
Hourly ceiling remains 60, minimum entry spacing two seconds and loss cooldown
30 seconds. Independent opposite setup scanning remains active.

Validation: 93 focused tests passed. Updated timing boundary tests and increased
the deliberately unaffordable cost fixture to remain unaffordable at the new
margin. Added a one-completed-candle/no-future-candle test. Safe demo reload.

This lowers entry selectivity. It is not validated improvement in returns and
cannot ensure continuous trades. Rollback: confirmation bars 2, cost multiple
1.5, post-exit and re-entry pauses 5, then safely reload main.

Self-check: focused boundary verification; retained risk guards; main-only scope;
explicit rollback; no frequency or profitability claim from unit tests.
