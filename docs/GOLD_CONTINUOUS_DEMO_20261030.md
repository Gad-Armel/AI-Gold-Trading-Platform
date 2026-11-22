# User-authorized continuous demo experimentation

User explicitly requested resuming high-activity demo orders after the failed
validation review. Removed the research entry hold, updated the dashboard to
USER_AUTHORIZED_DEMO_EXPERIMENT, and restarted main on the exact approved demo.
The existing 75/100 displayed-source 1/2/3 allocation drives entries. The failed
executable-event challenger stays shadow-only and the wider exit stays disabled.
Historical negative test results were not relabelled as a successful validation.

Changes: target loop cadence .25s (actual depends on processing), hourly ceiling
240 rather than60. This is an upper bound, not an order quota. Keep0.01 lot,
three total slots, mandatory broker SL and $5 planned risk, fresh quote/account
checks, entry spacing, news protection, reconciliation and loss cooldown. The
bot can remain active throughout the broker session but cannot guarantee fills
during absent/weak direction, bad data, capacity limits or broker closures.
It remains a Python/MT5 retail scalper; this change is not a native MQL5 EA port
or institutional HFT certification. No positive expectancy has been validated.

Validation:62 focused tests passed. Live readback confirmed two SELL positions,
tickets59107443024 and59107443530, both0.01, SL4007.66/4007.87. The latter
reported broker deal58706841134. Both were initially floating negative, so
activity is not evidence of profitability. Three-minute read-only monitor:
data/research/continuous_demo_20261030. Final broker reconciliation over
00:03:06–00:06:07 UTC (01:03–01:06 Africa/Lagos):9 entry deals,8 exit deals,
closed-deal net+2.11 USD, one position still open floating-.35 USD. Same demo
identity at both ends,37 dashboard samples, no observation errors. Early
losses were followed by profitable closes; this tiny interval does not overturn
the earlier negative strategy evidence or establish future profitability.

Advisor1 and inverse strategy remain untouched. Inverse remains disabled.
Rollback for previous cadence/cap: .5s/60; stop/hold new entries explicitly if
requested. No risk baselines or display values were reset.
