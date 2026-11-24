# Four-position limit — 21 October 2026

User requested exactly 0.01 lot per trade and four simultaneous positions maximum.
The main SCALP lane and global configured limit are now four. Broker capacity
checks enforce at most four controlled positions and 0.04 lot aggregate exposure
across all controlled lanes, immediately before order submission. Larger-volume
existing positions consume capacity; no fifth order is permitted. Existing SL,
news, quote and addition safeguards are unchanged. Advisor 1 is untouched.

The dashboard subtitle now states four positions; already-running dashboard
processes need restarting to load changed HTML. The trading bot remains stopped
on the new account pending its explicit provisional-cost setup; this change does
not silently import old-account cost observations or submit calibration trades.

S5 startup syntax, only after cost/account readiness is verified and when stopped:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& ".\.venv-audit\Scripts\python.exe" -u -B .\run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --scalp-timeframe S5 --smc-policy observe
```
