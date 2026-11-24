# Continuous scalp review and measured results — September 15, 2026

The incomplete flow-primary implementation has been repaired and regression
tested. It is an experimental strategy candidate, not a demonstrated profitable
AI trader. No broker orders were submitted during this review. An existing bot
held the runtime lock; it was neither stopped nor restarted.

## What was retained

Scalp uses tick-advisor evidence on its own scale (60), with a usable opposing
candle source at 72 or above acting as a veto. Completed M1 candles supply ATR
and structure. Intraday and swing retain their two-source candle requirements.
There is one adaptive position per lane, three total, exactly 0.01 lot each.
Scalp remains first in the entry iteration order. This does not reserve CPU
time, guarantee execution latency, or establish an advantage over slower trades.

Adaptive exits do not wait for a fixed TP. The system combines protective stops,
news restrictions, sustained quote reversals, a profit giveback trail, a
breakeven trigger and a heuristic support score. The support score is not a
probability, consciousness or a learned hold/close policy.

## Defects corrected beyond the original failing fixtures

- **Observation mode leaked into execution.** Learned and dollar forecasts
  could influence the support score and therefore exits even in observation
  mode. The runner now excludes them from execution scoring unless their
  respective filter/protect policy is enabled. They remain visible as research.
- **Wrong risk unit.** Scalp and swing inherited a $4 cumulative lane threshold
  for trailing protection despite the $2 per-entry risk ceiling. The runner caps
  the risk unit at $2, and adaptive protection binds to the initial observed stop
  distance when it is smaller. Later stop changes cannot expand this reference.
  This is an engineering exposure bound, not a guaranteed maximum loss.
- **Unobservable short window.** Four samples in three seconds were incompatible
  with a two-second loop. Flow now uses 6/12/30-second windows, requires adequate
  span and at least two warmed windows, and rejects stale/future quotes.
- **False support and acceleration.** No opposing flow previously translated to
  full positive support. Quiet flow is now neutral. Acceleration compares rates
  across windows instead of comparing unequal accumulated distances. One-sided
  spread changes cannot create directional flow.
- **Stale level reference.** Scalp ATR levels now anchor to the executable ask
  for buys and bid for sells, not the previous candle close. Invalid volatility
  and non-finite evidence cannot authorize a trade. The reported scalp threshold
  now matches the actual flow gate.
- **Incorrect loss accounting.** Close retries previously counted floating loss
  repeatedly, and broker-stop exits escaped streak accounting. Churn protection
  now reconciles completed net fills, deduplicates entries, rebuilds recent
  history on restart, and blocks re-entry while a known close remains
  unreconciled. History failure blocks new scalp entries. Dashboard history
  resets do not reset this protection. Existing protective exits remain active.
- **M1/M5 forecast identity mismatch.** The older learned scalp model still uses
  M5 input. Its cache and confirmation identity now use the actual M5 bar, so
  each M1 management update cannot count the same forecast as new evidence.
- **Insufficient research recording.** Open scalp positions now receive a
  two-second recording heartbeat; flat scalp observations use ten seconds.
  Records include micro-flow, timing blocks and churn telemetry. This supplies
  better examples for a future learned exit policy without manufacturing labels.

The dashboard now displays quote-flow status, pressure, reversal strength,
entries per hour, loss streak and execution-history availability.

## Offline measurements

Run the audit without connecting to MT5:

```powershell
python -B .\tools\audit_continuous_scalp.py
```

The final reviewed capture contained 32,231 quote observations. Flow was
available on 22,985 observations, and 1,834 observations failed the strict
two-second quote-age check. The flow engine averaged about 82 microseconds per
observation on this machine (about 77.5 microseconds on the final run). This measures the isolated flow engine, not the
full bot, broker latency or order completion.

Of 2,668 sampled scalp decision records, the old authority test qualified one;
the flow-primary authority test qualified 224 (about 8.40%). This deliberately
isolates signal authority. It does not include M1 availability, micro-flow
agreement, news, cost, margin, timing or risk gates, and is not a fill forecast.

A fixed StandardScaler + Ridge(alpha=100) experiment predicted the bid change
30 seconds ahead using only previously observed flow features. There were
9,086 training examples, 6,066 later test examples and 13 purged examples whose
labels crossed the boundary. Test mean absolute error was **0.650695 USD/oz**;
the zero-change baseline was **0.647910 USD/oz**. The model was worse overall
and in three of four chronological test blocks. It was not promoted, saved as
an executable model or connected to trade control.

A separate diagnostic of 476 non-overlapping, flow-directed 30-second holds
averaged **-0.3133 USD** at one-ounce exposure, including recorded spread and
0.05 price slippage on each fill. This is **not a backtest of the main bot**:
it omits its stops, candle/news gates, margin limits, commission and swap.
Its purpose is to test the assumption that flow direction alone overcomes
costs. This capture does not support that assumption.

The JSON report is `data/research/continuous_scalp/audit.json`. The input
manifest hashes the exact quote bytes read. Files may continue to grow while
the user's existing bot runs, so later audit counts can differ. Overlapping
forecast labels are correlated; no independent-trade significance is claimed.
These recordings also helped design thresholds, so this is development
evidence, not pristine forward validation.

## Verification and operation

The original state ran 190 tests with eight failures and two errors. The review
now passes 210 tests, including buy/sell flow, stale and repeated observations,
spread-only moves, net-fill reconciliation, cooldowns, risk anchoring and
forecast-time separation. Existing tests for three total positions, 0.01 lots
and broker execution guards remain in the suite. Both protected Advisor 1
source hashes are unchanged.

```powershell
python -B .\tools\validate_gold_changes.py
```

Stop the existing bot with Ctrl+C before starting another instance. The configured
shutdown may close its controlled demo positions. Code edits do not update the
already-running process. To evaluate this candidate using live MT5 quotes and a
simulated $100 account, with learned and dollar forecasts kept observational:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
python .\run_gold_ai.py --learned-policy observe --cross-market-policy observe --max-minutes 60
```

The existing demo command remains supported. It places demo orders; this review
does not establish that using it will improve returns. No real-account execution
has been enabled. Source archives and useful regression tests were preserved.

## Research basis and next evidence

Chronological evaluation must not train on later examples or labels overlapping
the test period; see [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
Net deal accounting includes separate commissions and other costs; see
[MT5 deal properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties).

The next meaningful performance test is a forward paper comparison of the full
candidate against the prior policy using matching market periods, costs and
risk limits. A learned hold/close model requires sufficiently dense position
trajectories and causal outcome labels. Neither heuristic votes nor a failed
short-term regression can substitute for that evidence.
