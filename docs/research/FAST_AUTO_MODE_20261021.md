# Fastest-feasible demo timeframe selection

User asked to remedy inactivity without modifying Advisor 1. The observed S5
median range was 0.625 against an estimated 0.70 round-trip cost; the configured
3x feasibility check required 2.10. S5 candle directions also disagreed at the
inspection instant. Going to S1 would not inherently solve either condition.

`--scalp-timeframe AUTO` considers S5, S15, then S30 and chooses the shortest
candidate satisfying the existing closed-candle, coverage, spread, cost,
extension and direction/evidence gates. If none qualifies, it reports each reason
and uses S30 for observation; all normal entry gates remain in force. No order
is authorized by selection alone. News, risk, broker checks, persistence and
3/5/6 staging still apply. No cost thresholds were lowered.

When SCALP positions exist, the selected period is pinned to the first successful
entry's in-process period until flat. After restart with existing exposure and
no recovered period, it conservatively uses S30; it does not switch to a shorter
addition period. Advisor 1 remains unchanged and supplies existing exit context.

Candidate-selection telemetry is included in the decision and entry journal as
`fast_timeframe_selection`. These eligibility checks are not evidence of positive
expectancy, a calibrated win probability or proof that AUTO beats fixed periods.

78 targeted tests passed before deployment. These include shortest eligible
selection, fallback rejection, held-period pinning, fresh data, provisional demo
binding and existing risk/entry regressions. Limits remain 0.01 lot per trade and
four controlled positions maximum. S1 stays research-only.

Start only when stopped:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& ".\.venv-audit\Scripts\python.exe" -u -B .\run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --scalp-timeframe AUTO --smc-policy observe --allow-provisional-costs --s30-cost-report data/runtime/s5_provisional_demo_costs.json
```
