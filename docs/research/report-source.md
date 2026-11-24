# XAUUSD trading-bot deep research review

- Audience: project owner and future engineering reviewers
- Review date: 2026-09-07
- Scope: decision policy, execution, economic news, USD/rates, positioning,
  central-bank/ETF demand, time-series validation and dashboard observability
- Constraint: Gold Advisor V1 is protected; improvements are implemented around
  it or in Economic Advisor V5.

## Executive answer

The defensible architecture is horizon-aware. Fresh executable MT5 data and
technical evidence remain entry authority. Verified release surprises can affect
very short horizons briefly. Daily USD/yield/risk variables affect intraday and
swing context. CFTC, ETF and central-bank data are too delayed for scalp timing
and may only provide swing context. No heuristic score is a calibrated win
probability, and no configuration can guarantee profits.

## Findings translated into code

1. **Source diversity, not vote duplication.** V1 and V2 apply related analysis
   to different feeds, while V3 contributes tick flow. SCALP therefore requires
   tick flow plus another strong usable source. INTRADAY/SWING require MT5 and
   independent API candles. A failed API no longer disables a valid MT5-based
   scalp, but longer lanes remain blocked.
2. **Elapsed-time confirmation.** A two-second loop must not turn an unchanged
   snapshot into multiple independent confirmations. Signals now persist for
   5/15/30 seconds before entry. The second position requires 90/90/92 evidence
   and 15/30/60 seconds spacing.
3. **Execution economics.** Directional evidence can ignore absolute spread as
   requested, but an order still must be economically tradable. Spread may not
   consume more than 35% of analysed reward, reward/risk must be at least 0.70,
   and current executable price must remain in the analysed entry zone.
4. **Surprise, not headline direction.** `actual - forecast` is normalized by an
   indicator-specific scale: payrolls, inflation, unemployment, claims, retail
   sales, GDP and policy rates no longer share an invalid common denominator.
   Percent, K/M/B units are parsed. Future, estimated and unverified releases
   protect the calendar but never predict direction.
5. **Continuous macro pressure.** USD, real yields, nominal yields and VIX use
   scaled magnitudes rather than maximum-strength sign switches. Conflicting
   inputs reduce quality through a coherence penalty.
6. **Slow demand provenance.** Central-bank tonnes, ETF tonnes and CFTC managed-
   money changes require a source and observation timestamp. Stale or anonymous
   records receive zero quality. Magnitudes saturate smoothly rather than
   becoming all-or-nothing votes.
7. **No weak-bias inversion.** The prior idea that BUY evidence from roughly
   15-75 implies SELL is an anecdotal hypothesis, not validated causal evidence.
   Deterministic inversion remains disabled; it may only be evaluated later as
   a pre-registered challenger on untouched data.
8. **Operational observability.** The dashboard now exposes local analysis and
   validity times, all possible TP levels, analysis SL, evidence, source health,
   temporal confirmation, Economic V5, live demo positions, lane P/L, the last
   30 closed trades per lane and non-destructive reset controls.
9. **V6.4 confirmation-point accounting.** V6 turns each usable economic input
   into a bounded contribution: allocation x directional magnitude x freshness
   x source quality. Agreement with the final horizon direction adds points and
   disagreement subtracts points. Closely correlated observations first become
   one coherent source family. The SWING budget is 10 release-surprise, 20
   USD/yields/VIX, 5 daily US uncertainty, 5 global uncertainty, 10 systemic
   financial stress, 7.5 inflation/recession, 5 World Bank growth, 20 central-
   bank demand, 10 physical ETF flow and 7.5 CFTC managed-money flow points.
   The result is an auditable evidence-strength score, not a win probability.
10. **Resilient official-data collection.** Sixteen FRED series and the World
    Bank Global Economic Prospects world-growth path are fetched in a bounded
    pool. A failed keyed FRED call gets one graph-CSV fallback. A fully failed
    source keeps its last valid observation timestamp so quality continues to
    decay instead of silently becoming fresh or disappearing.
11. **Short-horizon official release monitor.** Census Economic Indicators RSS,
    Federal Reserve monetary-policy RSS and the BEA API are refreshed outside
    the scoring loop and cached. Census/Fed items retain their authoritative
    publication time. BEA GDP and core-PCE values create an event only when the
    running cache detects a new period or revision. A change versus the prior
    value is explicitly separated from an actual-versus-consensus surprise and
    capped at 35% source quality. SCALP never uses that prior-value comparison;
    instead, it can receive at most 30 points from a range-scaled XAUUSD move
    measured after a verified official release. The reaction expires after 12
    minutes for SCALP and 60 minutes for INTRADAY.
12. **Compact V6 display.** The console now stops after the three horizon rows,
    as requested. Full source diagnostics remain in the JSON report for audit
    and debugging without cluttering the visible advisor.

## Evidence base

- The World Gold Council groups gold drivers into expansion, risk/uncertainty,
  FX opportunity cost, interest-rate opportunity cost and momentum; the
  relationships change through time. Source:
  https://www.gold.org/goldhub/tools/gold-return-attribution-model
- WGC notes that a simple real-yield/USD model can fail under structural shifts;
  those variables are useful features, not deterministic rules. Source:
  https://www.gold.org/goldhub/research/qaurum-vs-us-real-rates-and-dollar-model
- Federal Reserve research finds that macro announcements move exchange rates
  and rates quickly, while volatility and volume can remain elevated longer.
  Sources:
  https://www.federalreserve.gov/econres/ifdp/the-high-frequency-response-of-exchange-rates-and-interest-rates-to-macroeconomic-announcements.htm
  and https://www.federalreserve.gov/Pubs/ifdp/2004/823/ifdp823.htm
- An IMF event study reports gold sensitivity to scheduled US and euro-area
  announcements including retail sales, non-farm payrolls and inflation, while
  emphasizing that the response is state-dependent. Source:
  https://www.imf.org/external/pubs/ft/wp/2009/wp09140.pdf
- Intraday gold research finds meaningful reactions to CPI, unemployment, GDP
  and PPI announcements, and reports that much futures-price adjustment can
  occur in the first minute. Source:
  https://doi.org/10.1016/S0148-6195(00)00029-1
- Recent high-frequency FOMC research finds that gold adjustment can continue
  beyond five minutes after a monetary-policy shock. Source:
  https://doi.org/10.1016/j.irfa.2024.103486
- Market responses to macro news vary by regime and investor attention. Sources:
  https://www.federalreserve.gov/econres/feds/how-markets-process-macro-news-the-importance-of-investor-attention.htm
  and https://www.nber.org/papers/w19523
- CFTC COT represents Tuesday positioning and is generally published Friday, so
  it cannot be a tick-level trigger. Sources:
  https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm and
  https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm
- WGC ETF holdings and flows are weekly/monthly. Source:
  https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows
- The FRED GEPUCURRENT series is a monthly Global Economic Policy Uncertainty
  index. It is used only as fading SWING regime context. Source:
  https://fred.stlouisfed.org/series/GEPUCURRENT
- The daily US EPU index is newspaper-based and is smoothed as a five-day mean
  relative to a twenty-day mean before use. Source:
  https://fred.stlouisfed.org/series/USEPUINDXD
- The St. Louis Fed and Chicago Fed financial-condition indexes are weekly and
  are combined into one systemic-stress family to avoid double counting.
  Sources: https://fred.stlouisfed.org/series/STLFSI4 and
  https://fred.stlouisfed.org/series/NFCI
- The 10-year breakeven inflation rate is market-implied expected inflation;
  the real-time Sahm indicator signals recession only after a 0.50 percentage-
  point unemployment threshold. Their mixed/conditional gold effect justifies
  a small combined allocation. Sources:
  https://fred.stlouisfed.org/series/T10YIE and
  https://fred.stlouisfed.org/series/SAHMREALTIME
- World Bank Global Economic Prospects growth is semi-annual. Deceleration is
  treated as modest defensive/rate-cut context, never an intraday trigger.
  Sources: https://databank.worldbank.org/source/global-economic-prospects and
  https://datahelpdesk.worldbank.org/knowledgebase/articles/1886686-advanced-data-api-queries
- Central-bank reserve managers cite crisis performance, diversification,
  inflation hedging and geopolitical-risk protection as reasons for holding or
  increasing gold. This supports the structural sign of net buying, not a
  claim of immediate causality. Source:
  https://www.gold.org/goldhub/research/central-bank-gold-reserves-survey-2026
- WGC explicitly warns that central-bank reports can be delayed and revised. A
  recent example revised Q1 2026 demand from 244t to 57t, demonstrating why this
  cannot be treated as contemporaneous execution data. Source:
  https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q2-2026/central-banks
- Official reserve series are available from IMF IRFCL, with the usual reporting
  and data-quality limitations. Source: https://data.imf.org/Datasets/IRFCL
- Release protection uses official schedules where possible: Federal Reserve
  FOMC calendar and BLS CPI schedule. Sources:
  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm and
  https://www.bls.gov/schedule/news_release/cpi.htm
- Census publishes an official Economic Indicators RSS feed and API covering
  retail sales, durable goods, trade, housing and other timely releases.
  Sources: https://www.census.gov/economic-indicators/indicator.xml and
  https://www.census.gov/data/developers/data-sets/economic-indicators.html
- The Federal Reserve provides an official monetary-policy RSS feed. Source:
  https://www.federalreserve.gov/feeds/feeds.htm
- BEA states that its API programmatically exposes published official economic
  statistics. Its standard limit is 100 requests per minute; V6 uses only two
  cached table calls per refresh. Sources: https://apps.bea.gov/api/ and
  https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf
- Model calibration data must remain separate from fitting data, and time-series
  splits must preserve chronology. Sources:
  https://scikit-learn.org/stable/modules/calibration.html and
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Trying many strategy variants increases backtest-overfitting risk and expected
  out-of-sample degradation. Source:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659

## Limitations and non-claims

- The advisor evidence scale is heuristic, not a calibrated probability.
- Central-bank activity may remain unreported; geopolitical narratives are not
  machine-readable surprises and should not be guessed from headlines.
- FRED current observations can contain revisions. Historical tests require
  point-in-time vintages.
- Two XAUUSD price vendors observe the same market and are not independent alpha.
- A $5 lane target with the configured stop policy can still have poor realised
  reward/risk after spread, slippage and two simultaneous losses. Demo forward
  evidence must determine whether sizing and exits survive costs.
- Tests prove software behavior, not trading profitability. Promotion to any
  live workflow requires a large untouched forward sample and explicit human
  authorization; this repository remains demo-only.
- An FMP economic-calendar verification returned HTTP 402 on 2026-09-07, and
  no FMP key is currently configured. Official schedules still protect
  event windows, but they do not contain market-consensus forecasts; therefore
  SCALP remains WAIT outside a verified actual-versus-forecast release. This is
  a data-licensing limitation, not a reason to invent confidence.
- The BLS documents a one-day lag between publication and Public Data API
  availability. Its official RSS endpoints also returned HTTP 403 from this
  runtime after one bounded user-agent retry. BLS therefore remains a verified
  schedule/protection source, not a falsely labeled live directional feed.
- Comparing an official value with its previous release does not measure market
  expectations. It receives a low quality cap and cannot create a SCALP vote.
- Post-release XAUUSD movement is contemporaneous confirmation, not proof of
  causation, and it can reverse. It is range-scaled, time-decayed and bounded.

## Validation ledger

- 44 focused V6.4 tests passed on 2026-09-07. They cover the official RSS/BEA
  parsers, key non-leakage, previous-release quality cap, market-reaction expiry,
  exact 100-point budgets, macro/institutional fallbacks and compact console.
- 38 focused V6.3 tests passed earlier on 2026-09-07 for the FRED API/CSV/cache fallback
  paths, World Bank parsing, economic direction and freshness, expanded release
  mappings, confirmation-point arithmetic, institutional provenance and V6
  display behavior.
- An earlier 55-test focused suite passed on 2026-09-07 for consensus, horizon
  policy, broker controls, Economic V5, news normalization, institutional
  provenance and dashboard routes.
- Broad discovery ran 98 tests on Python 3.11: 96 passed. Two pre-existing V3
  checks remain outside this V6.4 change: one expects the intentionally removed
  standalone `run_gold_advisor_v3.py`, and one synthetic upward-tick fixture
  does not clear every horizon's V3 action threshold. The V6.4 focused suite is
  clean; these two findings must not be represented as V6 regressions.
