# Scalper Expert 3.20 — continuation scalp and economic release context

October 1, 2026. Main EA: `mql5/Experts/GoldScalpAI/GoldScalpAI.mq5`.
Advisor 1 is unchanged. All resources use native/free MT5 facilities.

## Diagnosis and changes

The existing bot was running, unlocked and trading: five new completed positions
since the earlier loss pause, three winners and two losers, net -$1.19. These held
for 10–54 seconds. Combined account EA history showed 20 completed positions,
40% wins, Profit Factor 0.55 and -$6.09 net. These are losing demo observations,
not a reason to claim that simply trading faster creates an edge.

Changes implemented:

- Irregular tick windows include one bounded bracketing observation. The
  one-second micro window accepts three genuine quotes; it previously required
  four and was often unavailable on approximately two-observation/second feeds.
  Stale-quote checks and the ten-observation/second sampling limit remain.
- Entry persistence is **1 second**, ordinary re-entry spacing **3 seconds**,
  previously 2 and 8. Evidence, cost, risk and broker checks still apply.
- A separate **20-second trend-continuation entry lane** can qualify smooth
  movement without the fast direction flag. It requires aligned M1/M5 context,
  efficient 20-second movement of at least two spreads, supportive eight-second
  flow, no materially opposing fast flow, and four extra evidence points.
  This supplements the 3/8-second impulse lane; it does not force permanent exposure.
- **Same-direction continuation** joins opposite-direction rapid re-entry after
  a broker-confirmed profitable exit, including profitable broker stop exits.
  It needs a flat account, no unresolved deal request, reconciled exposure,
  strong fresh micro flow and score at least six points above the ordinary threshold.
  Minimum rearm remains 750 ms, adapting to measured acknowledgement latency;
  authorization expires after ten seconds. Losing exits receive normal cooldown.
- **Earlier profit exit** can bank a small net winner before the fixed $0.35
  percentage-trail arming threshold when opposing micro flow persists 500 ms and
  profit retreat exceeds quote/execution noise. The 33% giveback, ATR stop,
  breakeven and trailing protections remain. This detects current deterioration;
  it cannot know a future reversal or guarantee a positive fill.
- Fixed 0.01 lots, max three account positions/orders, no averaging down,
  36 entries/hour, loss pauses and existing equity/rolling-loss limits remain.
  Session outcome adaptation starts a new `ScalperExpert320:S0..3` cohort.
- Corrected slippage telemetry: some broker callbacks omitted the requested
  price, previously producing an impossible -$4,140.21 reading. Measurement now
  uses the saved request correlated by ID; unavailable prices produce null.

## Economic releases

The native news worker now exports a bounded economic context feed alongside the
existing blackout feed. It includes high-importance USD events plus named ADP,
PCE and GDP releases over the previous/next 24 hours, up to 64 events. It refreshes
every 30 seconds, every 5 seconds near selected release times, on a separate
script thread. The EA reads cached files every five seconds, outside OnTick.

The browser shows release names, server times, actual, forecast, previous value
and units/multipliers. Missing actuals remain **NA**; future actuals are suppressed.
Actual/forecast values are the native MT5 calendar's data, not independently
verified consensus forecasts. The supplied screenshot is a reference to event
types, not an authoritative live timetable. The installed feed includes ADP,
Core PCE m/m and y/y, GDP and upcoming claims/PMI releases.

The strategy deliberately does not hard-code “higher inflation = buy gold” or
“higher GDP = sell gold”. For a newly observed release with an actual value,
it can record the current gold quote within 120 seconds of the scheduled release.
After at least 20 seconds, a response larger than twice the current spread adds
or subtracts at most **two evidence points**, according to alignment with the
candidate scalp. This is observed price response, not proof of news causality.
It expires after 30 minutes; a stale feed contributes zero. Starting the bot long
after a release does not invent a historical response baseline. Existing news
blackouts remain in force. Several simultaneous reports are treated as a release
window; the bot does not sum their surprises into a fabricated directional forecast.

## Validation

- Five MQL5 programs: zero compilation errors/warnings.
- 176 native invariant checks and 46 Python tests passed; seven browser checks passed.
- Native diagnostic on the unchanged 285,799-observation fixture: 34,305 raw
  qualifying impulse observations and 9,592 neutral-context score-62 observations,
  versus 31,543 and 8,648 before the window adjustment. Counts overlap in time;
  they are **not trades, independent opportunities or a profitability backtest**.
- Native macro tests cover file transport, missing/future data, freshness and
  bounded response evidence. Execution tests cover continuation preconditions,
  sparse micro quotes, early exit persistence/noise and slippage availability.
- All 18 protected Advisor 1 file hashes match the baseline.

Live and browser checks are recorded in
`mql5/validation/scalper-expert-320-validation.json`. No completed 3.20 performance
study exists. The demo balance remains approximately $23,642; it does not establish
margin feasibility on the intended $100 account. Forward outcomes and a full
real-tick, fee/delay-aware strategy backtest remain necessary.

## Restart

Close MT5 normally before restarting the main EA:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_scalp_mt5.ps1 -DemoOrders
```

Restart the two browser pages in another PowerShell and keep that window running:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\restart_gold_dashboards.ps1
```

Main: http://127.0.0.1:8766/ ; Advisor 1: http://127.0.0.1:8766/advisor .
Refresh existing pages with Ctrl+F5. VS Code need not stay open.

## Primary research references

- [MQL5 calendar structures](https://www.mql5.com/en/docs/constants/structures/mqlcalendar):
  actual/forecast missing-value handling, million-scaled storage and unit multipliers.
- [CalendarValueHistory](https://www.mql5.com/en/docs/calendar/calendarvaluehistory):
  native currency-filtered release history and upcoming events.
- [Economic calendar](https://www.mql5.com/en/docs/calendar): release times use the
  trade server timezone; screenshot/local clock times must not be assumed equivalent.
- [BEA PCE](https://www.bea.gov/data/personal-consumption-expenditures-price-index):
  official definition and links to monthly releases.
- [BEA release schedule](https://www.bea.gov/news/schedule): official publication dates.
- [ADP employment report](https://adpemploymentreport.com/): private-sector employment
  measurement; it is not interchangeable with the government payroll report.
- [MQL5 trade result](https://www.mql5.com/en/docs/constants/structures/mqltraderesult):
  request-ID correlation and execution-result fields.
