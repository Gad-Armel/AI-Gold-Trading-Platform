# Scalp feed reliability and faster protection — September 15, 2026

The user's paper run ended with `KeyError: 'timestamp'` after 257 cycles.
Its last saved tick-history age was 914.365 seconds. The tick advisor regenerated
a current report around old data without declaring the whole source unavailable.
When MT5 subsequently returned an empty history, the window calculation indexed
a missing column and stopped the main bot.

The right improvement here was to repair the data and execution paths. Lowering
entry thresholds cannot make a stale broker quote executable.

## Implemented changes

- Empty, missing, malformed and non-finite tick inputs produce an unavailable
  report, not an exception or fabricated direction. Fresh report timestamps do
  not override stale underlying ticks. Per-horizon data usability survives the
  consensus adapter.
- The main bot keeps a bounded incremental tick-history buffer. Initial history
  covers 920 seconds; subsequent requests start one second before the previous
  latest tick, deduplicate the overlap and discard expired/future observations.
  A provider failure remains visible even when old cached observations exist.
  The buffer retries and can recover when the provider resumes.
- Quote-only protective exits run before candle, macro and learned entry
  analysis. Sustained opposing flow and eligible profit protection can therefore
  trigger before those calculations complete. Position limits and execution
  safeguards still apply, and failed close attempts are not completed trades.
- The loop target is now one second. Entry persistence thresholds remain
  unchanged. This is a latency improvement, not evidence of better prediction.
- Exceptions in the candle, tick, cross-market, economic and learned advisors
  are isolated and exposed as unavailable inputs. A snapshot failure pauses
  entries and retries rather than pretending old data is current. Broker-side
  stops remain essential: software cannot promise an executable exit without
  usable broker quotes or connection.
- Main-bot candle freshness is checked against current wall time using the
  configured broker offset. A frozen snapshot can no longer keep old M1 bars
  apparently current. Advisor 1 and its snapshot behavior were not changed.
- Console and dashboard now distinguish stale quotes, disconnected terminal,
  absent tick history, advisor failures and entry-timing blocks. They display
  broker tick age, loop processing time and history-fetch time.
- Paper execution rechecks quote expiry at entry, close and shutdown. An expired
  simulated quote cannot be used to manufacture a fill. If shutdown has no
  fresh sample, an unresolved simulated position remains in the saved account;
  it is not reported as closed at an unavailable price.

## Live diagnosis and validation

The read-only diagnostic at 20:48 UTC found the terminal connected but the
XAUUSD quote about 2,902 seconds old under the configured UTC+3 broker clock.
All three bounded history queries returned no usable recent ticks. This does
not establish the cause: a symbol trading pause, stopped feed or broker-clock
configuration needs investigation in MT5. The program must not invent a new
offset merely to make old data appear fresh.

Two bounded paper-mode smoke runs completed without a traceback:

| Run | Cycles | Last measured loop processing | Broker orders |
|---|---:|---:|---:|
| `20260915T205018-6201e493` | 11 | 125 ms | 0 |
| `20260915T205332-5b3a610c` | 16 | 109 ms | 0 |

Both correctly remained flat with a $100 simulated balance because the feed
was stale. These timings were observed during a quiet/stale-feed run and do not
establish active-market latency, execution quality or profitability.

The suite passes 221 tests. New coverage exercises the actual empty-history
crash, malformed ticks, stale reports, source-usability propagation, frozen
candle timestamps, incremental overlap, cache failure/recovery, quote-only
profit protection and paper quote expiry. Dashboard JavaScript also rendered
the new data-health and error fields successfully with mocked status data.
The SHA256 hashes of both protected Advisor 1 source files are unchanged.

The diagnostic evidence is saved at
`data/research/feed_reliability/diagnostic.json`. Smoke account records are in
their respective `data/research/gold_paper/` run folders. The earlier failed
forecast experiment remains documented in `docs/CONTINUOUS_SCALP_REVIEW.md`;
no learned model was promoted during this update.

## Commands

Read-only feed diagnosis:

```powershell
python -B .\tools\diagnose_gold_feed.py
```

Regression tests:

```powershell
python -B .\tools\validate_gold_changes.py
```

Run the updated candidate on live MT5 data with simulated positions:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
python .\run_gold_ai.py --learned-policy observe --cross-market-policy observe --max-minutes 60
```

No test process was left running. If another bot is already running when using
this command, stop it normally before starting another instance. Broker demo
execution remains available through the existing explicit demo-mode command;
this update does not enable real-account execution or alter the three-position,
0.01-lot constraints.

## Primary references

MT5 documents that tick-history requests can return `None` on failure and exposes
`last_error()` for diagnosis: [copy_ticks_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py).
Terminal connection state is separately exposed through
[terminal_info](https://www.mql5.com/en/docs/python_metatrader5/mt5terminalinfo_py).
The project retains its explicitly configured broker timestamp convention;
these references do not establish that every broker requires its UTC+3 setting.
