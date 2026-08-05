# V6.2 Architecture and Safety

## Four layers

1. **Data:** MT5 bid/ask ticks and closed candles; optional free macro context.
2. **Evidence:** legacy indicator/factor candidates, tick microstructure, V6 structural consensus and cost/location filters.
3. **Research:** shadow triple barriers, candidate logs, chronological walk-forward and approval hash.
4. **Execution:** controlled demo only after approval; fresh quote, account identity and order preflight checks.

## Non-bypass guarantees

- Shadow import graph contains no order sender.
- Demo preflight and execution gate both validate the approval artifact.
- Approval is bound to the complete V6 settings hash and expires after seven days.
- Demo and shadow evaluate the same `v6_candidate_gate` and `v6_market_structure` modules.
- Real-account execution and core live trading are disabled.
- One bot position maximum; no pyramiding.
- Cumulative demo loss stop: -$100, persistent until explicit reset.
- Three consecutive approved-demo losses revoke approval and require shadow recalibration.
