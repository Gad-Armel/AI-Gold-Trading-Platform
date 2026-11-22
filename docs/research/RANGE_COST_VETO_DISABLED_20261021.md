# User-requested demo range/cost veto removal

User explicitly requested removal of the experimental range >= 3x round-trip-cost
entry veto to observe demo performance. `FAST_RANGE_COST_FILTER_ENABLED=False`
now makes this calculation a warning in live fast-mode entry checks and AUTO
selection. Raw costs and the failed/passed calculation remain visible in telemetry
as `cost_screen_passed`; `range_cost_screen_enforced` explicitly reports false.

This is a strategy relaxation, not evidence of improved profitability. Historical
research screens keep the original strict default unless explicitly overridden;
they must not be described as backtests of the relaxed live policy.

Unchanged: live broker maximum spread and spread-to-analysis-target checks,
mandatory SL, grid/minimum-distance checks, news, quote freshness, tick coverage,
3/5/6 candle confirmation, same-direction profitable additions, fixed 0.01 lot,
four-position global cap, demo identity and provisional-profile account binding.
Advisor 1 protected files remain untouched. No manual order is forced.

77 targeted tests passed, including disabled cost veto, warning telemetry and
restoration of the veto by setting the configuration flag to true.

Start only if stopped:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& ".\.venv-audit\Scripts\python.exe" -u -B .\run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --scalp-timeframe AUTO --smc-policy observe --allow-provisional-costs --s30-cost-report data/runtime/s5_provisional_demo_costs.json
```
