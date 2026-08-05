# V6.3.5 Regime Consistency

## Runtime finding

The first V6.3.4 session closed 21 shadow trades for -$4.78. STRICT had only one
trade (-$0.04), so this is not enough evidence to tune profitability thresholds.
That STRICT trade nevertheless exposed two deterministic defects: it entered
while unified context explicitly reported `NO_TRADE`, and its learning profile
stored ADX as zero because the real field is `adx_m5`.

## Research interpretation

Federal Reserve studies find that high-frequency FX price discovery and the
relationship between flow and returns vary intraday and with liquidity. BIS
analysis similarly highlights time-of-day vulnerability, fragmented liquidity,
and algorithm suitability for current market conditions. Recent walk-forward
research continues to find that naive directional forecasts often fail after
costs, while regime, turnover and cost gates can improve defensive performance.

Sources reviewed include the Federal Reserve papers *Order Flow and Exchange
Rate Dynamics in Electronic Brokerage System Data*, *Rise of the Machines*,
*Transmission of Volatility and Trading Activity*, and *The Evolution of Price
Discovery in an Electronic Market*; BIS reports on FX execution algorithms and
the sterling flash event; Baillie and Bollerslev on intraday FX volatility; and
walk-forward studies of regime- and cost-aware prediction.

## Implemented scope

- STRICT and BALANCED block explicit `NO_TRADE` context.
- Their directional context, when non-neutral, must match the candidate.
- EXPLORATORY stays permissive to collect counterfactual evidence.
- ADX learning values come from `verified_market_context.adx_m5`.
- No session was disabled from this 21-trade sample; doing so would overfit.
- Shadow, approval, one-position, and real-account locks remain unchanged.
