# Session-aware XAUUSD scalping system

Research and implementation: 26 October 2026. Demo only. This assembles existing
execution safeguards with new schedule context and risk-aware candidate routing;
it is not a validated profitable HFT strategy or a promise of signal accuracy.

## Market model and sources

- [World Gold Council market structure](https://www.gold.org/gold-market-structure/global-gold-market):
  London OTC, US futures and Shanghai are important centres. Our broker's XAUUSD
  quote is not a consolidated global exchange order book. Quote counts cannot
  substitute for actual aggressor volume or limit-order queues.
- [World Gold Council drivers](https://www.gold.org/goldhub/research/what-drives-gold):
  currencies, rates, inflation, investment demand and risk interact. These are
  context, not a deterministic seconds-level BUY/SELL rule. A monthly/long-term
  explanatory relationship cannot be assumed to time a five-second trade.
- [LBMA auctions](https://www.lbma.org.uk/prices-and-data/about-lbma-daily-auction-prices):
  regular gold auction times are 10:30 and 15:00 London local time. Convert with
  Europe/London, not a permanent UTC offset. The next regular auction is marked
  as unverified against holidays; no auction-day price direction is inferred.
- [SGE regular sessions](https://en.sge.com.cn/eng_trading_ProductsIntroduce):
  the published day session is 09:00–15:30; regular night sessions span
  20:00–02:30 Shanghai time, with trading-day/weekend conventions. The code
  handles the midnight crossing, including Friday night/Saturday morning, but
  does not claim a verified Chinese holiday calendar or universal product hours.
- [CME hours/holidays](https://www.cmegroup.com/trading-hours.html):
  schedules are contract-specific and holiday-sensitive. Some products are also
  covered by [24/7 developments](https://www.cmegroup.com/markets/trade-24-7).
  No blanket futures-hours table is imposed on the CFD account.
- [BLS release schedule](https://www.bls.gov/schedule/news_release/empsit.htm):
  release dates must come from verified calendars. A daily 08:30 New York clock
  marker alone would falsely label non-release days as news days. Existing
  economic-calendar/news policy remains unchanged; complete coverage is not
  newly guaranteed by this session layer.
- [MT5 symbol modes](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants):
  disabled, long-only, short-only, close-only and full permissions differ.
  They are now checked before a main horizon entry and again during final
  preflight. This is an entry restriction, not a veto on protective closures.

## Assembled decision path

1. **Data:** broker bid/ask ticks, timestamp/freshness validation, completed
   seconds candles with real coverage; no fabricated missing ticks.
2. **Context:** London/New York local-time liquidity windows (08:00–17:00
   heuristics, not venue hours), Shanghai regular day/night reference, overlap,
   upcoming regular gold auction and New York rollover-watch warning.
   DST uses IANA zoneinfo. The UK/US change clocks on different dates, so their
   overlap must not be computed from one fixed UTC table. Missing timezone data
   yields unavailable context, not guessed offsets.
3. **Techniques/regimes:** the existing continuation entry uses completed fast
   candles plus executable bid/ask follow-through. Existing pullback/breakout
   detectors are catalogued for trend regimes and sweep/reclaim for range or
   transition regimes. Those alternatives remain research-only: prior tests did
   not establish a profitable implementation, so combining them by majority vote
   would not create evidence. No research pattern may send a broker order.
4. **Frequency selection:** AUTO evaluates S5, S15 and S30 in order. Explicit
   MICRO can also evaluate S1; it is not promoted to the default. In addition
   to data, direction, micro-confirmation and cost checks, candidate selection
   now values the proposed structural stop through MT5 at exactly 0.01 lot.
   An over-budget candidate is excluded before selection, allowing assessment
   of another eligible period. Previously the first pattern-feasible period
   could be repeatedly selected and then rejected by the broker risk gate,
   hiding a potentially feasible alternative. Missing risk valuation fails
   closed. The stop is quantized to broker ticks, never squeezed to force entry.
   Held positions keep their original period pinned.
5. **Authorization:** news policy, persistence, entry spacing, combined capacity,
   risk, spread, broker permissions, margin/order_check and final-quote preflight
   remain necessary. A contextual active centre is NOT permission to trade.
6. **Management:** broker SL and existing adaptive exit engine remain active;
   main close decisions notify the inverse. Same account, four combined slots,
   fixed 0.01 lot and no fixed broker TP remain unchanged.
7. **Learning evidence:** accepted entry journals now include market schedule
   and execution-plan tags, enabling subsequent broker-confirmed analysis by
   session and setup. No performance-based automatic lot escalation or online
   strategy promotion was introduced.

## New surfaces

- `services/research/gold_market_schedule.py`: explicit session context,
  permissions and live-versus-research technique plan.
- `services/research/gold_fast_selection.py`: broker-valued risk-aware candidate
  routing, with all original final-entry risk checks retained.
- Main dashboard: gold liquidity centres, London/New York overlap, next regular
  auction, rollover warning and explicit holiday/broker-calendar limitations.
- Main status: `market_schedule` and `market_execution_plan` in SCALP decision.
- Advisor1 and its protected dependencies are not modified.

## What is not established

This code does not implement a complete broker holiday/session feed, a trained
AI with calibrated probabilities, validated profitability, native institutional
HFT execution, or a target number of trades per hour. The current continuation
strategy still needs fresh executable-price evidence and prospective validation.
The previous sampled-tick markouts did not validate simply trading faster or
reversing every signal after costs. See `GOLD_ULTRASHORT_RESEARCH_20261026.md`.

The system maximizes **feasible candidate assessment**, not forced order count.
If no setup clears costs/risk, waiting is a valid outcome; it does not mean the
program failed to launch. More frequent opportunities require better data,
execution economics and validated predictive edge—not removing those checks.

## Validation and deployment

182 targeted Python tests and the dashboard polling/render tests pass. Coverage
includes UK/US DST mismatch weeks, Shanghai midnight/weekend conventions,
auction UTC conversions, broker directional permissions, risk-unavailable and
over-budget selection, and held-period pinning. The updated main was loaded on
demo and its new schedule/plan fields and served dashboard were verified. The
separate inverse heartbeat remained fresh. All 18 protected Advisor1 files
matched their pre-existing hash baseline; the temporary deployment hold was
removed. No forward profitability or higher signal accuracy is claimed.
