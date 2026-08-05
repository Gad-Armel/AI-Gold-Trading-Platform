# V6.3.6 Operating Guide — Tick-Horizon Fast Research

## FAST tick-horizon lane

MT5 standard bars begin at M1, so FAST constructs 1-second and 5-second
decision horizons from bid/ask ticks. Both horizons must agree with the signal;
the 3-second quote-flow proxy must also align. Spread is capped at $0.20,
tick-data quality at 0.75 minimum, and maximum hold at 15 seconds. FAST is
shadow-only and cannot be passed into the controlled-demo execution gate.

## V6.3.5 regime consistency

The executable STRICT hypothesis cannot enter when unified context explicitly
reports `NO_TRADE`, or when a directional context regime opposes the candidate.
BALANCED applies the same protection; EXPLORATORY remains a counterfactual
research lane. The learning profile now records verified `adx_m5` correctly.

## V6.3.4 entry protection

The STRICT main-bot lane now reads the production microstructure window keys
`1`, `3` and `5`. Entry requires at least 0.70 tick-data quality, aligned
3-second quote-flow imbalance of at least 0.10, no more than 0.04 ATR of spread
expansion, and a tape regime other than `STALLED` or `DISLOCATED`. These are
pre-entry safeguards; they do not claim or guarantee profitability.

## Failed-thesis reset

After `NO_PROGRESS_THESIS_EXIT` or `STRONG_OPPOSITE_TAPE_EXIT`, the same lane
cannot re-enter the same candidate direction until the directional thesis
actually resets. A transient gate failure is insufficient. This avoids paying
the spread repeatedly inside one failed market episode.

The terminal prints process-session shadow P/L after each close and when the
loop stops. V6.3.2 history is retained for audit but excluded from V6.3.3 model
training and performance ranking.

## Candle-only benchmark

Run this separately from the main shadow loop:

```text
python run_candle_follow_shadow_loop.py --max-minutes 0
```

It fades the live M1 candle: green sells, red buys and a doji waits. Its target
is $0.40 and maximum hold is five seconds; after closing it may re-enter on the next 0.25-second loop
cycle, even within the same candle. It uses separate state/history, charges the
observed bid/ask spread on every attempt and can never authorize execution.

## Conservative shadow fills

For `TRIPLE_BARRIER_TARGET`, the shadow history books `final_profit_usd` at the planned target. The later polled quote is retained separately as `observed_market_profit_usd`.

For `TRIPLE_BARRIER_HARD_STOP`, the full adverse observed quote remains charged. This asymmetric policy avoids optimistic research results:

```text
profitable target gap -> planned target fill
adverse stop gap      -> observed executable quote
```

The console reports any uncredited target overshoot explicitly.


## Install and validate

```text
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" -m pip install -r ".\requirements.txt"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_scalping_all_tests.py"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_scalping_audit.py"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_unified_news_update.py"
```

## Run shadow research

```text
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_scalping_shadow_loop.py" --max-minutes 0
```

Run the separate medium-horizon model (stop the main loop first because both
use the same MT5/process lock):

```text
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_medium_horizon_shadow_loop.py" --max-minutes 0
```

This runner is shadow-only. It prints M45/H1/H2/H4 direction, consensus,
currently open positions, and session/cumulative net P/L, expectancy, win rate,
and profit factor. Press `CTRL+C` to stop without fabricating an exit; open
shadow positions remain in the isolated state file and resume monitoring on the
next start.

The initial two-year historical screen failed all performance approval checks,
so medium-model entries are blocked by default. This is intentional. The
downloaded broker dataset and latest conservative report are under
`data/research/medium_horizon/`. A revised hypothesis must be selected on a
training period and pass a genuinely untouched chronological holdout before
`SCALPING_MEDIUM_ENTRY_ENABLED` may be reconsidered.

## Review results

```text
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_v6_lane_review.py"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_v63_self_learning_review.py"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_v63_model_status.py"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_v6_walk_forward_review.py"
```

`run_v63_self_learning_review.py` trains a challenger only after enough de-correlated base-lane outcomes exist. It cannot create broker orders.

## Upgrading from V6.2.1

Copy only:

- `.env`
- `data/research`

Do not copy:

- `data/runtime`
- `data/microstructure/state`
- `data/models/v63`
- lock or temporary files

A new V6.3 model must be trained and validated under the V6.3 settings.

## Prohibited

Do not enable real execution. Do not manufacture or duplicate history to reach the minimum sample. Do not edit an approval or model registry manually.


## V6.3.2 model diagnostics

Model artifact format 3 reserves the final chronological fold as an untouched
promotion holdout. Existing format-2 champions are intentionally rejected and
must be retrained from genuine closed shadow outcomes.

After enough independent closed shadow episodes, run:

```
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_v63_self_learning_review.py"
```

The model report now includes selected-fold stability, the confidence-aware win-rate lower bound and OOS permutation importance. Do not use feature importance to manually lower gates; it is diagnostic only.
