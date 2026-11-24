# Main bot second review — 23 October 2026

## Post-fix performance, not the dashboard session counter

Read-only demo broker reconciliation:
`data/research/revision_20261023/trade_audit.json`.
The sample is restricted to positions opened after the previous deployment
at 22 October 17:11:21 UTC (18:11:21 Lagos).

Final capture at 23 October 00:26:33 UTC / 01:26:33 Lagos includes the position
that closed during review: 50 closed positions, 20 wins, 30 losses, net
-17.89 USD including recorded costs; profit factor 0.538. Average win
+1.0405, average loss -1.29 USD. S5: 22 trades / -0.08 USD;
S15: 4 / -1.91; S30: 24 / -15.90.
There are no new S1 entries in this sample. The small unequal timeframe
groups are not independent strategy comparisons or grounds to select S5
as a proven winner. The sample does not demonstrate profitable expectancy.
Open positions are excluded; the dashboard's session baseline differs.

The previous micro-confirmation and monetary stop-risk fixes remain active.
They improved correctness, not established profitability. No threshold is
tuned to recover the recorded losses in this review.

## Reproducible exit dependency defect

Fast entry/exit direction is owned by the selected S1/S5/S15/S30 signal;
Advisor1 and other higher-timeframe signals are context-only. However, the
adaptive neutral-thesis exit required two usable neutral contributors.
A completed fast signal could therefore become neutral while context
advisors stayed directional, suppressing the intended unsupported-loss exit.

The fast-primary branch now uses only its matching usable fast contributor
to confirm neutrality. Legacy/non-fast paths still require two neutral
contributors. Stale/unavailable fast data does not count as neutral.
The remaining protections are unchanged: dominant bias must be WAIT,
completed-candle momentum must oppose the held position, the loss must exceed
the larger of two spreads or 0.1 ATR, and adverse confirmation must persist
for the configured duration (SCALP: 10 seconds). Mixed candles alone do not
immediately close profitable trades. No fixed TP, SL widening or retries added.

## Validation and deployment

133 targeted tests pass. New regressions exercise all four fast frames,
context disagreement, stale primary data, confirmation persistence and
momentum/loss prerequisites. Tests establish behavior, not improved returns.
Advisor1's protected files are not edited. Demo lot 0.01, global position
cap four, planned price-to-SL risk cap 5 USD, AUTO timeframes and existing
entry guards are preserved. Planned risk is not an execution-loss guarantee.

Deployment uses a temporary new-entry hold and verifies flat demo positions
before restart. Existing positions are not manually closed for deployment.
The temporary hold is removed only after the new main starts successfully.

## Launch

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1 -ScalpTimeframe AUTO
```
