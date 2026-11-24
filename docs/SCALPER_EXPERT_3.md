# Scalper Expert 3.00

Historical policy note. Current update: [Scalper Expert 3.10](SCALPER_EXPERT_310.md).

The main native EA remains `GoldScalpAI.ex5` for installation compatibility. Its
new default policy and browser name are **Scalper Expert**. Gold Advisor 1's
18 protected source files and separate analysis dashboard are unchanged.

## Why the previous policy rarely qualified

The previous policy required a 13:00–16:00 UTC session, M1/M5/M15/H1 alignment,
Advisor 1 approval, above-average closed-candle volume and a spread below $0.30.
These gates could all reject a viable short-lived movement independently.
The 24-hour broker capture for this revision contained 514,140 ticks, sampled to
285,799 observations at no more than ten per second. 61.70% of sampled spreads
exceeded $0.30; the median was $0.32. This is a quote diagnostic, not evidence
that trades at wider spreads would have been profitable.

## New decision policy

- Executable bid/ask movement over 3 and 8 seconds leads the decision. Both quote
  sides must move: a widening spread alone cannot manufacture momentum.
- Fast pressure, slower pressure, path efficiency, M1/M5/M15/H1 directions,
  relative volume and fresh Advisor 1 direction contribute to a bounded evidence
  score. The default qualifying score is 62/100 with two seconds of confirmation.
  The score is hand-designed evidence, **not a probability of winning**.
- Advisor 1 is context by default. WAIT does not veto a scalp. An explicit
  `Advisor1Mode=1` restores mandatory approval if desired. Intraday and swing
  analysis remain available in Advisor 1, but do not control scalp entries.
- Broker trading hours are eligible on weekdays, except 21:00–23:00 UTC rollover.
  The fixed London/NY-only entry restriction is removed in ExpertScalpMode.
- Maximum spread is $0.60, subject to a 1.8x rolling spread limit and 0.40 ATR
  limit. Estimated spread + commission + two slippage allowances must fit within
  45% of a bounded movement estimate. This estimate is a heuristic, not a
  guaranteed excursion or a validated expected return.
- A live failed breakout, extreme extension, stale quotes, missing news,
  high-impact USD news window, extreme bar expansion and account safety locks
  still prevent entries. Low closed-bar volume is no longer a 1.05x requirement;
  the minimum is 0.35x, with volume also contributing to the score.
- Eight seconds minimum between entries/exits, at most 36 entries per hour.
  A new position can only add to an existing same-direction winner whose broker
  stop has reached entry or better. No averaging down or opposite-side stacking.

## Net-profit management

Each position records its peak executable-side P&L, less the configured estimated
round-trip commission. Spread is already reflected in that P&L; it is not
subtracted again. The default profit guard arms above the larger of $0.35 and
twice an ATR/spread/slippage noise allowance. After arming, the exit trigger is
peak net profit minus the larger of one-third of that peak and the noise allowance.
For example, a $3 peak with a small noise allowance creates a $2 exit trigger.
This does **not** guarantee a $2 fill: gaps, liquidity and slippage still matter.

Profitable confirmed reversals can exit before this trigger. A failed impulse
can cut a losing trade before its broker SL. Winners can continue without a fixed
TP; broker breakeven and trailing stops tighten as profit grows. MaxHoldMinutes
only closes stagnant trades, not a sufficiently profitable runner. No position
is intentionally closed merely because an arbitrary profit target was reached.

The browser position table shows peak estimated net profit, whether protection
is armed, and its current exit floor. The main bot's existing P&L column includes
swap and excludes commissions; the guard estimate is separately labelled.

## Session adaptation

UTC buckets: Asia 23:00–07:00; London 07:00–12:00; overlap 12:00–16:00; New York
16:00–21:00. These are fixed operational buckets, not exchange opening calendars.
The entry order comment records its UTC bucket, avoiding later broker DST inference.
Only fully closed Scalper Expert positions, including commissions, swap and fees,
are used. Missing/replaced broker comments cannot be used to infer a bucket.

After at least 20 completed positions in a bucket, mean P&L and its variability
can lower the score threshold by four for consistently positive results or raise
it by eight for consistently negative results. The latter also adds 12 seconds
to re-entry spacing. Otherwise the threshold stays neutral. This bounded heuristic
does not establish a statistically independent or out-of-sample session edge.
The dashboard shows samples and net P&L; no session is called profitable in advance.

## Limits and execution

Demo USD hedging accounts only; exactly 0.01 lot and at most three account
positions/orders. Planned risk remains at most $2 per position, $4 aggregate,
with the existing $5 rolling-loss breaker and 3% daily equity protector.
An ATR stop may be capped to the affordable risk distance only when it still
clears a structural floor of 0.30 ATR, twice the spread and broker minimum distance.
If it cannot fit, the trade is skipped. Stops cannot guarantee maximum realized loss.

Indicators, news files, history reconstruction, session outcomes, browser exports
and peak persistence run on timers. Peak persistence updates once per second;
a sudden process crash can lose the last second's peak. Tick handling uses bounded
buffers and the existing asynchronous request/reservation/reconciliation logic.
Ambiguous entry acknowledgements are never blindly retried.

## Run / restart

Close MT5 using File > Exit before restarting the main EA:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_scalp_mt5.ps1 -DemoOrders
```

Restart/open the two browser dashboards separately:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\restart_gold_dashboards.ps1
```

Main: http://127.0.0.1:8766/ ; Advisor 1: http://127.0.0.1:8766/advisor

## Validation and remaining evidence

September 29 run: all five programs compiled with zero errors/warnings;
116 native checks and 29 Python dashboard/transport tests passed. The native
diagnostic processed 285,799 broker observations across 24 hours: 31,543 raw
3/8-second impulse observations, of which 8,648 reached score 62 with neutral
trend/advisor context. These counts overlap in time and must not be called trades.
The installed 3.00 binary matched the compiled build; both browser feeds were live.
See `mql5/validation/scalper-expert-300-validation.json` for the recorded checks.

Native deterministic tests cover score direction, countertrend context, tick
readiness, net-profit giveback, noise arming, session boundaries/adaptation, and
affordable-stop rejection, alongside the existing execution/safety tests.
An optional real-tick replay exercises the actual native flow and score helpers.
Its counts are overlapping qualifying observations, **not orders or a profitability
backtest**. It does not replay the complete news, indicator, account or broker pipeline.
Forward demo outcomes and full broker real-tick Strategy Tester runs with realistic
commission and execution delays remain necessary to measure profitability.

Primary implementation references:

- [MetaQuotes OnTick event handling](https://www.mql5.com/en/docs/event_handlers/ontick):
  events are sequential and new ticks can be coalesced while a handler is busy.
- [MetaQuotes OrderSendAsync](https://www.mql5.com/en/docs/trading/ordersendasync):
  request acceptance is distinct from broker execution; track transactions.
- [MetaTrader Strategy Tester](https://www.metatrader5.com/en/terminal/help/algotrading/testing):
  real ticks, commissions and simulated execution delay matter for evaluation.
- [MetaQuotes tick-range API](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py):
  read-only tick capture used by the diagnostic exporter.
