# XAUUSD ultra-short EA / AI research

Research date: 26 October 2026. Scope: retail MT5 tick and S1/S5/S15/S30
execution. This is not a claim of institutional HFT capability or profitability.
Only public descriptions were inspected; no paid EA binary was downloaded,
decompiled, installed, or traded. Vendor pages describe claims, not verified
algorithms or independently reconciled returns.

## 1. Evidence hierarchy

1. MetaQuotes platform documentation establishes event and execution semantics.
2. Published research supports hypotheses and testing methods, with its original
   instrument/feed limitations preserved.
3. Product descriptions reveal design ideas; they do not establish an edge.
4. Reviews, profit screenshots, and short backtests are not grounds for changing
   live risk, selecting a model, or predicting future return.

## 2. Commercial EA comparison

| Public product | Described mechanism | Applicable idea | Not established / rejected |
| --- | --- | --- | --- |
| [GoldHFT MT5](https://www.mql5.com/en/market/product/109937) | Small neural network, frequent trading, periodic learning, configurable schedule | Evaluate broker-specific costs and time windows | The public overview does not expose reproducible weights, training labels or an independent audit; its short promotional backtest is not transferable evidence |
| [SD Gold HFT Scalper EA](https://www.mql5.com/en/market/product/177153) | Bid/ask bursts in second-based windows, spread control, stops/trailing | Quote-side confirmation, tick coverage, latency stress tests | Its recommendation of ideal zero-delay testing is insufficient for deployment; its zero-latency language cannot describe end-to-end broker execution |
| [HFT EA Gold Strategy](https://www.mql5.com/en/market/product/202945) | Responsive pending orders, broker-distance checks, trailing, request limiting | Respect stops/freeze levels, request budgets and hedging/netting semantics | Frequent pending-order amendments do not establish positive expectancy; do not import an untested order-chasing engine |
| [Scalper M1 Gold AI By June](https://www.mql5.com/en/market/product/173320) | Claimed adaptive modes, momentum/MTF confirmation and volatility exits | Separate normal and adverse execution conditions; validate changes chronologically | Public AI/self-tuning claims are not reproducible model evidence; no recovery sizing or confidence-based lot escalation adopted |

These are first-party seller statements, not recommendations to buy them.
No private strategy can be reliably reconstructed from its marketing overview.

## 3. What very short timeframe actually means

- [Native chart periods](https://www.mql5.com/en/docs/constants/chartconstants/enum_timeframes)
  begin at M1. Our seconds candles are built from tick history; changing the
  visible MT5 chart period does not accelerate our Python logic.
- [Event handling](https://www.mql5.com/en/docs/event_handlers) coalesces a new
  tick event when one is already queued or processing. Therefore OnTick callback
  counts are not tick counts, and switching to MQL5 alone does not prevent loss
  of intermediate observations.
- [CopyTicks](https://www.mql5.com/en/docs/series/copyticks) provides chronological
  tick arrays with millisecond timing and quote-change flags. Replay/history
  recovery must be separate from the latest-quote wake-up. The current bot
  already retrieves incremental history and refuses fabricated candle coverage.
- A [millisecond timer](https://www.mql5.com/en/docs/eventfunctions/eventsetmillisecondtimer)
  is not a guaranteed microsecond scheduler. It also shares event-queue limits.
- [OrderSend](https://www.mql5.com/en/docs/trading/ordersend) acceptance is not
  synonymous with a completed deal. [OrderSendAsync](https://www.mql5.com/en/docs/trading/OrderSendAsync)
  removes waiting in the caller, not broker latency. A native executor would
  require a transaction state machine, idempotent intent IDs and reconciliation.
  [Transaction events](https://www.mql5.com/en/docs/event_handlers/ontradetransaction)
  can arrive in an unexpected order. Do not blindly retry uncertain requests.

Inference for this project: improving correctness and measuring actual phase
latencies are prerequisites to a native low-latency rewrite. A nominal S1 signal
cannot promise one-second execution if source calculation or order handling
takes longer. No asynchronous sender or automatic real-money activation added.

## 4. Signal versus executable edge

For a buy, markout is exit bid minus entry ask minus round-trip commission and
adverse slippage price equivalents. For a sell it is entry bid minus exit ask
minus those costs. Do not subtract spread again; it is already in bid/ask prices.
Reversing the same entry/exit timestamps makes both legs pay costs; it is not an
exact negation of net P/L.

Our earlier review found 92 of the last 100 main entries failed the recorded
range-cost screen while that screen was warning-only. It is now enforced.
A recent candle's range is an affordability proxy, not a prediction of remaining
movement. Neither passing this screen nor three same-colour candles proves edge.

Midpoint changes can be driven by widening/narrowing spreads on one side. New
confirmation requires both bid and ask to advance in the proposed direction over
the existing six-second follow-through window. It remains a conservative
heuristic: it can reject some legitimate moves and does not estimate a win rate.
The existing micro-confirmation override reports a warning rather than secretly
enforcing this rule. Default demo configuration enforces it.

## 5. What the AI literature does and does not support

- [Gould and Bonart: queue imbalance](https://arxiv.org/abs/1512.03492) studies
  next-price prediction using actual limit-order-book queues on Nasdaq stocks.
  It does not validate a two-tick XAUUSD CFD strategy. Bid/ask quote counts cannot
  be renamed order-flow imbalance without queue and trade data.
- [Briola et al.: Deep Limit Order Book Forecasting](https://arxiv.org/abs/2403.09267)
  distinguishes forecast quality from actionable complete transactions. The
  instruments and order books differ from our broker feed. It supports evaluating
  executable outcomes rather than treating classification accuracy as profit.
- [Bailey et al.: backtest overfitting](https://escholarship.org/uc/item/4w1110bb)
  explains selection bias from strategy searches. Repeatedly tuning to a losing
  session, or picking the best of many S1 thresholds, is not reliable validation.

Accordingly, no random neural network, LLM-in-the-order-loop, PPO agent, fabricated
confidence probability, or online loss-recovery optimizer was installed. A future
trained model needs cost-net labels, purged chronological validation, calibration,
frozen features, dataset provenance and an unseen forward period before promotion.

For a future native AI executor, [MQL5 ONNX support](https://www.mql5.com/en/docs/onnx)
permits local inference from an exported model, without an HTTP/LLM call per tick.
[OnnxRun](https://www.mql5.com/en/docs/onnx/onnxrun) also exposes profiling options.
This is an implementation route, not an edge. Feature ordering, preprocessing,
input shapes and model version must match training exactly. MetaQuotes' own
[tester example](https://www.mql5.com/en/docs/onnx/onnx_test) separates directional
prediction checking from building a trading strategy; its EURUSD H1 example
must not be repurposed as proof of XAUUSD seconds-level profitability. No ONNX
model was promoted in this change because none was validated for our objective.

## 6. Implemented research tool and integration

`services/research/gold_s30_shadow.py`: executable bid/ask progress diagnostics
and confirmation shared by S1/S5/S15/S30 selection and final entry checks.
Main improvements automatically propagate to confirmed-fill inverse entries.

`tools/research_gold_micro_markouts.py`: offline diagnostic report on the local
semicolon tick CSV, with source SHA256, explicit round-trip cost assumptions,
entry and exit latency, no fabricated ticks across gaps, and a chronological
70/30 development/holdout boundary. Observations whose exits cross the boundary
are excluded from development. Reports 5/15/30-second markouts for raw and
filtered candidates on S1/S5/S15/S30, including the inverse outcome.

This is intentionally NOT a full backtest: observations overlap; there is no
broker fill probability, position cap, margin, protective SL/trailing simulation,
or production adaptive exit replay. Positive means would justify further work,
not automatic deployment. Counts are not independent-trade sample sizes. Once
read, the holdout becomes inspected data; future tuning needs a new unseen period.
Fast-entry cost profiles now fail closed after 24 hours; stale reports must be
replaced with fresh broker-specific evidence before S1/S5/S15/S30 entries can pass
the cost gate. This freshness rule does not improve or establish the signal edge.

Reproduce baseline cost assumptions (provisional, not measured guarantees):

```powershell
.\.venv-audit\Scripts\python.exe -B tools/research_gold_micro_markouts.py data/research/scalper_expert3/scalp_ticks.csv --commission-price 0.1 --slippage-price 0.2 --latency-seconds 0.25 --output data/research/gold_micro_markouts_20261026.json
```

Repeat separately with one-second latency and greater slippage, preserving all
reports rather than selecting only the most flattering scenario. The historical
file's absolute broker timestamp offset is not auto-corrected; this experiment
uses relative timing only and does not support session/news conclusions.
The adjacent `tick_capture.json` describes 285,799 sampled ticks out of 514,140
broker ticks for this 24-hour export. It is not a complete raw feed. Missing
coverage particularly constrains S1/S5 interpretation; do not infer full-feed
tick burst statistics or production fill performance from this sample.

## 7. Deployment criteria

### Local replay result

The 250 ms per-leg latency / 0.10 commission / 0.20 slippage run completed in
`data/research/gold_micro_markouts_20261026.json`. Costs and results are price
equivalents, NOT account-currency returns. Input SHA256:
`8a70fcfaea2bc8b73dc78c077cb91e98fb43834d40a2a637d42e60c8d3c20780`.

For the inspected holdout's 15-second raw-sequence markouts:

| Signal period | Overlapping observations | Main mean net price | Inverse mean net price |
| --- | ---: | ---: | ---: |
| S1 | 1,182 | -0.56074 | -0.66435 |
| S5 | 1,075 | -0.65603 | -0.54925 |
| S15 | 324 | -0.66750 | -0.54145 |
| S30 | 193 | -0.61005 | -0.60036 |

Filtered observations numbered only 0, 3, 3 and 2 respectively for that horizon.
These counts are far too small to validate a profitable filtered strategy.
The two S30 filtered observations had a positive mean, which is NOT sufficient
reason to choose S30 or optimize to that result. The raw-sequence comparison
does not show an edge in either direction under these assumptions. This is not
the production bot's realized performance or a backtest of its adaptive exits.
No new model or faster default was promoted based on this experiment.

The additional one-second per-leg latency / 0.10 commission / 0.40 slippage
scenario also completed in `data/research/gold_micro_markouts_stress_20261026.json`.
For the same 15-second horizon, raw holdout main/inverse means were respectively:
S1 -0.75750/-0.86223, S5 -0.85918/-0.74505, S15 -0.83644/-0.76542 and
S30 -0.79326/-0.81021. Filtered observation counts were 0/1/0/0. Both costs and
latency changed, so the difference cannot be attributed to latency alone. This
reinforces the lack of validated seconds-level edge in this sampled diagnostic;
it is not a prediction of actual future losses.

Validation: 164 targeted unit/integration tests pass, plus the dashboard polling
test. Tests include executable bid/ask pricing, both legs losing on a flat market,
entry/exit latency, missing future ticks, gaps, duplicates, invalid ordering,
one-sided spread changes, override diagnostics and the report CLI. The main
worker was reloaded on demo with AUTO retained; the inverse remained running.
All 18 protected Advisor1 files match their existing hash baseline.

[Real tick modelling](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation)
preserves changing intraminute spreads differently from generated ticks.
[Strategy Tester execution delay](https://www.metatrader5.com/en/terminal/help/algotrading/testing)
should be stressed rather than fixed at an ideal zero. For an eventual native EA,
test rejection, partial fill, reconnect, restart, SL gap and simultaneous-close
cases as well as returns. Native tester results are not a substitute for testing
our Python implementation.

Preserve demo-only, exactly 0.01 lot, four combined slots, mandatory broker SLs,
and separate inverse identity. Advisor1 and its dependencies remain unchanged.
Keep AUTO rather than forcing S1, and retain the existing freshness and cost
vetoes. No increase in trading frequency or profit improvement is promised.
