# Scalper Expert 3.10 — review of Gemini / DeepSeek proposals

Updated September 30, 2026. Main source: `mql5/Experts/GoldScalpAI/GoldScalpAI.mq5`.
This is an experimental, rule-based adaptive demo scalper. Evidence scores are
not calibrated probabilities; the observational online model is not proof of an edge.

## What was retained

| Proposal | Implementation / decision |
| --- | --- |
| Tick-led continuous scalp | Existing 3/8-second bid/ask flow retained; new 1-second micro flow supports exits and strong opposite re-entry. No requirement to maintain a position constantly. |
| Acceleration | Bounded ±4 evidence adjustment from direction-normalized fast versus slow quote velocity. It cannot override risk, spread, cost, news or execution checks. |
| Early reversal exit | An armed net winner can exit after opposing micro pressure persists 750 ms, with sufficient efficiency, meaningful profit retreat and decelerating broader flow. |
| One-third giveback | Existing 33.33% net-profit peak trigger and protective broker-stop tightening retained, subject to a noise floor. Existing ATR BE/trailing remains active. |
| Rapid opposite re-entry | Requires a matching broker exit event, flat account, reconciled history, no unresolved deal request, new quotes and evidence six points above the ordinary threshold. Minimum rearm 750 ms, increasing with observed acknowledgement latency up to 3 s. Authorization expires after 10 s. All ordinary risk/environment checks still apply. |
| Session learning | Existing bounded evidence adjustment retained, with at least 20 fully closed positions per session. New `ScalperExpert310:S0..3` comments isolate this policy's outcomes. Historical account P&L and risk locks are retained. |
| Browser controls | Pause / Resume entries and confirmed Close All for the entire displayed demo account. Native acknowledgement distinguishes queued, accepted, completed and rejected states. No direct buy/sell endpoint. |
| Execution diagnostics | Measured request acknowledgement EWMA/max, signed latest fill slippage, quote velocity, sampled observation rate, micro state and ATR/reference range in the browser. No measured fills means no invented latency figure. |

The profit trigger cannot guarantee retaining exactly two-thirds of the peak:
gaps, spreads, stops/freeze levels and execution slippage affect actual fills.
BE at or beyond entry also cannot guarantee a risk-free outcome.

## What was excluded, and why

- Lot escalation: **0.01 lot fixed, maximum three account positions/orders**.
- Permanent market exposure and removing cost limits: these can multiply spread
  losses without creating predictive information. The $2 planned trade / $4
  aggregate limits, $5 rolling-loss breaker and 3% daily equity protection remain.
- Crypto Binance depth as gold order flow: it is not the broker's XAUUSD executable
  liquidity. OTC depth and quote tick counts are not a consolidated gold exchange tape.
- Commercial bot claims, guaranteed win rates and unmeasured sub-100 ms execution:
  no supporting evidence was supplied. No paid services were introduced.
- Unconditional IOC: broker-supported fill policy remains authoritative; IOC can
  partially fill. Existing reservation/reconciliation handles uncertain requests.
- More slow mandatory indicator confirmations: this is a scalp policy. Existing
  higher-timeframe and Advisor 1 context remain weighted evidence.

## Browser control contract

Server binds to loopback only. Commands require the matching Host/Origin, a
per-server random token, explicit feed and current EA instance. Atomic CSV
mailboxes expire after ten seconds; duplicates/in-flight commands are refused.
The native EA revalidates timestamps, instance, action and full file format.
Polling is on its 250 ms timer, not a network call inside OnTick.

Pause stops entries and preserves exits. Resume cannot clear an equity/rolling-loss
lock or interrupt liquidation. Close All requires demo execution and affects all
account positions/orders, including manual trades and other symbols. Entries remain
paused after completion. Broker refusals keep liquidation active; the browser does
not claim completion while positions or unresolved requests remain.

Closing the browser does not stop MT5. The local Python server must remain running
for browser data/controls and Advisor 1 supervision. VS Code need not remain open.
Advisor 1 retains a separate analysis page; its 18 protected files are unchanged.

## Measured results and validation

Version 3.00 forward demo, September 29: **15 completed positions, 5 wins / 10 losses,
net −$4.90, Profit Factor 0.547**, mean holding time 34.2 s. All were in the New York
UTC bucket. Mean win $1.182; mean loss −$1.081. The rolling-loss breaker activated
while floating + realized loss crossed its limit. Final realized loss after closing
was −$4.90. The account was flat at review.

This is a small losing sample, not evidence that more trades improve performance.
The demo balance is $23,643.11, **not the intended $100 starting account**. Testing
on this demo does not establish margin feasibility or drawdown behaviour at $100.
The audit is `data/research/scalper_expert3/forward_300_20260930.json`.

Functional validation: all five MQL5 programs compile with **0 errors / 0 warnings**;
**150 native checks**, **44 Python tests**, and **10 browser control checks** pass.
Native checks include CSV round-trip/rejection, rotation timing, execution state,
profit protection and safety invariants. Browser checks use the actual JS with
stubbed transport; no fake orders reach MT5. The optional broker quote diagnostic
processed 285,799 observations; its overlapping signal counts are not trades or
a full profitability backtest. It does not validate the new exit policy's returns.

3.10 still needs forward demo outcomes and a complete broker real-tick Strategy
Tester run with commissions and realistic execution delay. Preserve the current
safety lock; do not use reinstall/restart to erase losses or resume early.
Validation artifacts: `mql5/validation/scalper-expert-310-validation.json`.

## Restart commands

After closing MT5 normally with **File > Exit**, start the main bot:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_scalp_mt5.ps1 -DemoOrders
```

In a separate PowerShell, restart both browser dashboards:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\restart_gold_dashboards.ps1
```

Keep that PowerShell running. Main: http://127.0.0.1:8766/ ;
Advisor 1: http://127.0.0.1:8766/advisor . Restarting preserves safety locks.

## Primary references

- [MetaQuotes OnTick](https://www.mql5.com/en/docs/event_handlers/ontick): event
  coalescing makes bounded handlers important; this is retail terminal scalping,
  not exchange-colocated high-frequency execution.
- [MetaQuotes OrderSendAsync](https://www.mql5.com/en/docs/trading/ordersendasync):
  submission is distinct from broker execution; transaction correlation is required.
- [MetaQuotes filling policies](https://www.mql5.com/en/docs/constants/tradingconstants/orderproperties):
  FOK/IOC and partial-fill behaviour depend on execution/filling support.
- [MT5 Depth of Market](https://www.metatrader5.com/en/terminal/help/trading/depth_of_market)
  and [price data](https://www.metatrader5.com/en/terminal/help/trading_advanced/price_data):
  OTC broker quotes/depth differ from exchange trade/volume information.
- [CopyTicks](https://www.mql5.com/en/docs/series/copyticks): broker tick data access;
  sampled observations in this EA are explicitly labelled, not called traded volume.
