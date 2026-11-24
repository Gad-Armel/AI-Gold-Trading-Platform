# XAUUSD bot performance and adaptive trading research

## Decision

The current three-horizon strategy has a negative realized expectancy in the broker history examined. Its primary defects are not solved by making the evidence threshold easier to pass. The immediate priorities are accurate broker accounting, correct time alignment, nonblocking market-data refresh, less repetitive exposure, and exits that allow a market thesis to develop without an arbitrary small profit cap.

A configurable adaptive-exit implementation is now available in the main runner. It closes on confirmed thesis invalidation, volatility-adjusted profit giveback accompanied by weakening momentum, stagnation without trend support, and existing news protection. Ordinary profit-taking no longer uses the fixed $5 basket target when adaptive mode is selected. Broker stops, lane loss limits and the account-session circuit breaker remain independent protections.

No trained model passed a sufficient standard for execution. Six learners were fitted across three candle timeframes, with 18 model/threshold combinations examined on validation data. The selected short-horizon learners lost money on their subsequent holdouts. The most promising simple candidate was hourly adaptive trend management, but its returns were regime-dependent and its block-bootstrap uncertainty interval included zero. It is a research candidate, not an established profitable trading system.

The default trading policy has therefore not been silently switched to an unvalidated strategy. The new behavior is selected using `--exit-policy adaptive`; model artifacts remain explicitly unapproved. A short MT5 shadow run verified the integrated analysis without sending orders.

## Actual trading performance

The audit used broker deal history for the 30-day window ending September 10, 2026 at approximately 15:28 UTC. Entries identify the controlled position IDs; all available deals belonging to those positions contribute profit, commission, swap and fees. Only positions with sufficient exit volume to be fully closed are included. Positions whose opening deals precede the available window can be omitted, so this is not an account-lifetime statement.

| Lane | Closed trades | Net P/L | Win rate | Profit factor | Average win | Average loss |
|---|---:|---:|---:|---:|---:|---:|
| SCALP | 840 | −$222.77 | 45.83% | 0.778 | $2.03 | −$2.22 |
| INTRADAY | 287 | −$271.79 | 62.72% | 0.679 | $3.19 | −$7.91 |
| SWING | 198 | −$197.36 | 69.19% | 0.686 | $3.14 | −$10.29 |
| Combined | 1,325 | **−$691.92** | — | — | $2.54 | −$3.99 |

Source: locally exported MT5 history, `data/research/xauusd_audit/closed_trades.csv`, `summary.json` and `performance_detail.json`. Results describe this broker account's controlled trades, including historical policy versions sharing these magic numbers. They do not attribute every trade to today's exact implementation.

Combined drawdown measured at closed-trade observations was $869.09. This is not equity drawdown: open-position excursions may make actual equity drawdown larger. Lane-level closed-trade drawdowns were $265.50, $349.26 and $279.54 respectively. Concurrent trades are correlated, and treating all trades as independent observations would overstate the precision of performance estimates.

The payoff imbalance is especially important. With the observed rounded average win and loss, intraday would need roughly 71% winners just to break even; swing would need roughly 77%. Their observed win rates are below those levels. Optimizing the number of winning trades alone is therefore the wrong objective. The required objective is positive expected net payoff after costs, subject to tolerable drawdown and execution reliability.

Median holding periods were approximately 85 seconds for scalp, 345 seconds for intraday and 568 seconds for swing. A strategy named SWING was typically holding positions for under ten minutes. That is consistent with small basket exits or short-lived thesis changes dominating the nominal multi-hour analysis. The old close journal did not record the actual strategy reason, so historical exits cannot all be reliably split into profit target, reversal, weakened evidence and news protection. Future close records now retain that reason.

## Broker clock and accounting findings

A live comparison found MT5 tick timestamps approximately 10,799 seconds ahead of system UTC. This terminal is exposing a broker clock corresponding to UTC+3. Using a UTC endpoint directly against that history omitted recent broker-stamped deals. An initial query returned 1,279 closed trades; applying the explicit server conversion recovered another 46 positions and produced the final 1,325-trade audit.

This explains why a display can show changing positions while realized P/L remains unchanged: the broker close may lie outside the incorrectly constructed query endpoint. Mixing naive local datetimes and timezone-aware datetimes was also removed, but that change alone was not sufficient. A direct comparison of naive and aware endpoints returned the same count before the broker conversion was applied.

The implementation now separates actual UTC from broker-encoded time. `MT5_SERVER_UTC_OFFSET_SECONDS` is set to 10,800 for the measured terminal. Query bounds are converted to broker time and displayed deal timestamps are converted back to UTC. The setting must be changed if the broker or its daylight-saving convention changes. Entry checks reject substantial disagreement between the configured offset and the current quote clock instead of silently treating a future timestamp as a fresh quote. Official MetaQuotes examples describe UTC timestamp handling, but the observed terminal behavior is the reason for this explicit local adapter.[^1]

Additional accounting and execution corrections include floating swap in session P/L; controlled-position ID attribution for closing deals whose magic differs from their opening deal; pending-order checks before another entry; and propagation of failed position queries. A failed `positions_get` no longer becomes an apparently empty lane with zero exposure. Accounting remains a broker-history reconstruction: a zero-magic close whose identifying entry is outside the requested history window may still require a longer ownership history.

## Market-data and loop findings

The runner previously performed independent API, macro and calendar refreshes on the same thread that managed open positions. HTTP timeouts could therefore postpone a software-controlled exit. A bounded background worker pool now refreshes those data sources while the main loop continues to read MT5 and manage exposure. A source cannot queue duplicate refreshes while its previous request is still pending. Failures retain the old observation and expose an error class; they do not fabricate a fresh publication timestamp.

The existing official Census/Federal Reserve/BEA release monitor and institutional refresh were used by the standalone economic display but were not fully connected to the main runner. They are now integrated. The economic builder also receives the live snapshot, enabling its existing post-release market-reaction calculation. Data-source availability still depends on the configured provider and its current response; a connection path is not a guarantee that every field is available.

The tick advisor also had an incorrect microprice diagnostic: it treated `volume` and `volume_real` as opposite sides of the order book. MetaQuotes defines both as last-price trade volume at different precision. They are not bid depth and ask depth. That calculation has been removed, and the fields remain explicitly unavailable without appropriate depth information.[^2]

Tick history is now requested on the configured broker clock and normalized before computing short windows. Future observations cannot vote in a window. In the integrated shadow check the tick advisor reported 8,423 ticks and a latest-tick age of 0.212 seconds; all three adaptive candle contexts were available. These are connectivity observations from that run, not a latency benchmark or evidence of prediction accuracy.

The economic market-reaction baseline was tightened to use candles that had actually completed before publication. A one-minute candle that opens before an event but closes after it must not become a supposedly pre-event baseline. This distinction matters both for real-time reactions and later event studies.

## How adaptive exits work

The controller observes a position's favorable price excursion, current volatility, recent momentum, moving-average trend and completed-bar structure. It does not send a fixed take-profit order. It continues holding while the market thesis remains valid, including when floating profit exceeds the old $5 target.

| Condition | Adaptive behavior |
|---|---|
| Strong authorized opposite direction persists | Request lane close after the configured confirmation interval |
| Completed structure breaks and trend opposes the position | Treat as thesis invalidation after confirmation |
| Meaningful favorable excursion reverses by a volatility-scaled amount and momentum weakens | Request a profit-protection exit |
| Position stagnates and loses trend support | Request close after the horizon-specific stagnation period |
| Relevant close-and-block news window | Preserve immediate news protection |
| Stale or invalid adaptive observations | Abstain from inventing a market signal; retain independent broker/lane protections |

Scalp uses M5 structure, intraday M15 and swing H1. The input calculation explicitly excludes forming candles. A quote-based favorable excursion is separate from the completed-bar indicators. Spread imposes a floor on the trailing distance, so ordinary spread noise alone should not trigger a very narrow trail. These coefficients are transparent research defaults, not fitted optimum parameters.

The adaptive runner permits one position per lane, resets entry confirmation after a close, and requires a new completed anchor bar before re-entering after that close. It also detects a previously observed position disappearing through a broker stop. This reduces immediate re-entry on the identical stale setup. It does not prove that all subsequent same-direction entries have independent information.

Emergency stops remain because Python can disconnect, the machine can lose power, and software management cannot execute while offline. They serve a different role from ordinary profit-taking. The existing lane-dollar limits are still active, so the new controller is not an unrestricted hold-until-profitable strategy.

The initial implementation kept excursion memory in-process. The subsequent [proposal 2 update](AI_PROPOSAL_02_REVIEW.md) adds account- and position-bound checkpoints for adaptive demo mode. It restores saved favorable/adverse excursions and re-entry markers, while resetting adverse-signal confirmation. Prices during an outage remain unknown; this recovery feature does not establish readiness for model promotion.

## Historical experiment

The broker supplied 50,000 completed candles for each of M5, M15 and H1. The hourly archive starts in March 2018; M15 starts in July 2024 and M5 in December 2025. Equal row counts are not equal historical coverage. Each export has a SHA-256 fingerprint in `data_manifest.json` and is preserved by subsequent performance-audit runs.

The study uses a simplified trend challenger, not a replay of the three-advisor consensus bot. It computes causal moving-average separation, three-bar momentum, distance from the fast average, range relative to ATR, volatility ratio, cost relative to ATR and time-of-day encodings. Direction-sensitive features are normalized to the prospective trade side. No revised macro series, historical news consensus or future announcement values are injected into these features.

The first 60% of observations train the classifiers, the next 20% select a model and threshold, and the last 20% evaluate the selected choice. Training observations whose forward label could overlap the next segment are removed. The two learners are regularized logistic regression and a small histogram gradient-boosting classifier. Thresholds are 0.50, 0.55 and 0.60, and validation selection requires at least 100 simulated trades.

Labels represent whether the predefined adaptive trade path earns positive net return. Entry occurs at the next bar open, not the signal bar's closing price. Stops are checked against the subsequent adverse bar extreme; a gap uses the worse opening price. Other exits occur at the next available open after the completed-bar condition. Evaluation uses one non-overlapping simulated position at a time.

These rules reduce obvious look-ahead and fill optimism but do not eliminate execution uncertainty. Bid candles cannot reconstruct the full ask path. Costs assume a 0.01 point value, a minimum $0.28 spread and $0.10 additional slippage allowance per one-ounce-equivalent trade. Commissions, rollover swap, changing historical broker offsets and the exact live news veto are not reproduced. Returns are price-distance accounting for one ounce equivalent, not a promised MT5 account return.

| Timeframe | Fixed-profit comparator PF | Adaptive comparator PF | Selected learned adaptive PF |
|---|---:|---:|---:|
| M5 | 0.895 | 0.936 | 0.628 |
| M15 | 0.964 | 0.952 | 0.815 |
| H1 | 0.963 | **1.203** | No candidate met the validation sample requirement |

Source: `model_comparison.json`. PF is gross positive simulated return divided by absolute gross negative return after the modeled costs. A value below one indicates a negative total result for that experiment.

The learned M5 filter generated 77 holdout trades with −155.47 modeled net return; the M15 filter generated 125 with −184.82. Both deteriorated further under doubled modeled costs. Their artifacts carry `execution_approved=False`. The H1 classifiers did not produce enough qualifying validation trades, so no hourly classifier was selected for deployment.

The H1 adaptive comparator produced 688 holdout trades, +1,870.75 modeled net return and 646.47 closed-trade drawdown. Its win rate was only 35.61%, yet its profit factor exceeded one because payoff size mattered more than winning frequency. This also exposes a limitation of filtering solely on probability of a positive trade: a threshold above 50% may exclude asymmetric trend opportunities. A future learner should estimate net continuation value and downside, not merely maximize win rate.

The hourly comparator is not identical to the integrated controller. In particular, its stop, maximum holding horizon and confirmation mechanics differ from the live lane-dollar protections and persistent live exit checks. Its positive result therefore cannot be assigned to the newly integrated runner. A faithful tick replay with identical execution code is still required.

## Robustness and the limits of the promising result

With hourly parameters frozen, doubling modeled spread/slippage reduced profit factor to 1.172; quadrupling them reduced it to 1.112. These checks support the narrow conclusion that the observed candle result is not erased by those particular cost multipliers. They do not account for missing overnight financing or broker-specific execution effects.

Across five chronological blocks of the hourly archive, adaptive net modeled returns were approximately −269, +293, −35, +102 and +1,877. The large gain was concentrated in the latest block. That pattern does not establish a stable edge across regimes.

A descriptive block bootstrap resampled groups of ten successive holdout trades, using 2,000 samples. Its approximate 95% interval for mean return per trade was −0.51 to +6.47 in the study's price-return units. Because that interval includes zero, the experiment does not establish a positive mean with that level of confidence. Block length, serial dependence and strategy selection also limit interpretation.

The stress exercise was performed after viewing the initial comparison. It is a sensitivity analysis, not a fresh independent holdout. Repeatedly changing parameters after looking at a test period consumes that period as research data. The backtest-overfitting literature is directly relevant: selecting from many trials can produce attractive historical results without durable forward performance.[^3]

## Gold-specific information architecture

Gold analysis should combine several horizons without pretending that every source delivers the same kind of information. The World Gold Council describes drivers including economic conditions, risk and uncertainty, opportunity cost and momentum. Its 2026 mid-year assessment also documents substantial changes in the gold price and volatility regime. These are reasons to test conditional behavior across environments, not grounds for hardcoding a permanent BUY or SELL direction.[^4]

| Information | Useful role | Principal restriction |
|---|---|---|
| Broker bid/ask updates and completed candles | Execution price, immediate conditions, structure and volatility | Broker-specific; not centralized global order flow |
| Independent candle provider | Feed consistency and outage detection | A second view of the same price is not independent economic evidence |
| Scheduled BLS and FOMC releases | Known event timing and exposure planning | The publication outcome is unknown before release |
| Verified actual versus previously recorded forecast | Event surprise after publication | Prior observation is not an analyst forecast |
| Observed post-release gold response | Confirmation of the market's reaction | Requires a genuinely pre-event baseline and realistic delay |
| USD, nominal/real yields and volatility context | Conditional macro regime features | Publication frequency, revisions and correlation matter |
| Gold ETF flows, central-bank activity and CFTC positioning | Slow institutional context | Delayed publication; unsuitable as a fresh seconds-scale trigger |

Official BLS release schedules and Federal Reserve calendars provide authoritative event timing.[^5][^6] A future announcement can influence today's risk plan through its scheduled time and uncertainty; its unreleased value cannot be known in advance. The engine must represent missing consensus as missing rather than substituting a previous number and labeling the result a surprise.

For historical macro learning, observations must be joined by when they were available. FRED's real-time period mechanism exists specifically to retrieve information known during a specified period; using today's revised history would answer a different question.[^7] The same rule applies to institutional observations: CFTC's usual Friday report refers to the preceding Tuesday, while WGC ETF commentary is monthly.[^8][^9]

The low-cost design is to keep MT5 as the execution authority, use the existing official/public data adapters on their natural cadences, and record raw publication timestamps and receipt times. Adding more correlated indicators does not create more independent information. Missing providers should reduce coverage or block a dependent decision, not increase the weight of the remaining source until it resembles certainty.

## Forward validation and operational status

Adaptive mode now writes daily observed-quote files and completed-bar decision records under `data/research/gold_forward/`. Records retain observation time, broker tick time, executable bid/ask, market context, decision and news information. These files create a point-in-time basis for future evaluation; the old training dataset contained no usable labeled rows.

The recorder samples the main loop. It is not a lossless tick archive and must not be treated as one. Dense broker tick exports are still required for accurate short-term fill simulation. Restart recovery, actual financing costs, full news-calendar replay and long-running fault tests remain before an execution-approved learned controller can be claimed.

The recommended next model objective is expected incremental value of continuing a position versus closing at the current executable price, conditioned on direction, elapsed holding time, entry risk, favorable/adverse excursion, current regime and available event context. The action should be WAIT or CLOSE when estimated continuation value is insufficient, with independent exposure constraints. This is a proposed learning target; no validated continuation-value model was produced by this study.

Promotion should require an untouched forward period, reliable point-in-time labels, adequate trades across multiple market environments, positive net performance under realistic costs, stable calibration or value-estimation error, and acceptable drawdown. Existing evidence does not meet that standard. Waiting and collecting evidence are valid autonomous decisions; generating more trades is not itself greater efficiency.

### Reproduction

```powershell
python tools/audit_gold_performance.py
python tools/research_gold_adaptive.py
python tools/stress_gold_candidate.py
python -m unittest discover
python -m unittest discover -s tests
python tools/validate_gold_changes.py
python run_gold_consensus_bot.py --mode shadow --exit-policy adaptive --no-dashboard --max-minutes 10
```

Repeated research runs overwrite research reports and candidate files; archive results before changing the study. Do not repeatedly optimize against the already inspected holdout. The main runner remains demo-only for execution. The shadow command observes markets and records research evidence without opening or closing positions.

For a deliberately experimental demo evaluation, the existing explicit demo confirmation mechanism remains available:

```powershell
python run_gold_consensus_bot.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --exit-policy adaptive --max-minutes 30
```

That command was not executed during this investigation. It enables an unvalidated candidate and should not be confused with model promotion. The system was left stopped after the short shadow connectivity check.

The full validation runner includes both unittest collections and the four standalone research-function checks. Its machine-readable outcome is saved in `data/research/xauusd_audit/validation.json`. Pytest was unavailable in the installed interpreter, so these checks were executed through Python's standard-library test framework without installing additional packages.

Final validation passed 124 tests with zero failures, errors or skips. A read-only terminal check confirmed a USD demo account, a 100-ounce contract size and a 0.01 price point. No demo or real orders were sent by the investigation.

## Sources

[^1]: MetaQuotes. [copy_rates_from](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrom_py) and [history_deals_get](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py), Python integration documentation, accessed September 10, 2026. The UTC+3 observation itself comes from the connected terminal, not a universal claim about MT5.
[^2]: MetaQuotes. [MqlTick price data structure](https://www.mql5.com/en/docs/constants/structures/mqltick), accessed September 10, 2026.
[^3]: David H. Bailey, Jonathan M. Borwein, Marcos López de Prado and Qiji Jim Zhu. [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), research paper, accessed September 10, 2026.
[^4]: World Gold Council. [What drives gold?](https://www.gold.org/goldhub/research/what-drives-gold), 2013; and [Gold Mid-Year Outlook 2026: Point break](https://www.gold.org/goldhub/research/gold-mid-year-outlook-2026), July 1, 2026.
[^5]: U.S. Bureau of Labor Statistics. [Schedule of Releases for the Employment Situation](https://www.bls.gov/schedule/news_release/empsit.htm), accessed September 10, 2026.
[^6]: Federal Reserve Board. [FOMC meeting calendars and information](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), accessed September 10, 2026.
[^7]: Federal Reserve Bank of St. Louis. [FRED API real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), accessed September 10, 2026.
[^8]: Commodity Futures Trading Commission. [Commitments of Traders release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm), accessed September 10, 2026.
[^9]: World Gold Council. [Gold ETF Commentary](https://www.gold.org/goldhub/research/etf-flows?page=1), accessed September 10, 2026.

Local evidence: the attached `pasted-text.txt` console excerpt; `config/gold_consensus_settings.py`; the main runner and associated execution, research and news modules; broker-derived `closed_trades.csv`; `summary.json`; `performance_detail.json`; `data_manifest.json`; `model_comparison.json`; `H1_stress.json`; and saved test outputs under `data/research/xauusd_audit/`. Private broker history is available in the workspace and is not published externally.
