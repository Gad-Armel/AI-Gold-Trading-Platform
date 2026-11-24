# S30 efficiency correction — 20 October 2026

The bot was connected and had valid quotes, but no entry attempts. The six-second
efficiency gate divided net movement by the sum of every individual tick movement.
High quote activity and intra-second oscillation inflated that denominator; the
0.65 threshold was substantially more restrictive than a six-second trend filter
at a stable observation cadence.

The denominator now uses the initial midpoint and the last midpoint in each
one-second bucket. Net displacement, the six-second window, 0.65 threshold,
minimum displacement greater than spread, original tick-coverage validation,
spread expansion, extension and cost gates remain. Raw efficiency is retained in
telemetry as `raw_tick_efficiency`; `quote_efficiency` is the sampled measurement.
This changes the signal statistic, not just presentation. It is not evidence of
positive expectancy and can increase the frequency of demo entries.

Read-only diagnostic at 15:43 Lagos time:
`data/research/goldhft_20261020/efficiency_diagnostic.json`.
798 evaluated one-second observations; three directional S30 existed during 150.
Old efficiency plus the other candidate filters: zero distinct setups.
Corrected efficiency plus the same other filters: three distinct setups across
nine passing observations. These are correlated signal observations, not executed
trades; news, broker protections, persistence and portfolio controls still apply.

Mixed S30 candle bodies now report no directional signal without falsely labeling
healthy input unavailable or stale. Data gaps and stale quotes still fail closed.

53 targeted tests passed, including a regression with intra-second oscillations
and identical one-second endpoints. Protected Advisor 1 code is unchanged.

Repeat the diagnostic without placing orders:

```powershell
& ".\.venv-audit\Scripts\python.exe" -B tools/diagnose_s30_filters.py
```
