# V6.3.6 Tick-Horizon Fast Research

## Forward result that motivated the experiment

The reviewed V6.3.5 process session closed 12 EXPLORATORY trades for -$4.07.
STRICT and BALANCED opened no positions because structure did not confirm. This
does not demonstrate that faster trading is profitable; it shows the permissive
counterfactual lane remained negative after spread.

## Data and timeframe design

MetaTrader 5 standard timeframes start at M1. Official Python integration does,
however, expose timestamped bid/ask ticks. FAST therefore uses the existing raw
tick recorder to form rolling 1-second, 3-second and 5-second features. These
are observation windows, not falsely labelled broker candles.

Federal Reserve research has used one-second FX prices but commonly aggregates
transaction information to one- or five-minute intervals. Its findings show
that order-flow impact is time-varying and liquidity-dependent. BIS research
also emphasizes the cost of latency competition and very small per-trade
margins. Consequently, faster sampling is treated as an experiment rather than
evidence of faster profitability.

## FAST acceptance rules

- 1-second and 5-second directional tick ratios and velocities must agree.
- The 3-second quote-flow proxy must agree with absolute magnitude >= 0.10.
- Spread <= $0.20 and spread/M1-ATR <= 0.15.
- Tick-data quality >= 0.75; micro confidence >= 0.55.
- `STALLED`, `DISLOCATED`, `NO_TRADE`, and opposing regimes are blocked.
- At least one structural family supports the trade with no opposite 2/3 vote.
- Maximum shadow hold is 15 seconds.
- FAST is never demo eligible and does not authorize STRICT.
