# Live demo observation — October 8, 2026

Requested monitoring: at least two hours. All timestamps below are UTC; Lagos
is UTC+1. Recorder began 04:02:08, following initial inspection at 04:01.
Baseline account equity is approximately $23,619. Historical strategy loss
before monitoring must not be presented as loss incurred during monitoring.

## Changes and activation times

- 04:04:24: quote-reversal protection accepts the same bounded five-second
  clock skew as the rest of the main bot. Exit conviction no longer saturates
  to full support merely because evidence exceeds the 15-point entry floor.
- 04:11:37: SCALP spread ceiling aligned with the existing $0.50 global ceiling.
  Recorded first 19 samples were $0.44–$0.61; all exceeded the old $0.35 ceiling.
  Relative spread/target cost and entry-zone checks remain active.
- 04:12:34: account-bound recovery preserves post-exit cooldown and M5
  candle-confirmation state. Old snapshots receive conservative restart warmup.
- 04:16:04: SCALP/INTRADAY entries require latest completed M1 candle direction
  agreement; explicitly opposing fresh micro-flow delays entry. Forming candles
  do not confirm. The entries at 04:12 preceded this change.
- 04:23:56: same-direction INTRADAY entry cannot bypass a pending leading SCALP
  two-M5-candle confirmation wait. Opposite direction remains independently eligible.

Restart procedure verifies connected demo account and broker SLs, replaces
only the main bot process, and restores account-bound exit state. Existing
positions remain open with broker protection. Advisor 1 is unchanged.

## Observations

- Position 58813342001 existed before monitoring; closed 04:11 at +$3.09 net.
- SCALP 58813636984 and INTRADAY 58813640577 bought near 04:12. Latest completed
  M1 candle was bearish despite SCALP evidence near 99. Both stopped near 04:20;
  combined strategy realized P/L moved from -$11.17 to -$21.28 (loss $10.11).
- INTRADAY 58813744249 reopened 04:22 before shared SCALP-wait activation.

## External context

- Investing.com XAU/USD showed approximately 4137.42, with an independently
  stamped but delayed web quote. Used as context, never an execution quote:
  https://www.investing.com/currencies/xau-usd
- Official Fed calendar records September meeting minutes released October 7:
  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- DOL PDF retrieved during monitoring was dated October 1, not a fresh October 8
  release; must not be treated as newly published news:
  https://www.dol.gov/ui/data.pdf

No win-rate or profitability claim is established by this small observation set.
Raw observations and summary.json are the evidence for the eventual report.

## Later monitoring changes and observations

- 04:37:13 UTC: pending SCALP candle confirmation continues to block a same-thesis
  INTRADAY entry if SCALP temporarily becomes neutral; an ordinary neutral signal
  without a pending wait does not impose this block.
- 04:52:48: reuse one MT5 deal-history snapshot across lane reconciliation.
- 05:11:17: main-only closed-candle signal cache, with current quotes and levels
  rebuilt each loop. Standalone Advisor 1 remains unchanged. Live parity checks
  passed. Initial 11 cached samples: median 125ms versus preceding 275 samples
  median 406ms; these small, different-time samples are not a controlled benchmark.
- 05:14:32: main loop interval changed from 1.0 to 0.5 seconds; time-based entry
  persistence and cooldown remain unchanged.
- 05:21:06: confirmed loss-of-thesis exit for a losing position when at least two
  usable contributors become neutral and completed-candle momentum opposes it.
  Existing per-lane confirmation timers and the broker $5 stop remain active.
- 05:21:40: INTRADAY 58813744249 closed at -$4.64 under that neutral-thesis rule.
  Main realized monitoring change then -$11.66 (one win, three losses).
- 05:25:09: SCALP 58814349549 opened SELL at 4129.51, 0.01 lot, broker SL 4134.50.
  This is the first new entry following the full set of later entry/exit changes.

Validation after the last live change: 143 relevant unit tests passed. No
profitability conclusion follows from those software tests or one new position.
- 05:31:01: SCALP 58814349549 closed at +$3.28 net on opposing-flow risk.
- 05:39:33: SCALP 58814540299 opened SELL; initially adverse, then recovered.
- 05:47:51: that position closed at +$3.40 net on opposing-flow risk.
- 05:51:30: SCALP 58814702449 opened SELL; closed 05:55:30 at +$3.48 net.
- 05:56:18: SCALP 58814803141 opened SELL, 0.01 lot, broker SL 4121.21.
  Open and losing at the 05:58 checkpoint. Do not omit it from performance.
- At 05:58, latest three completed post-update entries earned $10.16 combined;
  entire monitoring period remained -$1.50 realized with an additional open loss.
