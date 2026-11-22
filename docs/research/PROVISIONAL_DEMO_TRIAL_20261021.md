# User-authorized provisional-cost S5 demo trial

The new demo has no XAUUSD execution history. The user explicitly approved a
trial with assumed costs, fixed 0.01 lot and four positions maximum. No measured
fills are fabricated and old-account measurements are not used for this trial.

`tools/prepare_demo_provisional_costs.py` writes an account-fingerprinted USD demo
profile to `data/runtime/s5_provisional_demo_costs.json`. Commission 0.10 and
slippage 0.20 are provisional round-trip XAUUSD price equivalents, not measured
fees, not profit predictions and not guaranteed worst-case costs. Current spread
is added separately. Profile keeps `available=false` and `reconciled_pairs=0`.

Use requires `--allow-provisional-costs` and the exact matching demo identity.
Startup and every entry gate check that binding. Live, changed-account, missing
identity, missing opt-in and invalid-cost profiles fail closed. No expiry entry
block is reintroduced. Future cost recalibration must use actual matched fills;
this trial does not automatically promote assumptions to measured data.

72 targeted tests passed, including four provisional-profile tests for opt-in,
account identity, real-account rejection and invalid estimates. Advisor 1 protected
files are not modified. Existing SL, quote, news, cost feasibility and addition
protections remain. No guarantee of a trade or profitability.

Safely replace an existing main worker:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\restart_monitored_main.ps1 -ScalpTimeframe S5 -AllowProvisionalCosts
```

Start only if stopped:

```powershell
& ".\.venv-audit\Scripts\python.exe" -u -B .\run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --scalp-timeframe S5 --smc-policy observe --allow-provisional-costs --s30-cost-report data/runtime/s5_provisional_demo_costs.json
```
