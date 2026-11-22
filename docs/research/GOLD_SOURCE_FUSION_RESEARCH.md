# Gold source selection and decision fusion

## Decision

The appropriate design for this project is a combined decision layer that keeps
price evidence, publication risk and slower economic context distinct. A third
advisor repeating another gold quote or rewording the same economic releases
would add apparent agreement without necessarily adding information. The new
source advisor is therefore an inspectable component of the main decision loop,
with an optional read-only display, rather than another independent order sender.

The strongest immediate engineering additions are accurate source identity,
publication timing, visible failures and fresh cross-market observations. These
improve what the system can observe and how it handles uncertainty. They do not,
by themselves, demonstrate profitable prediction. The local currency-augmented
forecast experiment failed to improve on the gold-only baseline, so currency
signals remain experimental and the broker-demo default only observes them.

Direct BLS CPI and employment release adapters and a New York Fed funding-data
adapter are implemented. Initial BLS requests were rejected, but the production
request settings successfully retrieved both feeds in Atom format. Official
release-header verification remains a separate access requirement. The New York Fed
endpoint responded successfully. Existing Census, Federal Reserve, BEA, FRED,
calendar and institutional inputs remain available according to their existing
configuration. No missing release is substituted with a fabricated value.

## Starting from the economic mechanisms

Gold must be analyzed at the horizon at which a position is managed. A multi-year
reserve-allocation argument is not a reliable instruction for a five-minute
trade. Conversely, a short-lived change in the dollar does not settle whether
gold is attractive as a long-term reserve. A useful source must therefore answer
both what changed and when that change could have become known to the strategy.

The opportunity-cost mechanism is a reasonable place to begin: gold does not
pay contractual interest, and its relative attraction can change when expected
real returns on alternatives change. Chicago Fed research examines real rates,
inflation expectations and other long-run influences, but also finds that the
historical real-rate relationship is not uniform across all periods. That is
evidence against hard-coding an invariant inverse relationship.[^1] The design
implication is to treat real yields as contextual evidence, then verify whether
the current market is responding consistently with that explanation.

The dollar adds a separate measurement issue. XAUUSD is denominated in dollars,
while EURUSD and USDJPY encode dollar strength with opposite quote conventions.
A rising EURUSD is normally a weaker-dollar observation relative to the euro;
a rising USDJPY is a stronger-dollar observation relative to the yen. Neither
pair is the broad dollar, and their combination is not a licensed dollar index.
Local European and Japanese developments can also dominate individual pairs.
The implementation consequently requires agreement and labels both instruments
as one currency family, not two independent votes for gold.

Investment flows and reserve behavior require particular care with units. A
larger dollar value of gold holdings can result from higher gold prices without
additional ounces being purchased. A September 2026 Federal Reserve research
note challenges the inference that changes in the market value of reserves
necessarily demonstrate a dramatic new preference for gold over Treasuries.[^2]
The engineering conclusion is to prefer quantity changes, reliable observation
dates and first-available publication records to headline dollar totals.

Finally, market reaction and market prediction are different measurements. The
World Gold Council explicitly describes its return-attribution tool as a way to
analyze historical drivers and unexplained returns.[^3] A model that explains a
completed month cannot be assumed to forecast the next candle. The new local
experiment tests the harder, forward-looking claim rather than converting an
attribution correlation into a trading-confidence percentage.

## Source priorities

| Source or family | Useful information | Appropriate role | Decision for this build |
|---|---|---|---|
| MT5 XAUUSD quotes and completed candles | Executable-side price, spread, observed structure | Entry execution and ongoing exit management | Retain as execution authority |
| MT5 EURUSD and USDJPY | Fresh dollar-relative price changes | Experimental transmission context | Add with strict instrument and timing checks |
| BLS CPI and Employment Situation feeds | Release identity; timing requires header verification | Release protection and measured gold reaction | Implement Atom/RSS and verified-header parsing; expose failures |
| Federal Reserve, Census and BEA releases | Monetary-policy and activity publications | Existing economic context; publication protection | Retain and connect recent publications to risk checks |
| FRED and Treasury real yields | Opportunity-cost background | Daily or slower context | Retain existing FRED inputs; do not duplicate votes |
| New York Fed SOFR and EFFR | Daily secured/unsecured money-market observations | Descriptive funding context | Add; no gold-direction score |
| CFTC positioning | Published trader-position categories | Slower positioning context | Retain; do not use as live order flow |
| WGC ETF and official-sector statistics | Investment and physical-demand context | Slower context with publication discipline | Retain existing implementation |
| CME gold/silver and rates markets | Potentially useful futures and price-discovery information | Fast only with a suitable entitled feed | Do not treat the free delayed website as live |
| LBMA benchmarks | Defined gold benchmark observations | Reference checks and slower research | Do not use as continuous executable quotes |
| Shanghai Gold Exchange | Chinese-market pricing and physical-market context | Further slow-context research | Defer automated premium trading signals |
| Broad news search and sentiment summaries | Discovery of potentially relevant developments | Research queue requiring verification | No direct order authority |

The ranking reflects the present deployment, not a claim that only US information
matters. US releases are operationally relevant to this dollar-denominated
instrument, but physical markets, non-US monetary policy, geopolitics and reserve
behavior can matter as well. Their incremental value still has to survive the
same timing, access and prediction tests. More inputs are not automatically a
better model, particularly when they repeat the same underlying information.

## Provider timing and access constraints

BLS publishes official RSS choices for CPI and the Employment Situation, and
also publishes an iCalendar schedule.[^4][^5] The release adapters use an
allowlisted BLS release link and verify its official header time. They deliberately do
not extract an arbitrary number from prose and call it an economic surprise.
Consensus expectations are a separate dataset; an actual value compared with
last month's value is not the same thing as an actual-versus-consensus surprise.

Initial direct requests returned HTTP 403. The production request headers later
retrieved both feeds successfully, each with twelve Atom entries despite its
`.rss` address. Critically, the September CPI entry carried a timestamp near
07:50 New York time while the official release header specified 08:30.[^13]
The adapter must not confuse feed preparation with release availability. It now
recognizes Atom and RSS, rejects arbitrary XML, and requires the linked header's
release time, including New York daylight-saving conversion, before emitting
a tradable publication event. Unknown timing produces no new publication signal.

The archived release page was readable through the research browser, but a
direct request from this machine returned HTTP 403. Header verification is
therefore a material deployment limitation even when feed retrieval succeeds.
The runtime exposes unverified recent releases separately; no complete BLS
announcement coverage is claimed. Existing calendar protection remains
important. Older feed entries do not trigger fresh blocks on startup, and parser
fixtures do not substitute for a verified live release event.

The New York Fed publishes SOFR at approximately 08:00 New York time on business
days, and provides reference-rate data through its markets interfaces.[^6] This
is not a real-time funding order book. The implemented endpoint returned SOFR
and EFFR observations with a common effective date. The parser calculates their
difference in basis points only when dates match, and rejects future, nonfinite
or overly old observations. It does not interpret the difference between two
distinct money markets as a mechanical gold buy or sell signal.

FRED's normal view of the past can include subsequent revisions. Its real-time
period parameters support retrieving information associated with earlier
vintages.[^7] The distinction is essential for historical news training: a latest
download must not silently be treated as what the bot knew on the day of a trade.
The existing macro collector remains suitable for live contextual observation;
it is not automatically a valid publication-time training dataset.

CFTC reports generally publish Friday data describing positions from Tuesday,
subject to the published schedule.[^8] Polling that source every few seconds
would not turn it into current order flow. Similarly, Treasury's real-yield
curve is a daily observation, not an intraday bond-futures feed.[^9] Duplicating
Treasury-derived series from multiple aggregators would increase source count
without necessarily improving independence or freshness.

CME's public delayed quotes are delayed by at least ten minutes.[^10] That is a
material mismatch for a strategy using a two-second position-management loop.
LBMA's gold benchmark is established in twice-daily London auctions, and its
data use also has licensing considerations.[^11] These are legitimate sources
for their intended roles, but neither should replace a fresh executable bid/ask.

Shanghai exchange data is an attractive research direction for physical-market
conditions. However, the public historical page inspected in this review showed
old entries rather than a verified current automated feed.[^12] A cross-market
premium additionally needs aligned timestamps, currency conversion, product
specification and delivery conventions. The project does not fabricate a live
China premium from mismatched daily prices.

## What the broker actually offers

The deployment audit verified the following metadata directly in MT5:

| Symbol | Broker description | Identity result |
|---|---|---|
| XAUUSD | Gold vs US Dollar | XAU base, USD profit currency |
| EURUSD | Euro vs US Dollar | EUR base, USD profit currency |
| USDJPY | US Dollar vs Yen | USD base, JPY profit currency |
| USDX | SGI Enhanced Core ETF | Not the dollar index |
| DXYN | The Dixie Group Inc | Not the dollar index |
| GDXY | YieldMax Gold Miners Option Income Strategy ETF | Not the dollar index |

This finding materially changes source selection. A fuzzy search for a familiar
ticker could have connected an unrelated security to the gold model. The new
collector uses exact currency pairs and verifies their base and profit currency
metadata before accepting observations. It does not automatically substitute an
instrument just because its name contains DXY or USDX.

The collector reads quotes and M5 candles from the existing terminal. It does
not open foreign-exchange positions. Currency histories refresh at most once
per fifteen seconds, while quote freshness is checked on each assessment. Only
completed bars are used. Missing or asynchronous final candles produce an
unavailable result rather than an old, apparently complete comparison.

## Local incremental-information experiment

The experiment exported 15,000 completed M5 bars each for XAUUSD, EURUSD and
USDJPY. After timestamp alignment, feature warm-up, missing-bar checks and
forward-label continuity requirements, 12,162 observations remained. Source
CSV hashes and broker metadata are retained with the research results. Displayed
historical bar timestamps are broker-encoded; they are not represented as
verified UTC publication times.

Two fixed ridge specifications were compared. The first used gold's own
one-bar return, three-bar return and rolling volatility. The second added the
same measurements from both currency pairs. Both predict the next three-bar
gold log return. Inputs were standardized on the training segment only, and the
first 60% of observations supplied training data with a fifteen-minute purge
before the later evaluation segment. No parameter search was performed after
seeing the comparison.

| Forecast | Later-period MAE, basis points | Direction accuracy |
|---|---:|---:|
| No change | 10.6970 | Not used |
| Gold only | 10.7041 | 49.743% |
| Gold plus currencies | 10.7225 | 49.558% |

The currency-augmented forecast was slightly worse overall and had higher MAE
than the gold-only specification in each of four later chronological blocks.
The sensible conclusion is narrow: this specification, dataset and horizon do
not establish incremental predictive value from these currency features. This
does not prove that currencies never matter, nor does it validate a different
nonlinear model that has not been tested.

The experiment measures forecast error, not executable trading profit. It does
not reproduce consensus permissions, order filling, financing, account margin
or adaptive exits. Some periods overlap historical material already explored
in earlier project research, so the comparison is not advertised as a pristine
new strategy holdout. The output explicitly sets execution approval to false.

The practical consequence is to retain the new transmission measurements for
inspection and paper experiments. A simultaneous currency/gold relationship can
still help describe a position's environment, but whether it improves entries
or exits must be tested separately. The project does not count a plausible
economic story as a profitable forecast result.

## Integrated decision behavior

The main bot now has separate background workers for BLS CPI, BLS employment
and New York Fed funding data. CPI and employment requests use a sixty-second
cadence; funding uses thirty minutes. Requests are bounded and do not sit in
the position-management path. Slow institutional and macro jobs retain their
existing workers, reducing the chance that a slow contextual request queues
ahead of publication detection.

Successful source payloads receive a SHA-256 identity, retrieval timestamp,
normalized content and source URL. Changed payloads are archived separately.
The dashboard distinguishes current data, pending/stale data and failed
requests. A cached result does not become newly published merely because a
refresh was attempted. A recently observed verified release may still supply
short-lived protection during a later refresh failure; its publication clock
continues to expire normally.

Fresh, verified, high-impact official publications supplement the news-risk
filter for five minutes after their stated publication time. This is publication
protection, not a directional forecast. The existing lane-specific news policy
then determines whether to close controlled positions or block new entries.
Existing calendar blocks remain intact. A future-dated, stale, unverified or
unrecognized publication cannot create this new event block.

The experimental currency context requires fresh quotes, synchronized completed
bars, nonzero volatility, agreement between the two dollar-relative movements
and a negative recent gold/dollar relationship. The three-bar movement is
normalized using an earlier volatility window. Recent contemporaneous
correlation is labeled as context, not causation or future-return probability.
If the relationship is weak or conflicting, the output is neutral or unavailable.

In `protect` mode, a clear currency-context contradiction can veto an otherwise
permitted entry. A new exit additionally requires actual gold deterioration and
weakening lane momentum on two distinct completed M5 observations. Repeated
ticks cannot count as separate confirmations. Stale data clears confirmation;
a new position cannot inherit an old position's confirmation. This rule is
experimental and is enabled by default only in the integrated paper launcher.

Broker demo execution observes currency context by default. An explicit
`--cross-market-policy protect` is available for a deliberate demo experiment,
but it does not mark the policy validated. The existing learned forecasts retain
their own observation/filter selection. Neither source context nor the currency
policy can authorize a fourth position, change a new entry from 0.01 lot,
override the broker's demo guard or disable emergency protection.

The two original advisors remain distinct components; Advisor 1's protected
files are unchanged. This preserves a useful baseline and avoids silently
changing its behavior while improving the main bot around it. Slow funding,
positioning and economic data are displayed as their own families rather than
being folded into a fabricated single confidence percentage.

## Commands and evaluation

Run one main bot at a time with MT5 open:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
python .\run_gold_ai.py --max-minutes 60
```

This is paper trading with the experimental learned and currency filters.
For an adaptive baseline without either experimental intervention:

```powershell
python .\run_gold_ai.py --learned-policy off --cross-market-policy observe --max-minutes 60
```

For broker demo trading with experimental signals in observation by default:

```powershell
python .\run_gold_ai.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 60
```

The optional read-only source display can run separately:

```powershell
python .\run_gold_source_advisor.py --interval-seconds 15
```

Reproduce the local forecast comparison and inspect paper accounting:

```powershell
python -B .\tools\research_gold_sources.py
python -B .\tools\report_gold_ai.py
python -B .\tools\validate_gold_changes.py
```

Paper sessions record both policy selections and the source assessment at entry.
Separate runs can encounter different market conditions; raw P/L differences
between them are not a controlled causal comparison. Source-code regression
tests verify parsing, rejection, timing and position-management behavior. The
main-runner smoke test was blocked by an already-running demo instance, which
was left in place. A separate read-only source-advisor check retrieved official
feeds, funding data and live currency context. This establishes source-layer
connectivity, not end-to-end trading profitability. Restart the running main bot
to load the new integration; changes on disk do not hot-update that process.

## Limits and next evidence

This implementation is continuous monitoring of selected, verified resources.
It is not an unrestricted language model browsing arbitrary headlines and
rewriting its execution rules. That distinction matters because automatic
collection, semantic interpretation, predictive learning and order authority
are separate capabilities. A trained numerical forecast already exists in the
project, but the new source layer is explicit, inspectable policy and telemetry.

The most valuable next dataset is a publication-time event history paired with
broker quotes, market expectations, revisions and actual eligible trades. That
would permit testing whether a release changes the expected value of holding
an existing position after costs. It would also distinguish a genuinely new
announcement from repeated coverage of old information. Collecting that record
is more defensible than immediately retraining on latest-revised macro series.

A serious exit comparison must include adverse gaps, missed ticks, swaps,
commission, spreads, margin and every stopped or losing run. With a $100 profile
and fixed 0.01-lot gold entries, many attractive-looking structural stops will
remain unaffordable under the current risk budget. The system should abstain in
those cases. The retained three-position cap is a maximum, not a target that
must be filled regardless of market evidence.

## Sources

[^1]: Federal Reserve Bank of Chicago. [What Drives Gold Prices?](https://www.chicagofed.org/publications/chicago-fed-letter/2021/464), Chicago Fed Letter 464, 2021. Historical mechanisms and instability of simple relationships.
[^2]: Colin Weiss, Federal Reserve Board. [Why Gold Didn't Actually Overtake Treasury Securities as the World's “Favorite” Reserve Asset](https://www.federalreserve.gov/econres/notes/feds-notes/why-gold-didnt-actually-overtake-treasury-securities-as-the-worlds-favorite-reserve-asset-20260903.html), September 3, 2026. Valuation versus quantities and reserve interpretation.
[^3]: World Gold Council. [Gold Return Attribution Model](https://www.gold.org/goldhub/tools/gold-return-attribution-model), accessed September 14, 2026. Historical attribution purpose; not evidence of this bot's predictive edge.
[^4]: U.S. Bureau of Labor Statistics. [RSS Feeds](https://www.bls.gov/feed/), accessed September 14, 2026. Official CPI and Employment Situation feed addresses.
[^5]: U.S. Bureau of Labor Statistics. [Subscribe to iCal Calendar](https://www.bls.gov/help/hlpiCAL.htm), accessed September 14, 2026. Official release-schedule distribution.
[^6]: Federal Reserve Bank of New York. [Secured Overnight Financing Rate](https://www.newyorkfed.org/markets/reference-rates/sofr) and [latest reference-rate API](https://markets.newyorkfed.org/api/rates/all/latest.json), accessed September 14, 2026. Publication cadence and observed response schema.
[^7]: Federal Reserve Bank of St. Louis. [FRED API Real-Time Periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), accessed September 14, 2026. Revisions and information vintages.
[^8]: Commodity Futures Trading Commission. [Commitments of Traders Release Schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm), accessed September 14, 2026. Publication timing and reporting lag.
[^9]: U.S. Treasury. [Daily Treasury Par Real Yield Curve Rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_real_yield_curve), accessed September 14, 2026. Daily real-yield observations.
[^10]: CME Group. [Delayed Quotes](https://www.cmegroup.com/market-data/browse-data/delayed-quotes.html), accessed September 14, 2026. Public-quote delay.
[^11]: London Bullion Market Association. [LBMA Precious Metal Prices](https://www.lbma.org.uk/prices-and-data/lbma-precious-metal-prices) and [Gold Price FAQs](https://www.lbma.org.uk/prices-and-data/lbma-gold-price/lbma-gold-price), accessed September 14, 2026. Auction timing and data-use considerations.
[^12]: Shanghai Gold Exchange. [Historical daily market information](https://www.sge.com.cn/sjzx/mrhqsj), accessed September 14, 2026. Public historical page and its observed limitations.
[^13]: U.S. Bureau of Labor Statistics. [Consumer Price Index, August 2026 release](https://www.bls.gov/news.release/archives/cpi_09112026.htm), September 11, 2026. Official embargo/release header compared with the directly retrieved Atom feed timestamp.

Local experimental evidence: `data/research/gold_sources/capture.json` and
`evaluation.json`, with the accompanying source-hashed completed-bar CSVs.
Implementation: `gold_source_intelligence.py`, `gold_cross_market.py` and the
main bot integration. These are project observations, not external performance
endorsements.
