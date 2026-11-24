# Integrated experimental XAUUSD build — September 10, 2026

The project now has a working connection from historical training to live candle
inference, entry filtering, adaptive exits, a simulated $100 portfolio, dashboard
telemetry and recorded forward results. This is an experimental trading system;
the learned forecast has **not demonstrated a profitable edge**. Advisor 1 was
preserved byte for byte.

## Run the integrated experiment

Open MT5 and log in so the terminal can supply XAUUSD quotes. In PowerShell:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
python .\run_gold_ai.py --max-minutes 60
```

This starts the main bot with adaptive exits, the experimental learned filter,
the local dashboard, and a **new simulated $100 account**. It sends no orders.
Use `--max-minutes 0` to continue until Ctrl+C. Only run one main bot at a time.
The main runner also defaults to adaptive exits when called directly;
`--exit-policy legacy` remains an explicit comparison option.

Compare against the existing adaptive policy, without the learned veto:

```powershell
python .\run_gold_ai.py --learned-policy off --max-minutes 60
python .\tools\report_gold_ai.py
```

These are separate sessions, potentially in different market conditions; their
raw P/L difference does not establish causation. Every session is retained,
including losing sessions. A restart opens a new experiment, not a continuation
of the previous paper balance. Unexpectedly interrupted paper sessions retain
their last recorded positions for review; they are not silently resumed.

For broker demo execution using the existing adaptive controller and learned
forecasts in **observation only**:

```powershell
python .\run_gold_ai.py --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 60
```

The demo default deliberately observes the failed research candidate. An explicit
`--learned-policy filter` enables the experimental entry veto and learned exit
signal on demo as well. This does not mark the model validated or enable real
accounts. The main broker retains its demo-account authorization checks.

## What controls decisions

1. Existing MT5 candle, tick-flow and independent-feed evidence builds the lane
   decisions. Existing scheduled-news and economic conflict checks remain active.
2. A fitted gradient-boosted regressor for each of M5, M15 and H1 forecasts the
   change in bid close over the next three completed bars. Nine causal features
   describe trend, momentum, volatility, directional efficiency and candle gaps.
   These are learned numerical forecasts, not calibrated probabilities.
3. Filter mode can reject an otherwise permitted entry when estimated return
   after current spread and $0.10 modeled round-trip slippage is below $0.25.
   Forecasts are re-anchored at the current quote; an already-realized move is not
   counted again. A model cannot override a news, data, capital or position block.
4. Adaptive structure/volatility exits remain active. Filter mode can also close
   after two distinct completed candles forecast sufficiently adverse remaining
   movement. Repeated ticks do not count as additional confirmations. Learned
   entry vetoes do not disable the existing protective reversal signal.
5. Risk management remains independent: at most **three positions total**, exactly
   **0.01 lot per entry**, one per lane in adaptive mode, $2 planned stop exposure
   and the $5 rolling 24-hour realized-plus-floating loss circuit breaker. There
   is no ordinary fixed profit target in adaptive mode. Emergency stops remain.

The learned component forecasts remaining movement; it is not a reinforcement
learning agent trained to optimize the full value of every held position. News
is presently authoritative context/veto, not a learned historical feature: the
project does not yet have a verified historical publication-time news dataset.
Future announcements mean known release schedules, never knowledge of the
unpublished outcome. No unsupported claim of institutional order visibility is
used to authorize a trade.

## Paper account behavior

Paper execution uses observed bid/ask and $0.05 adverse slippage on each fill.
Margin requirements come from a read-only MT5 calculation and are reserved
against the simulated equity. The accounting requires USD and a 100-ounce
XAUUSD contract, making 0.01 lot one ounce. It checks the position cap, lane cap,
spread, analysis levels, entry zone, minimum stop distance, planned stop risk,
loss breaker and available margin before simulated entry.

Stops fill at the next observed executable quote, including adverse gaps; they
are not guaranteed fills at the ideal stop price. The approximately two-second
sampling can miss intervening price movement. Actual broker execution, latency,
commission, financing, margin liquidation and every intratick path are not fully
replicated. Paper shutdown uses the last valid sampled quote and records that
reason. A stale final quote can leave positions recorded as open.

## Training and measured results

```powershell
python .\tools\train_gold_ai.py
python .\tools\validate_gold_changes.py
```

Training uses the existing 50,000-bar CSV for each timeframe, one fixed model
configuration, a 60% chronological training segment, 20% validation, 20% test,
and a three-bar purge before validation. Features use finite trailing windows
shared with live inference; unfinished candles are excluded. Training does not
automatically refit on or optimize against the test segment. The earlier project
research already inspected these historical periods, so this is not a newly
untouched holdout. Models retain the historical training cutoff and must be
treated as experimental, particularly under changing market conditions.

| Frame | Validation profit factor | Test profit factor | Test net, USD | Forecast MAE / no-change MAE |
|---|---:|---:|---:|---:|
| M5 | 0.690 | 0.762 | -139.50 | 4.324 / 4.322 |
| M15 | 0.986 | 0.922 | -207.58 | 8.231 / 8.177 |
| H1 | 0.892 | 0.799 | -1,224.52 | 14.569 / 14.402 |

These are **forecast-only diagnostic trades**, using a $2 emergency stop and a
three-bar evaluation horizon. They are not an exact backtest of the integrated
consensus/news/adaptive-exit controller. The diagnostic intentionally reports
unconstrained trades rather than pretending a $100 account can sustain its full
drawdown: it does not model the daily circuit breaker or margin, and its equity
can become negative. The operational paper account does enforce those controls.
All three forecasts failed this research check and slightly underperformed the
no-change forecast on MAE. Increasing modeled costs also worsened results.

The short live-data integration check completed four cycles, produced M5/M15
forecasts, kept a stale H1 context blocked and placed no paper trades because
entry conditions were not met. It verifies wiring and abstention, not trading
profitability. Unit tests separately exercised simulated fills, gap stops,
account reconciliation, model exits, stale-data rejection and position limits.

## Files and evidence

| Program / directory | Purpose |
|---|---|
| `run_gold_ai.py` | Integrated launcher; paper/filter by default, demo/observe by default |
| `run_gold_consensus_bot.py` | Shared execution loop and dashboard |
| `services/research/gold_learned_policy.py` | Shared causal features, inference, entry veto and learned exit signal |
| `services/execution/gold_paper_portfolio.py` | Isolated simulated account; no order-send capability |
| `tools/train_gold_ai.py` | Deterministic training and chronological diagnostics |
| `tools/report_gold_ai.py` | Summaries and accounting reconciliation across all paper sessions |
| `data/research/gold_ai/evaluation.json` | Results, limitations, source hashes and model IDs |
| `data/research/gold_ai/*.joblib` | Locally trained experimental weights; load only trusted local artifacts |
| `data/research/gold_paper/<run>/` | Account snapshot and closed-trade journal, including model assessment at entry |
| `data/research/gold_forward/` | Sampled quotes and point-in-time decisions, including learned forecasts |

The dashboard shows forecast edges, historical validation profit factor, paper
balance/equity/drawdown, positions and exit explanations. Protected Advisor 1
still runs independently with `python .\run_gold_advisor.py --interval-seconds 60`.
The standalone V6.4 display was retired on September 14. Its shared data services remain integrated in the main bot.

The next evidence needed is forward performance across enough eligible trades
and market conditions, plus publication-time historical news data for any
learned news component. Training a larger network or downloading a sentiment
model does not establish that missing evidence.

## Implementation references

- [Scikit-learn histogram gradient boosting regression](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html): model API and deterministic estimator settings; random early-stopping splits are disabled here.
- [Scikit-learn chronological splitting and gaps](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): motivation for chronological evaluation and separation gaps. This trainer uses explicit chronological indices.
- [MT5 margin calculation](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py): read-only margin estimate used by the paper account.
