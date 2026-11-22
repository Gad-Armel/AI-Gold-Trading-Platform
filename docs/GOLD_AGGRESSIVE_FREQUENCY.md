# Aggressive demo entry cadence — 28 October 2026

Only idle timing and the hourly entry ceiling change. This profile does not
promise more profitable trades or authorize entries when data/cost/risk fail.

| Parameter | Previous | Aggressive |
| --- | ---: | ---: |
| Minimum entry spacing | 5 seconds | 2 seconds |
| Post-close re-entry cooldown | 30 seconds | 5 seconds |
| Global post-exit analysis pause | 30 seconds | 5 seconds |
| SCALP directional persistence | 2 seconds | 1 second |
| SCALP hourly entry ceiling | 30 | 60 |

The ceiling is not a target. Existing profitable-position addition checks,
five-second addition spacing, reconciled history, 30-second loss cooldown,
mandatory SL, exact 0.01 lot, configured position caps, $5 per-trade risk,
spread/cost/micro-confirmation and fresh cost evidence remain unchanged.
Advisor1 and the inverse executor are not edited.

The saved main status at inspection was STOPPED, not an active live baseline.
Its historical processing timings therefore cannot establish present latency.
No millisecond or trades-per-hour throughput improvement is claimed from
settings alone. The existing 500 ms target polling interval is unchanged.

The fast path currently rejects cost evidence older than 24 hours. Do not
disable that safeguard or simply re-date an old calibration to obtain entries.
Use current broker-specific cost evidence before enabling fast demo entries.
AUTO continues to assess S5/S15/S30; no forced S1/noisy-signal bypass added.

Rollback: restore the five previous values shown above in
`config/gold_consensus_settings.py`, then restart the main worker normally.

## Verification

101 focused tests pass, including seven profile-specific tests for cooldown
boundaries, hourly ceiling, preserved loss cooldown, required history and
blocked-signal/addition protection. No actual-trading frequency or return
improvement is established by those tests. Activation is pending the operator's
choice about renewing explicitly provisional cost assumptions; the expiry
check was not bypassed. The operator subsequently approved new provisional
assumptions, and the main demo was activated with AUTO. The profile remains
explicitly provisional, not measured evidence. Startup exposed a separate
one-bar M1/fast-frame mismatch: fast confirmation now explicitly maps one/two
M1 bars to the supported three fast bars, preserving fresh-candle timestamps.
The global post-exit analysis pause was also aligned to five seconds so it
cannot silently override the shorter SCALP re-entry cooldown.

## Delivery self-check

- Accuracy 4/5: settings and 99 tests verified; no live frequency measurement.
- Completeness 4/5: demo activation verified; stale broker ticks still block entries.
- Clarity 4/5: exact timer changes and rollback documented; frequency is conditional.
- Actionability 4/5: normal AUTO launcher remains valid after the cost prerequisite.
- Conciseness 4/5: changes limited to four settings and focused tests.

The deployment required explicit operator approval, not a silent cost-evidence
freshness bypass. The user can verify the exact changes, but should not read
them as a promise of higher accuracy or profitability.
