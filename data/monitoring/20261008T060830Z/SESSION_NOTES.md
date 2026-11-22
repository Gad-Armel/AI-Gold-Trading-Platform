# Extended main demo monitoring

User authorized another 5–10 hours of observation. Recorder started
2026-10-08 06:08:30 UTC (07:08:30 Lagos) for 305 minutes, 15-second samples.
Main baseline realized P/L is -$21.65. The previous open position closed at
06:08:17 for -$0.90, before this recorder started. Early commentary included
that exit in its continuation baseline (-$20.75); corrected explicitly at
07:08 UTC. Summary uses the actual recording baseline, not that earlier value.

At 59.38 minutes: two gains ($2.19, $0.56), one loss ($3.78), realized -$1.03,
maximum sampled account equity drawdown $5.26, loop median 156ms/p95 390ms,
no advisor-error samples. Last loss exited on confirmed neutral thesis.

At 07:39 UTC, live read-only cache parity passed for direction, score, levels
and votes across all lanes. MT5 quotes and candles were advancing; prolonged
WAIT was not a frozen cache. A reusable read-only tool was added at
tools/check_live_candle_cache.py. No strategy changes made in this window yet.

[Investing.com technicals](https://www.investing.com/currencies/xau-usd-technical)
at 07:30 GMT showed hourly neutral and mixed other timeframes. Context only;
web analysis does not replace the executable broker quote or scalp signal.

At 07:54 UTC: three 0.01-lot SELL positions open, all with broker stops:
SCALP 58816200127 (SL4124.99), INTRADAY 58816257294 (SL4123.46),
SWING 58816260761 (SL4124.14). Both candle contributors retained SELL bias;
all three positions were losing. Combined loss can exceed $5 because the
requested stop is per position, not a session-wide stop.

At 08:04–08:05, all three original SELLs stopped for $14.97 combined. SWING
reopened SELL at 08:04:46 while INTRADAY correctly waited on opposing M1 timing.
Recorded completed M1 candles were rising: 4119.10→4121.03,
4121.02→4121.92, 4121.93→4123.54. The SWING score was 72.53.

08:06:55 UTC restart activated all-lane M1 entry timing and extended the pending
leading-SCALP confirmation check to SWING. Longer-frame directional scores and
Advisor 1 remain unchanged. Existing position retained its broker stop. The
recorded SWING regression plus relevant checks passed (71 tests). This fix does
not retroactively prevent earlier losses or establish profitability.

At 148.98 minutes: 4 wins, 7 losses, realized -$22.55, account equity change
-$21.36, sampled maximum drawdown $29.20. Every lane negative: SCALP -$5.54,
INTRADAY -$7.82, SWING -$9.19. SWING analysis stops were often $13–15 price
units away while the configured broker stop represented about $5. This is a
timeframe/risk mismatch to investigate; it does not authorize increasing stops.

At 240.59 minutes: 7 wins, 13 losses, realized -$35.54, gross gains $9.78,
gross losses $45.32, profit factor 0.216, sampled maximum drawdown $39.77.
Median/p95 processing 156/360ms. No advisor errors recorded, stderr empty.
Lane realized: SCALP -$8.79, INTRADAY -$12.81, SWING -$13.94. Bot flat and
running after the last INTRADAY broker stop. Faster operation and continuous
re-entry have not produced profitable results. No further speculative strategy
changes were made after 08:06:55; all losses retained.

At 269.62 minutes: 15 wins, 13 losses, realized -$17.88, gross gains $27.44,
gross losses $45.32; profit factor 0.605. More winning trades still did not mean
more money gained than lost. One SWING SELL remained open near +$5.57. The main
SCALP two-M5 confirmation wait was active (zero new completed qualifying bars).
Recorded maximum account equity drawdown was $43.19. Loop median/p95 156/359ms;
no advisor-error samples. Full relevant regression suite passed 145 tests after
the SWING timing change. Late gains are not proof that the code change caused
an improvement; market conditions also changed.
