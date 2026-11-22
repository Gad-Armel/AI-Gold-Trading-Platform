# S5 demo mode and S1 research — 20 October 2026

## What changed

- Added explicit `--scalp-timeframe S5` to the Python main runner and controlled
  restart helper. Three/five/six completed five-second candles replace the
  corresponding thirty/fifteen-second confirmation history. First entry uses
  15 seconds of closed history; this is not a promise of an order every 15 seconds.
- S5 supplies direction, evidence and structural analysis levels independently
  of Advisor 1. The protected Advisor 1 calculations, runner and configuration
  are untouched. Existing Advisor 1/M1 adaptive exit context remains unchanged.
- S5 tick-history/advisor refresh targets 0.5 seconds, subject to processing and
  broker delays. The main loop target remains 0.5 seconds; no claim of measured
  sub-millisecond execution or institutional HFT is made.
- Tick-built S1 is available in the read-only observation tool, but not accepted
  by the live CLI or live gate. Current cadence and execution measurements do not
  justify one-second execution. No profitability claim is made for any period.
- Shorter bars require proportional coverage: no tick gap greater than one-third
  of the candle period (capped at five seconds), at least two observations per bar,
  no synthetic fill, and no future tick use. S1 retains at least twelve seconds
  of input so its six-second diagnostics are not truncated by short-bar lookback.
- S5 uses the same stop-grid alignment and broker stop-distance checks as S15/S30.
  Fast startup also checks USD account, 100-ounce contract, XAUUSD and 0.01 lot.

## Protections retained

Demo identity/arming, mandatory broker SL, TP=0 with dynamic exits, fixed 0.01 lot,
five positions globally, profitable-only same-direction additions, new completed
close after the previous entry for additions, signal persistence, re-entry and
churn guards, spread/cost/extension/news checks and quote freshness remain.
Previously disabled session loss stops are not silently re-enabled or claimed
to impose a monetary loss cap. Losses can still accumulate on demo.

The cost gate is not removed merely because short bars often move less than
round-trip costs. S5 may therefore trade less, not more, under some conditions.
All strategies remain experimental and unvalidated financially. Existing replay
tools default to S30 and must not be presented as an S5 backtest.

## Validation and deployment status

81 targeted tests passed, including S5 stages/boundaries, S1 diagnostic context,
S1 live rejection, proportional coverage, future ticks, policy identity, stop
alignment, previous fast-mode regressions and dashboard tests.

Deployment is BLOCKED by the actual broker connection, not a missing timeframe
option. The read-only probe returned `(-6, 'Terminal: Authorization failed')`;
the previous running S30 process reports disconnected terminal and stale quotes.
No process was stopped or new trading instance started in this change. Do not
claim S5 active until a successful demo preflight and live status confirm it.

Reconnect the same USD demo inside MT5 without sharing credentials. Then switch
the already-running bot safely:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\restart_monitored_main.ps1 -ScalpTimeframe S5
```

Fresh startup, ONLY if no trading worker is running:

```powershell
& ".\.venv-audit\Scripts\python.exe" -u -B .\run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --scalp-timeframe S5 --smc-policy observe
```

Read-only S1 observation after reconnecting:

```powershell
& ".\.venv-audit\Scripts\python.exe" -B tools/audit_gold_fast_shadow.py --period-seconds 1 --output data/research/goldhft_20261020/s1_snapshot.json
```

No manual entry should be sent to "prove" activity. Do not run native and Python
executors simultaneously. Respect missing-data and broker-authentication failures.
