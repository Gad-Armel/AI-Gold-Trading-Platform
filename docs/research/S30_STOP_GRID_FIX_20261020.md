# S30 execution stop-grid fix — 20 October 2026

The live status contained an actual attempted-entry failure:
`STOP_GRID_BLOCK: Protective stop violates broker tick grid or minimum stop distance.`
This was a local safety rejection before order submission, not a confirmed broker
fill rejection. It demonstrated that not all inactivity was caused by waiting for
signals. At the inspection instant the separate S30 range/cost gate also blocked.

S30 structural stops combine midpoint candle highs/lows and an ATR buffer. Those
values need not fall on the broker's legal tick grid. The demo XAUUSD symbol was
read back with trade_tick_size 0.01 and trade_stops_level 0.

For S30_PRIMARY with ANALYSIS stops, broker execution now rounds the proposed stop
to the symbol's actual tick grid, inward: BUY up, SELL down. Rounding never widens
the proposed risk. Invalid stop sides, nonpositive prices, unavailable valuation
and minimum distances still fail closed; order_check remains mandatory. Other
entry modes and fixed-money stop calculations are unchanged. The original
analysis SL and actual submitted SL remain separately journalled.

The main dashboard now labels entry engine/timeframe and Advisor 1 context
separately. A strong analysis score is not an order instruction or a probability.
Reload http://127.0.0.1:8765/ with Ctrl+Shift+R to load the new presentation.
An already-running independent dashboard process must be restarted to load this
presentation change; its old in-memory HTML is not updated by a file edit.

69 targeted tests passed, including both stop directions, non-cent tick sizes,
minimum-distance rejection, all existing analysis-stop tests, S30 policy, and
dashboard tests. The existing demo worker was replaced at 17:19:53 Lagos time,
with zero managed positions at preflight. Log:
`logs/monitored-main-20261020T161953Z.stdout.log`.

No filters were relaxed in this change. Spread, cost, quote freshness, news,
global capacity, mandatory SL and fixed-lot controls remain. This repair does not
guarantee a trade or profitability when the remaining signal conditions fail.
