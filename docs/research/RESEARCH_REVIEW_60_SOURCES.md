# V6.1 Scalping Bot Research Review — 60 Sources

This review combines official platform documentation, gold-market references, academic microstructure and validation papers, free-data API documentation, and educational tutorials/videos. The goal was not to copy a generic strategy, but to identify production rules that apply to a retail MT5 XAUUSD scalper with free or low-cost data.

## Practical conclusions adopted in V6

1. **MT5 bid/ask ticks are the execution source of truth.** External free APIs are too slow, differently timestamped, or differently instrumented to replace the broker quote.
2. **Transaction costs are part of the strategy.** A score that predicts direction but cannot overcome spread, slippage and the target/stop geometry has no tradable edge.
3. **The earlier bot overtraded late locations.** The uploaded sample was positive only in the lowest spread band and near VWAP; V6 starts with a strict cost/location hypothesis and records broader conditions in shadow mode.
4. **Validation must be chronological.** Random train/test splits leak market regimes. V6 requires walk-forward folds, recent performance, bootstrap uncertainty and an expiring approval artifact.
5. **Triple barriers are better research labels than “next candle up/down.”** They reflect target, stop and maximum holding time using executable bid/ask prices.
6. **Complex AI is postponed until enough labeled data exist.** With only 59 matched trades, a large neural model would mostly memorize noise. V6 first collects several hundred live shadow outcomes.
7. **Macro APIs are context-only.** BLS, FRED, BEA, Finnhub and Alpha Vantage can improve macro regime or news protection, but they do not time sub-second entries.
8. **One position precedes pyramiding.** A second position is disabled until the approved first-position strategy proves a positive demo edge.

## A. Official MetaTrader 5 execution and data documentation

1. MetaTrader 5 Python `order_send` — https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py  
   Use a fully specified trade request and inspect the returned retcode; never assume submission equals fill.
2. MetaTrader 5 Python `order_check` — https://www.mql5.com/en/docs/python_metatrader5/mt5ordercheck_py  
   Preflight margin and request validity immediately before sending.
3. MQL5 book: checking and sending an order — https://www.mql5.com/en/book/advanced/python/python_ordercheck_ordersend  
   Reinforces the separation between validation and execution.
4. `symbol_info_tick` — https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py  
   Fetch a fresh broker tick immediately before an order.
5. `copy_ticks_from` — https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksfrom_py  
   Tick times are UTC; correct cursor handling and flags are essential.
6. `copy_rates_range` — https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py  
   Candle ranges also use UTC; avoid local-time leakage.
7. `order_calc_profit` — https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py  
   Prefer the broker symbol/account calculation over a hard-coded contract-size formula.
8. `positions_get` — https://www.mql5.com/en/docs/python_metatrader5/mt5positionsget_py  
   Reconcile open positions by symbol and magic number before every new entry.
9. `history_deals_get` — https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py  
   Reconcile realized P/L including commission, swap and fees.
10. `initialize` — https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py  
    Terminal/account initialization must be explicit and checked.
11. MetaTrader 5 strategy testing overview — https://www.metatrader5.com/en/terminal/help/algotrading/testing  
    Testing quality depends on data mode and realistic execution assumptions.
12. MetaTrader 5 testing report — https://www.metatrader5.com/en/terminal/help/algotrading/testing_report  
    Review drawdown, trade distribution, sequences and robustness, not net profit alone.

## B. Gold market structure and liquidity

13. CME Gold futures overview — https://www.cmegroup.com/markets/metals/precious/gold.html  
    GC is a central price-discovery venue with deep but time-varying liquidity.
14. CME Micro Gold overview — https://www.cmegroup.com/markets/metals/precious/e-micro-gold.html  
    Micro contracts provide transparent smaller exposure and are useful as a cross-market context reference.
15. CME Gold futures education — https://www.cmegroup.com/markets/metals/precious/gold-futures.html  
    Gold trades nearly around the clock, but continuous access does not imply equal liquidity all day.
16. CME trading COMEX gold and silver — https://www.cmegroup.com/education/articles-and-reports/trading-comex-gold-and-silver  
    Session timing and settlement windows matter for spreads and volatility.
17. CME 1-ounce gold product lesson — https://www.cmegroup.com/education/lessons/1-ounce-gold-futures-product-overview  
    Contract tick size and execution granularity influence short-horizon economics.
18. World Gold Council market size and structure — https://www.gold.org/goldhub/research/market-primer/gold-market-primer-market-size-and-structure  
    Gold is globally liquid, but turnover is distributed across OTC and exchanges.
19. World Gold Council global gold market — https://www.gold.org/gold-market-structure/global-gold-market  
    London OTC, US futures and Shanghai are the dominant hubs.
20. World Gold Council market structure and flows — https://www.gold.org/about-gold/market-structure-and-flows  
    Cross-venue flows can alter intraday price behavior.
21. World Gold Council gold demand trends — https://www.gold.org/goldhub/research/gold-demand-trends  
    Macro and investment-demand regimes can change gold volatility.
22. World Gold Council increased transparency on gold trading — https://www.gold.org/goldhub/research/market-update/increased-transparency-on-gold-trading  
    Observable turnover supports using liquidity-aware session filters.

## C. Transaction costs, execution and market microstructure

23. Azencott et al., Real-time Transaction Cost Analysis — https://arxiv.org/abs/1302.6363  
    Diagnose underperformance by market context and execution conditions, not only signal direction.
24. Gerhold et al., Transaction Costs, Trading Volume and Liquidity Premium — https://arxiv.org/abs/1108.1167  
    Even small proportional costs materially alter optimal trading frequency.
25. Cesari et al., Effective Trade Execution — https://arxiv.org/abs/1206.5324  
    Execution quality and order mechanics are part of strategy design.
26. Tsagaris, Statistical Arbitrage with Transaction Costs in Futures — https://arxiv.org/abs/0801.3348  
    Spread, slippage and gearing must be included in expected utility.
27. BIS, FX execution algorithms and market functioning — https://www.bis.org/publ/mktc13.htm  
    Algorithm choice, fragmentation and liquidity conditions influence execution outcomes.
28. BIS Triennial Survey: foreign-exchange market structure — https://www.bis.org/statistics/rpfx22.htm  
    Liquidity varies by instrument, venue and time; a single fixed threshold is rarely universal.
29. Danyliv et al., Random walk model and execution — https://arxiv.org/abs/1908.04333  
    On noisy short horizons, apparent timing advantages can vanish after execution costs.
30. Noh and Weston, Price impact with transaction costs — https://arxiv.org/abs/2002.08286  
    Costs create a rational no-trade region; trading continuously is not optimal.
31. Market microstructure noise literature overview — https://en.wikipedia.org/wiki/Market_microstructure  
    Bid/ask bounce and discrete ticks contaminate naive high-frequency return signals.
32. Empirical high-frequency trading profitability limits — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2048658  
    Short-lived gross alpha can disappear after realistic fees and latency.

## D. Labels, validation and overfitting control

33. Rigorous walk-forward framework for microstructure signals — https://arxiv.org/abs/2512.12924  
    Use strict information-set discipline, realistic costs and independent chronological tests.
34. Double out-of-sample walk-forward optimization — https://arxiv.org/abs/2602.10785  
    Parameter-window choice itself can overfit; preserve a final untouched period.
35. QuantInsti walk-forward optimization guide — https://blog.quantinsti.com/walk-forward-optimization-introduction/  
    Repeated train-forward-test windows are more realistic than one static split.
36. Scikit-learn `TimeSeriesSplit` — https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html  
    Time-ordered splits prevent training on future observations.
37. Scikit-learn probability calibration — https://scikit-learn.org/stable/modules/calibration.html  
    Raw model scores should not be treated as probabilities without calibration.
38. Scikit-learn `CalibratedClassifierCV` — https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html  
    Calibration must itself respect the time split.
39. Hudson & Thames triple-barrier/meta-labeling study — https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/  
    Event sampling and meta-labeling can improve precision when applied carefully.
40. QuantInsti triple-barrier implementation — https://blog.quantinsti.com/triple-barrier-method-gpu-python/  
    Volatility-scaled horizontal barriers and a time barrier produce execution-relevant labels.
41. Sefidian triple-barrier explanation — https://www.sefidian.com/2021/06/26/labeling-financial-data-for-machine-learning/  
    The first barrier touched is more meaningful than an arbitrary future return.
42. Supervised autoencoders with triple-barrier labels — https://arxiv.org/abs/2411.12753  
    Transaction costs must be included when constructing labels and evaluating models.
43. Cross-validation tools for financial time series — https://medium.com/@samuel.monnier/cross-validation-tools-for-time-series-ffa1a5a09bf9  
    Purging and embargo reduce overlap leakage in event-based labels.
44. Backtest overfitting and combinatorially symmetric cross-validation — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253  
    Trying many parameter combinations raises the probability of selecting a false winner.

## E. Official/free macro and context APIs

45. FRED API — https://fred.stlouisfed.org/docs/api/fred/  
    Free key; useful for yields, dollar/liquidity and macro regime context.
46. Federal Reserve data access/FRED information — https://www.federalreserve.gov/data/data-download-fred-information.htm  
    Official guidance for programmatic Federal Reserve series access.
47. BLS Public Data API — https://www.bls.gov/developers/home.htm  
    Public access to CPI, employment and unemployment data; a key is optional for higher limits.
48. BLS Python examples — https://www.bls.gov/developers/api_python.htm  
    Official request structure for multiple series and years.
49. BEA Data API — https://apps.bea.gov/api/signup/  
    Free key for official GDP, income and expenditure data.
50. Finnhub economic calendar API — https://finnhub.io/docs/api/economic-calendar  
    Optional free-key calendar/context provider; not an execution quote source.
51. Alpha Vantage documentation — https://www.alphavantage.co/documentation/  
    Optional free macro/commodity/FX context with strict rate limits.
52. Twelve Data documentation — https://twelvedata.com/docs  
    Optional supplemental market data; free-tier limitations make it unsuitable as the authoritative XAUUSD execution feed.

## F. Educational videos and tutorials reviewed

53. Walk-forward optimization complete guide — https://www.youtube.com/watch?v=Ia2o0h23Zlo  
    Practical rolling optimization and out-of-sample workflow.
54. MATLAB walk-forward analysis webinar — https://www.youtube.com/watch?v=D8vGt0dT2Ks  
    Demonstrates systematic training/testing windows and performance aggregation.
55. Walk-forward testing explained — https://www.youtube.com/watch?v=bfwhXTnQgMI  
    Highlights why a strategy must be evaluated on unseen sequential data.
56. QuantInsti collection of algorithmic-trading videos — https://blog.quantinsti.com/best-algorithmic-trading-videos/  
    Reviewed topics include backtesting, execution, machine learning and risk controls.

## What was deliberately not implemented

- **No deep reinforcement-learning order agent yet.** The available labeled sample is too small and one-sided.
- **No paid tick feed dependency.** MT5 broker ticks remain the live execution reference.
- **No automatic parameter optimization on the 59 losing trades.** That would optimize the bot to one day of history.
- **No wider-spread “strong score” override.** The uploaded evidence showed that score strength did not compensate for spread.
- **No two-position pyramiding.** The base strategy has not earned the right to scale exposure.

## Optional keys worth obtaining

Priority order:

1. `FRED_API_KEY` — free, useful for yields and macro regime features.
2. `BEA_API_KEY` — free, official macro data.
3. `FINNHUB_API_KEY` — optional secondary economic-calendar context.
4. `ALPHA_VANTAGE_API_KEY` — optional macro/commodity context subject to free limits.

BLS works without a key for basic use. None of these keys is required to run V6 shadow calibration.

## G. Objective chart structure sources added for V6.1

57. Osler, *Technical Analysis and Intraday Exchange Rates* — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=888805  
    Professionally supplied support/resistance levels showed measurable intraday relevance in FX; levels must still be treated as probabilistic and temporary.
58. Chung & Bellotti, *Evidence and Behaviour of Support and Resistance Levels in Financial Time Series* — https://arxiv.org/abs/2101.07410  
    Repeated bounces increase a level's measured relevance, while the probability decays as the level ages.
59. Odders-White, *Technical Analysis and Liquidity Provision* — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=315660  
    Support/resistance can coincide with peaks in displayed depth, providing a microstructure rationale for level-aware execution.
60. Osler, *Currency Orders and Exchange-Rate Dynamics* — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=923370  
    Order clustering can explain both reversal near known levels and acceleration after a level breaks.

### How V6.1 uses these ideas

- A support or resistance is not a manually drawn single price. It is a cluster of confirmed M15/H1/H4 swing points with timeframe weights, touch count, freshness decay and an ATR-scaled band.
- An "order block" is not accepted because of its name or appearance. V6.1 defines it as the last opposite closed candle before a displacement of at least 1.10 ATR that also breaks a prior local range. It is invalidated after a close through the distal boundary or excessive retests.
- Three independent families vote: HTF trend, support/resistance structure, and objective order block. At least two of three must agree.
- The selected direction must still have enough price room to the next opposing structure for the complete target plus spread.
- Every structural feature is stored in shadow history for later walk-forward analysis. No structural pattern can authorize demo orders before the V6 promotion gate passes.

The phrase "order block" has weaker standardized empirical support than support/resistance. It is therefore treated as a testable supply/demand proxy, never as a guaranteed institutional footprint.

## V6.3 supplemental sources (61–68)

61. Scikit-learn, Probability calibration — calibrated confidence and Brier scoring. https://scikit-learn.org/stable/modules/calibration.html
62. Scikit-learn, TimeSeriesSplit — chronological expanding validation and gaps. https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
63. Lu et al., Learning under Concept Drift: A Review. https://arxiv.org/abs/2004.05785
64. CFTC, proposed automated-trading risk controls, testing and monitoring. https://www.cftc.gov/PressRoom/PressReleases/7283-15
65. MetaTrader 5 Python `order_send` reference. https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py
66. MetaTrader 5 Python `history_deals_get` reference. https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py
67. CME Group Gold overview and near-24-hour liquidity. https://www.cmegroup.com/markets/metals/precious/gold.html
68. Bakshi et al., Economic Drivers of Gold. https://ssrn.com/abstract=4652113
