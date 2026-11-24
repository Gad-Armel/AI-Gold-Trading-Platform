# Scalper Expert 3.21 — observation and engineering review

October 1, 2026. Compiled and installed in the connected demo MT5 terminal.
The 3.21 heartbeat and installed binary hash were verified. The existing safety
lock remains active. Installation is not evidence of profitable performance.
The live observation log is `data/research/scalper_321/forward_35s.jsonl` and its
accounting summary is `data/research/scalper_321/observation_review.json`.

## What the demo actually showed

The review started at 07:22:25 UTC. Automated read-only observations began at
07:26:32 UTC and finished at 08:11:53 UTC: **79 observations over 45.35 minutes**,
with a median interval of 35 seconds and no collection errors. One observation
caught the intentional MT5 restart; the other 78 were live. Fourteen observations
identified the installed 3.21 build. Total review work took about 50 minutes.
The first seven 3.20 positions produced:

| Measure | Observed result |
|---|---:|
| Completed positions | 7 |
| Net result | -$3.96 |
| Winners | 2 / 7 (28.57%) |
| Mean winner | $0.255 |
| Mean loser | -$0.894 |
| Profit factor | 0.114 |
| Break-even win rate at those observed payoffs | 77.81% |

These seven trades are too few to estimate a durable edge. The broader 27-position
history had a 37.0% win rate, 0.44 profit factor and -$10.05 net. Increasing
frequency without improving expectancy would magnify the existing losses.

The 10:29:34 broker-time BUY at 4158.48 closed at 4157.83 one second later, losing
$0.65. The execution event identifies an account emergency close after the rolling
loss protector triggered. The code checked the $2 per-trade allowance but failed
to reserve the remaining $5 rolling allowance. Entry and protection were therefore
working against each other near that limit. This is a verified engineering defect.

The market also changed direction repeatedly. The two winning buys followed five
closed M1 candles with net changes of +$1.66 and +$2.63. Two losing buys followed
five-minute declines of $4.64 and $5.11. This motivates a short-horizon counterflow
test; it does **not** establish that a new tick filter would have prevented either
loss. Minute candles cannot reconstruct the order of intrabar quotes. A subsequent
read-only tick audit succeeded for all 27 completed positions; its files are in
`data/research/scalper_321/audit_before`. Four of the five 3.20 losers never showed
a positive result at the available executable-side quotes. The fifth reached
only +$0.15 before closing at -$1.08. The two winners reached +$0.47 and +$0.49 and
closed at +$0.29 and +$0.22. This supports prioritizing entries rather than assuming
an earlier profit exit would fix the losers. Historical quote maxima are not
necessarily achievable fills and are not used as hindsight exit targets.

The observed broker acknowledgement EWMA was about 132 ms; tick computation was
much shorter. The main problem is not a slow dashboard. It is selecting moves
that can pay their costs, controlling exposure and avoiding small-win/large-loss
churn. Score values are heuristic evidence, not calibrated win probabilities.

## Changes and priority

1. **Risk consistency.** A new trade plus already reserved stop exposure must fit
   the remaining rolling allowance (`limit + realized P&L`). Entry fees, stop loss
   and slippage reserves remain in planned exposure. Stops are not squeezed into
   an unsuitable tiny distance to force an entry. The $5 breaker and its existing
   persistent 24-hour lock remain intact. Gaps/slippage can still exceed estimates.
2. **Short-term confirmation.** Four distinct sampled quotes and at least the
   configured confirmation duration remain required. A score dip of at most four
   points may retain confirmation for at most 250 ms, only after all structural
   checks pass. The latest signal must fully qualify. Reversals, hard vetoes,
   pauses, stale data and execution blocks clear confirmation. Sparse consecutive
   valid quotes are not mistaken for a weak signal.
3. **Counterflow selection.** A strong opposing 20-second move rejects a brief
   three-second bounce unless the eight-second flow demonstrates a stronger
   reversal. This uses quotes, not a mandatory H1/M15 alignment. It is a testable
   heuristic, not a proven profit improvement. `UseCounterflowGuard` and
   `UseConfirmationGrace` can be disabled for controlled comparisons.
4. **Auditability.** The browser shows rolling realized P&L, remaining allowance
   before reservations, loss streak, cooldown seconds, hourly entries and live
   confirmation progress. Cooldown and hourly-cap messages are separate. Submitted
   entries record score, spread, ATR, three flow pressures and remaining risk in
   the MT5 log and dashboard events. Session adaptation uses the 3.21 cohort only;
   account risk and aggregate performance still include older trades.
5. **Execution and exits.** Fixed 0.01 lot, maximum three account positions/orders,
   asynchronous reconciliation, cost/spread checks, protective broker SL, adaptive
   profit giveback and rapid re-entry after a confirmed profitable close remain.
   No unverified tightening of every winning exit was added to inflate win rate.

All work uses local/free tools. No paid API, indicator or external model was added.
Gold Advisor 1's 18 protected files match the original hash inventory.

## Validation and limits

- Five MQL5 programs: zero compilation errors and zero warnings.
- Native Strategy Tester **mathematical mode**: 198 checks, zero failures.
- Saved 24-hour broker quote replay: 285,799 samples. Neutral-context confirmation
  episodes: 459 strict versus 467 with bounded grace. These are overlapping signal
  episodes, **not executed trades or a profitability backtest**. This comparison
  isolates confirmation; it does not measure the combined counterflow policy.
- Dashboard transport/control regression suite: 46 tests passed.
- Observation-accounting regression suite: five tests passed, covering duplicate
  fills, partial exits, manual trades and entries leaving the rolling feed.
- Actual dashboard JavaScript with a DOM test double: eight checks passed.
  This validates text/control state, not a pixel-level browser rendering test.
- Full historical EA test: not completed. Copying the connected terminal's
  history cache failed because MT5 holds the `.hcc` file open.
- Detailed MT5/Python tick extraction: completed for 27 closed positions after an
  initial approval-service usage error cleared. It is read-only and sent zero
  orders. MFE/MAE use historical bid for BUY exits and ask for SELL exits, with
  recorded fees, restricted to the actual holding interval.
- Live 3.21 deployment: verified around 08:03 UTC, including matching installed
  binary, fresh telemetry and unchanged safety-lock expiry. New order execution
  is not validated: the prior build tripped its existing rolling-loss lock.
  After deployment, observed tick processing averaged about 25 microseconds.

The old build's lock expires on **October 2 at 10:29:35 broker time**, corresponding
to **08:29:35 Lagos time** for the observed UTC+3 server. Restarting/upgrading must
not erase that lock. Entry eligibility after expiry still depends on all normal
checks and remaining risk. The next useful evaluation is an untouched forward
sample across sessions, measuring net expectancy, drawdown, fees, rejected signals
and actual fill quality—not merely trade count or win percentage.

## Research checked

The [MQL5 event documentation](https://www.mql5.com/en/docs/event_handlers/ontick)
states that new tick events are not queued while a tick event is already queued
or processing. Heavy history/calendar work therefore stays outside `OnTick`;
the new confirmation uses bounded state and existing sampled quotes.

The [ISM release calendar](https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/)
lists October 1 for manufacturing PMI, and the
[BLS employment schedule](https://www.bls.gov/schedule/2026/home.htm) lists October 2,
08:30 Eastern, for the September employment report. These are scheduled risks,
not known future outcomes. Native calendar freshness and price response remain
separate from direction prediction. The
[MQL5 calendar reference](https://www.mql5.com/en/docs/calendar) documents broker
server-time handling; future actual values remain unavailable until released.

## Install and run

Version 3.21 is already installed. For a later reinstall/relaunch, close MT5 using
**File > Exit** first. The persistent safety lock survives these commands.

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\install_gold_scalp.ps1 -DataDirectory "$env:APPDATA\MetaQuotes\Terminal\F762D69EEEA9B4430D7F17C82167C844"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_scalp_mt5.ps1 -DemoOrders
```

Browser dashboards, including the unchanged Advisor 1 transport:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\restart_gold_dashboards.ps1
```

Main: `http://127.0.0.1:8766/`. Advisor 1: `http://127.0.0.1:8766/advisor`.
Refresh with Ctrl+F5. Check that the main identity reads **EA 3.21**; until then,
the old installed strategy is still running. VS Code does not need to stay open.
