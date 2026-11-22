# Main demo bot live monitoring — October 8, 2026

The main bot was monitored through MT5, runtime status and its execution journal.
Recording began at 04:02:08 UTC (05:02:08 Lagos). Final measurements are in
[summary.json](summary.json); the complete record is in `observations.jsonl`.
The main bot remains running. Standalone Advisor 1 was not modified.

Final recording ended **06:07:18 UTC / 07:07:18 Lagos**, after **125.16 minutes**
and **499 observations**. There were **4 wins and 4 losses**, **-$6.49 realized**
($13.25 gross gains, $19.74 gross losses; profit factor 0.671). Main realized plus
floating P/L changed **-$6.13** from the recording baseline. Account equity
changed -$6.31; account and strategy baselines differ slightly. Maximum observed
account equity drawdown was $16.75. Overall recorded loop median was 234 ms,
p95 828 ms, with no advisor-error samples.

At the final direct runtime check (06:07:43 UTC), the bot was RUNNING with one
0.01-lot SCALP SELL, ticket 58814871315, floating +$0.50 and broker SL 4124.76.
This open result can change. [Performance chart](performance.png).

## Findings

The whole monitoring period remained negative at the two-hour checkpoint.
Strong candle evidence did not reliably identify a profitable entry: two early
buys near 04:12 followed a bearish completed M1 candle and subsequently stopped
for a combined $10.11 loss. Those entries preceded the new M1 timing check.
Another INTRADAY buy remained unsupported for nearly an hour before the added
confirmed neutral-thesis exit closed it at -$4.64.

The later SCALP entries produced three consecutive realized gains of $3.28,
$3.40 and $3.48, followed by a $4.99 broker-stop loss. That four-trade subset
earned $5.17, but it is neither a controlled comparison nor enough evidence of
lasting profitability. All results, including earlier losses and open positions,
are retained in the session summary and chart.

## Changes applied to the main bot

- Fixed quote-flow protection rejecting otherwise acceptable small broker clock skew.
- Fixed exit conviction saturating at the 15/100 entry floor.
- Aligned the SCALP spread ceiling with the existing $0.50 global limit; retained
  spread/target cost, price-zone and risk checks.
- Added fresh completed-M1 entry confirmation and a wait for explicitly opposing
  fresh micro-flow. Forming candles cannot confirm an entry.
- Prevented INTRADAY bypassing a pending leading SCALP two-M5-candle wait,
  including when that pending SCALP direction temporarily becomes neutral.
- Preserved exit pause and candle-confirmation state across main-bot restarts.
- Added a confirmed losing-position exit when two usable sources turn neutral
  and completed-candle momentum opposes the position beyond spread/ATR noise.
  Source outages alone cannot trigger this exit.
- Reused lane deal-history snapshots and cached unchanged completed-candle
  analysis in the main process. Current prices and levels still refresh.
- Reduced the target loop interval from 1.0 to 0.5 seconds. Actual processing
  occasionally exceeds that interval; it is not a latency guarantee.

The $5 individual broker stop, 0.01 lots and three-position cap remain. Broker
slippage can exceed nominal stop exposure, as shown by the early $5.05/$5.06
losses. Closing a position does not terminate the bot; new entries pause for
approximately 30 seconds and still require valid current signals.

## Timing and validation

An isolated read-only MT5 measurement found full candle analysis around 365 ms
versus a cache hit around 26 ms. The initial live cached sample had median loop
time 125 ms (11 samples), compared with 406 ms in 275 preceding observations.
These are different-time samples, not a controlled speed benchmark. Overall
session median and p95 are reported in `summary.json`.

Final relevant regression run: **143 tests passed**, covering candle-signal
parity, cache invalidation, entry momentum, neutral exits, quote flow, conviction,
broker demo execution, per-position stops, continuous operation, cooldown
recovery, broker clocks and candle confirmation. Tests verify software behavior;
they do not establish trading profitability.

## External context

[Investing.com technicals](https://www.investing.com/currencies/xau-usd-technical)
provided mixed timeframe readings and timestamps older than the live check.
[TradingView technicals](https://www.tradingview.com/symbols/XAUUSD/technicals/)
did not expose complete indicator values in the retrieved page. Neither was
treated as a fresh scalp execution signal. MT5 supplied executable prices.

The [official Fed calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
confirmed the September meeting minutes were released October 7. The retrieved
[DOL weekly release](https://www.dol.gov/ui/data.pdf) was dated October 1, so it
was not treated as a new October 8 release. The saved learned-model evaluation
was negative and not live-approved; that model was not enabled.

## Limits

This was a short demo observation with several sequential changes and a small
trade sample. There is no reliable causal estimate of improved win rate, no
proven profitable strategy and no guarantee that continued trading recovers
losses. The bot continues running after this observation; this report does not
imply that interactive monitoring continues after the session ends.
