# Three-second demo confirmation experiment

User requested more entry opportunities based on confirmations. Main history on
the approved terminal showed 12 entries and 12 exits in the preceding two hours,
with reported exit price P/L totaling -7.66 USD (before commission and swap).
The bot was trading, although current snapshot positions were empty.

Live entry gating now measures the last three seconds instead of six. Two closed
directional candles remain required. Positive bid and ask progress, net movement
greater than spread, efficiency >= .65, four recent updates, maximum two-second
quote gaps, range/cost checks, identity, protective SL and risk limits remain.
Standalone research defaults remain six seconds. This is an unvalidated demo
experiment, not evidence of improved returns or guaranteed increased fill count.

Validation: 114 focused tests passed, including a recent bid/ask recovery that
passes the shorter window but fails the control, and missing-update rejection.
Safely restarted main on the approved explicit terminal. Rollback:
FAST_MICRO_WINDOW_SECONDS=6 followed by a safe main restart.

Self-check: tested decision boundaries; preserved risk controls; limited scope;
exposed active window in candidate telemetry; profitability remains unproven.
