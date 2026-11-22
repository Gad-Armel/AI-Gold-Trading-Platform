# SCALP-only main demo mode

Requested October 9, 2026. Main opens SCALP orders only; INTRADAY/SWING
remain analysis lanes and any existing positions retain exit management.
SCALP can hold three simultaneous 0.01-lot positions, subject to the unchanged
three-position account-wide cap. Each entry retains its own planned $5 broker SL.

Additions require the same direction as all existing SCALP positions, each open
position profitable beyond two spreads, current signal evidence at least 75/100,
5-second spacing, and existing freshness, momentum, candle confirmation, cost,
risk and margin checks. No averaging down or opposite-direction SCALP additions.
The initial entry retains the existing signal floor and analysis rules. Session
losses do not stop the main loop; post-exit analysis remains 30 seconds.

Both main-loop and broker execution enforce analysis-only secondary lanes.
Paper simulation supports the same three-SCALP capacity and profitable additions.
Adaptive exits already support same-direction position groups; broker stops remain
per position. Standalone Advisor 1 was not modified.

Validation: 162 relevant tests passed, including a paper sequence holding three
protected SCALP positions and refusing a fourth, loss/hedge addition rejection,
and execution-layer secondary order rejection. Legacy generic broker tests
explicitly enable secondary lanes inside their fixtures to retain coverage of
those generic risk paths; dedicated mode tests verify deployed permissions.
Runtime after deployment showed RUNNING, trading_horizons=[SCALP], total cap 3,
per-horizon cap 3, 0.01 lots, $5 maximum planned trade risk, disabled session-loss
shutdown. No owned positions were present at the first deployment. Historical
multi-lane research does not establish profitability for this new mode.

Higher-timeframe SCALP support added: INTRADAY and SWING remain execution-disabled.
Fresh usable directional views contribute a bounded alignment score. For additions
only, the existing 75-point SCALP requirement is adjusted by at most five points:
70 when both fully support, 80 when both fully oppose, and intermediate values
for weaker/mixed views. Initial SCALP entry authority and primary evidence are
unchanged. Context cannot flip direction, authorize an initial trade, bypass
profitability/spacing/capacity/market guards, or open secondary orders. Invalid,
stale or neutral views contribute zero. This is heuristic context, not calibrated
probability or proven profitability. Entry journals record the context. All 114
relevant tests passed before deployment; standalone Advisor 1 remains untouched.

October 9 reactivity update: initial SCALP signal persistence is 2 seconds.
After a strong signal weakens, SCALP requires one new completed M1 candle in
the candidate direction instead of two M5 candles. Forming, stale and opposing
candles cannot confirm. The absolute quote-spread ceiling is $0.75 in price
units; the spread-to-target cost limit remains 35%. Additions may be evaluated
every 5 seconds, still requiring profitable existing positions and fresh signals.
The 30-second post-exit analysis pause, three-position cap and planned $5 stop
per position remain. These frequency changes have no demonstrated profit edge.

Per-position profit lock: after a SCALP position reaches $6 in executable
price P/L, close that ticket if it gives back 20% of its highest observed profit.
A $6 peak triggers at $4.80; a $10 peak at $8. Peaks survive additions and
ordinary restarts, and each ticket is independent. Existing protective exits
may bank profits earlier. Re-entry follows fresh analysis and the existing
30-second pause; it is not an unconditional replacement order. Trigger prices
do not guarantee realized amounts because of execution latency and costs.
