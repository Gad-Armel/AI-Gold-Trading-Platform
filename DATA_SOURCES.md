# Data sources and horizon roles

## Source hierarchy

`MT5 executable quote > official release timestamp/result > independent candle
feed > official macro series > CFTC/ETF/central-bank context`.

Every value that can influence a decision should retain its source, observation
time, release time, retrieval time, confidence and vintage when available.

## SCALP

- MT5 bid/ask and ticks: executable price and micro-flow timing.
- MT5 M1/M5 candles: local structure and ATR levels.
- Independent API candles: low-weight cross-check, optional during an outage.
- Verified macro surprise: short-lived context and release-window protection.
- Official Census/Federal Reserve publications: release-time anchor.
- MT5 post-release XAUUSD movement: range-scaled reaction confirmation that
  expires after 12 minutes.

Slow FRED, CFTC, ETF and central-bank observations do not vote on a scalp.

## INTRADAY

- MT5 and independent API candles are both mandatory strong sources.
- MT5 tick flow refines entry timing.
- FRED USD/real-yield/nominal-yield/VIX regime is continuous context.
- A recent verified macro surprise can veto a conflicting new entry.
- Official BEA GDP/core-PCE changes and Census/Fed releases add conservative
  event context. Change-versus-prior is capped because it is not consensus.
- The post-release XAUUSD reaction can confirm direction for at most 60 minutes.

## SWING

- MT5/API H1-H4 structure is entry authority.
- FRED daily/weekly risk and opportunity-cost regimes, the semi-annual World
  Bank growth outlook, weekly CFTC positioning, weekly/monthly ETF flows and
  monthly/quarterly central-bank demand are context only.
- Slow data can confirm or veto; it cannot independently authorize a trade.

## V6 automatic institutional collection

- World Gold Council central-bank statistics: latest aggregate reported monthly
  net purchases/sales. Country figures are not summed again, avoiding double
  counting the published aggregate.
- World Gold Council global physically-backed gold ETF report: monthly change
  in collective gold holdings, in tonnes.
- CFTC public `Disaggregated - Futures Only` API: COMEX gold managed-money net
  position, four-week change and rolling 52-week percentile.
- Refresh cadence: at most once every six hours, with independent source errors
  and last-valid-value fallback.

Scoring is continuous rather than a binary headline vote. Net central-bank and
ETF tonnage are normalized by cadence-specific meaningful moves. CFTC flow is
normalized by COMEX open interest, while extreme crowding reduces quality. A
quality-weighted coherence penalty reduces confidence when the three sources
disagree. Publication age and observation age are penalized separately.

V6.4 exposes the calculation as confirmation points. The SWING 100-point budget
is allocated as 10 verified-release, 20 USD/yields/VIX, 5 daily US policy
uncertainty, 5 global policy uncertainty, 10 systemic financial stress, 7.5
inflation/recession, 5 World Bank global growth, 20 central-bank demand, 10 ETF
and 7.5 CFTC points. Magnitude and quality determine how much of each allocation
is earned. Agreement adds; contradiction subtracts; missing or stale data
contributes zero. Coverage and active-source counts are shown separately from
directional confidence. These are transparent evidence-strength points, not an
estimated probability of profit.

For SCALP, 70 points are reserved for verified actual-versus-consensus surprise
and 30 for the measured XAUUSD response after a verified official release. For
INTRADAY, the allocation is 35 verified surprise, 10 official change-versus-
prior, 20 observed market reaction, 25 USD/yields/VIX, 5 daily US uncertainty
and 5 systemic stress. These capacities still total 100; adding sources does not
allow confidence inflation.

Annual reserve-manager surveys explain structural motives such as crisis
performance, diversification and geopolitical-risk protection. They are not a
time-varying market signal and therefore do not add a permanent bullish vote.

Verified release coverage includes payrolls, CPI/PCE, PPI, wages, unemployment,
claims, JOLTS, ADP, retail sales, ISM/PMI, durable goods, industrial production,
consumer confidence, GDP and policy-rate decisions. Only a released event with
both actual and forecast values earns directional points. A scheduled estimate
protects the trading window but does not predict gold.

## Primary documentation

- MT5 Python integration: https://www.mql5.com/en/docs/python_metatrader5
- FRED API and series: https://fred.stlouisfed.org/docs/api/fred/overview.html
- ALFRED vintages: https://alfred.stlouisfed.org/
- BLS release calendar: https://www.bls.gov/schedule/news_release/
- BLS Public Data API limitations: https://www.bls.gov/bls/api_features.htm
- Census Economic Indicators RSS: https://www.census.gov/economic-indicators/indicator.xml
- Census Economic Indicators API: https://www.census.gov/data/developers/data-sets/economic-indicators.html
- BEA API: https://apps.bea.gov/api/
- BEA release schedule: https://www.bea.gov/news/schedule
- Federal Reserve/FOMC calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- Federal Reserve monetary-policy RSS: https://www.federalreserve.gov/feeds/press_monetary.xml
- CFTC Commitments of Traders: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- CFTC release schedule: https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm
- IMF IRFCL reserves dataset: https://data.imf.org/Datasets/IRFCL
- WGC central-bank reserves: https://www.gold.org/goldhub/data/gold-reserves-by-country
- WGC ETF holdings/flows: https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows
- WGC gold driver framework: https://www.gold.org/goldhub/tools/gold-return-attribution-model
- FRED Global Economic Policy Uncertainty: https://fred.stlouisfed.org/series/GEPUCURRENT
- FRED daily US Economic Policy Uncertainty: https://fred.stlouisfed.org/series/USEPUINDXD
- St. Louis Fed Financial Stress Index: https://fred.stlouisfed.org/series/STLFSI4
- Chicago Fed National Financial Conditions Index: https://fred.stlouisfed.org/series/NFCI
- FRED 10-year breakeven inflation: https://fred.stlouisfed.org/series/T10YIE
- FRED real-time Sahm recession indicator: https://fred.stlouisfed.org/series/SAHMREALTIME
- FRED observations API: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- World Bank Global Economic Prospects: https://databank.worldbank.org/source/global-economic-prospects
- World Bank advanced data API: https://datahelpdesk.worldbank.org/knowledgebase/articles/1886686-advanced-data-api-queries
- CFTC public Disaggregated Futures Only API: https://dev.socrata.com/foundry/publicreporting.cftc.gov/72hh-3qpy

## Point-in-time rules

Current FRED observations can be revised and are not safe for historical model
training. Use ALFRED vintages or locally archived releases for backtests. CFTC
positions represent Tuesday and are generally released Friday; central-bank
and ETF series also arrive with delay and may be revised. Their publication date
must not be backfilled into earlier rows.

## Secondary candle APIs

The runner supports OANDA and Twelve Data. They are fallbacks for the same
`API_CANDLES` role, not two independent votes. A second vendor does not make two
copies of the same methodology statistically independent.
