# Twenty-minute demo observation — 26 October 2026

## Actual window

06:36:43–06:56:43 Africa/Lagos (05:36:43–05:56:43 UTC), 20 minutes.
240 successful five-second status observations; one transient Windows permission
error reading the atomically replaced main status file. Main/inverse demo
identity remained consistent. No trading parameters were changed during the
window and no orders were submitted by the monitoring/audit tools.

## Broker-confirmed activity

One 0.01-lot main BUY, position 59041249548, and its opposite 0.01-lot inverse,
position 59041249613, both opened and closed during the observation:

| Executor | Booked net USD |
| --- | ---: |
| Main | -2.91 |
| Inverse | +2.05 |
| Combined | -0.86 |

No owned positions remained at the end of the window. Broker history, not
five-second snapshots, is authoritative for fills: the entry-ready interval
fell between status samples, so zero sampled ready states does not mean zero
orders. Initial main/inverse broker snapshots were flat.

## Why most cycles did not trade

- Six-second follow-through rejection: 237/240 samples.
- Recent S30 range did not clear the configured cost screen: 227/240.
- Bid and ask did not both progress in signal direction: 223/240.
- Directional decisions: WAIT 207, BUY 23, SELL 10.

These counts overlap and are not independent opportunities or trade results.
The observed BUY passed S30 entry checks, with a protected $4.84 planned stop
at entry, but subsequently lost. Its slow context was range/transition; this
is a hypothesis for further trend-versus-range analysis, not enough evidence
to promote a new range rule or guarantee a better entry after one loss.

## Prospective-price audit

Exported 6,893 broker ticks for the observed window, retaining all 6,893 valid
quotes. Evaluated the 33 sampled directional observations against subsequent
executable bid/ask prices, using 250 ms latency per leg and provisional
round-trip commission/slippage price equivalents of 0.10/0.20.

| Holding horizon | Midpoint direction correct | Positive executable net markout | Mean net price equivalent |
| --- | ---: | ---: | ---: |
| 5 seconds | 13/33 | 2/33 | -0.68030 |
| 15 seconds | 21/33 | 4/33 | -0.52939 |
| 30 seconds | 19/33 | 10/33 | -0.45152 |

These are overlapping observational labels, mostly for signals rejected by
the entry gates. They are NOT a strategy backtest, calibrated accuracy, live
trade win rate, or a replay of the adaptive exits. The assumptions are not
measured fill guarantees. Twenty minutes and one completed pair cannot validate
long-term expectancy, calibrate an AI, or justify selecting a new parameter set.

## Fix and validation

Added a bounded retry for transient PermissionError while reading main/inverse
dashboard JSON: at most three reads, 10/20 ms waits, no stale-cache substitution,
and a persistent failure remains an error. This fixes an observed reporting
problem, not the predictive strategy. Protective exits and risk limits remain
unchanged. 186 targeted tests pass, including this retry and the observational
markout audit. No filter was loosened to force frequency.

## Artifacts / reproduction

- `data/research/gold_live_20min_20261026T0536/report.json`
- `data/research/gold_live_20min_20261026T0536/samples.jsonl`
- `data/research/gold_live_20min_20261026T0536/observed_ticks.csv`
- `data/research/gold_live_20min_20261026T0536/signal_audit.json`

For another bounded observation, use a new output directory:

```powershell
.\.venv-audit\Scripts\python.exe -B tools/monitor_gold_demo.py --minutes 20 --interval 5 --output data/research/gold_live_NEW_WINDOW
.\.venv-audit\Scripts\python.exe -B tools/audit_gold_live_observation.py data/research/gold_live_NEW_WINDOW
```

The tooling is read-only and terminates after the requested duration; this is
not unattended strategy modification or a promise of persistent supervision.
