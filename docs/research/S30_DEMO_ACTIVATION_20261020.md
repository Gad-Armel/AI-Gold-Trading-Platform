# S30 demo activation — 20 October 2026

Explicitly requested by the user despite the absence of demonstrated profitability.
Update: S30 now supplies its own entry direction and structural levels through
the S30_PRIMARY policy. Advisor 1 is retained as context and its original decision
continues to feed existing adaptive exits; agreement is not required for entry.
S30 evidence is the completed-body/range ratio, not a calibrated probability.
Update after inactivity review: in live S30 demo entry mode, weak six-second
follow-through is informational rather than an additional entry veto. Closed
3/5/6 S30 candles still determine direction. Recent tick coverage, actual quote
reversal/overextension, spread expansion and estimated-cost checks still block.
The standalone shadow/replay screen retains its stricter micro confirmation by
default; its results must not be described as a replay of this updated live policy.
52 targeted tests pass, including opposing Advisor 1, news veto and bad tick input.
`--scalp-timeframe S30` replaces the SCALP completed-M1 confirmation gate with
completed S30 candles built from tick history. Advisor 1 still determines direction
and analysis levels in the initial version; the update above supersedes that
direction requirement. Exits continue to use the existing adaptive M1 context.

First entry requires three S30 candles, second five, later additions six plus a
new completed S30 after the last entry. The six-second continuation, spread,
extension and cost screens remain enforced. Existing addition profitability,
global five-position cap, fixed 0.01 lot, mandatory SL, demo arming, news and other
entry/exit protections remain. No guarantee of higher trade frequency or profit.

Tick advisor/history refresh is at most one second apart in S30 mode instead of
the default five-second cadence. It is not institutional HFT.

The cost file `data/research/goldhft_20261020/s30_execution_costs.json` is checked
before startup and before each entry. Requires XAUUSD, USD, 0.01-lot scope,
30 matched complete fills minimum. At the user's request, calibration age above
24 hours is now informational only and does not block entries. The last valid
estimates continue to be used; malformed or future-dated evidence still blocks.
Estimates are
historical demo costs, not guaranteed future execution costs.

Refresh this evidence while keeping MT5 on the same USD demo account:

```powershell
& ".\.venv-audit\Scripts\python.exe" -B tools/validate_gold_fast.py --hours 2 --output data/research/goldhft_20261020/s30_execution_costs.json
```

Startup, only when stopped:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& ".\.venv-audit\Scripts\python.exe" -u -B run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --scalp-timeframe S30 --smc-policy observe
```

Omitting `--scalp-timeframe S30` restores default M1 on the next launch.
The launcher does not automatically promote strategies based on profitability.
24 targeted tests passed before activation. Advisor 1 protected files untouched.
