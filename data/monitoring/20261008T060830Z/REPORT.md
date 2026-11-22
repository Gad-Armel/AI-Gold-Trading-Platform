# Extended live demo monitoring — October 8, 2026

Monitored another **5 hours 5 minutes**, from **06:08:30 to 11:13:39 UTC**
(**07:08:30 to 12:13:39 Lagos**), with **1,216 recorded observations**.
Evidence: [summary](summary.json), [performance chart](performance.png),
`observations.jsonl`, and [session notes](SESSION_NOTES.md).

**The full recorded window remained unprofitable.** There were **16 winning
and 13 losing closed positions**, but the monetary result was **-$13.60 realized**.
Gross gains were $31.72 and gross losses $45.32, giving a profit factor of 0.700.
Average winning trade was approximately $1.98; average losing trade $3.49.
More winning trades did not mean more money gained than lost.

At the recording cutoff, three open positions had **-$8.40 floating**, making
the main strategy's realized-plus-floating change **-$22.00**. Direct MT5 account
equity changed -$22.21; account and status snapshots are captured separately.
Maximum sampled account equity drawdown was **$43.19**.

| Lane | Closed positions | Realized net |
| --- | ---: | ---: |
| SCALP | 14 | -$0.63 |
| INTRADAY | 6 | -$6.48 |
| SWING | 9 | -$6.49 |

The late recovery narrowed an earlier -$35.54 realized result. It does not
establish that the code change caused better performance: market conditions
changed and there was no controlled strategy comparison.

## What was found and changed

At 08:04–08:05 UTC, three correlated SELL positions stopped for a combined
$14.97 loss. SWING then reopened SELL at 08:04:46 despite three rising completed
M1 candles. INTRADAY correctly waited on its M1 check, but SWING bypassed it.

At **08:06:55 UTC**, a validated main-bot restart activated the existing M1
entry-timing check for **all three lanes** and extended the leading SCALP
two-M5-confirmation wait to **SWING**. A recorded-case regression checks that
the opposing M1 rally blocks that SELL until a completed candle agrees.
Longer-timeframe directional analysis was retained; **Advisor 1 was unchanged**.
The restart preserved the existing broker-protected position.

Later, SCALP's two-M5 wait was observed live after weakening. SWING respected
that pending wait. New entries resumed around 11:10 UTC when confirmation
released. This verifies operation of the wait, not profitability.

No further speculative strategy changes were made after that restart. The
configuration comment about processing cadence was clarified without changing
its value. A reusable read-only audit tool, `tools/check_live_candle_cache.py`,
was added; live direction, score, level and vote parity passed in every lane.
Candles, cache refreshes and quotes were advancing during prolonged WAIT periods.

## Remaining causes and limits

- Larger losses outweighed frequent small gains. Strong heuristic evidence
  scores were not calibrated probabilities of a successful trade.
- Three lanes sometimes held the same direction, accumulating correlated loss.
- SWING's structural analysis stop was often $13–15 price units away while its
  configured money stop represented approximately $5. This observed timeframe
  and risk mismatch needs separate validation; stops were not widened.
- Entry timing fixes did not eliminate false directional signals. Every lane
  finished with a negative realized result.

The user-requested 0.01 lots, three-position cap, individual $5 stop policy,
30-second post-exit analysis pause and continuous operation were retained.
Actual fills and slippage can exceed nominal stop exposure. No session-loss
shutdown was introduced and no unvalidated learned model was enabled.

## Health, sources and validation

Recorded processing median/p95 were **156/359 ms**; occasional cycles were
slower. Maximum observed runtime-status lag was 2.19 seconds. No advisor-error
samples were recorded, and the restarted main process's stderr was empty.

**145 relevant regression tests passed**, covering entry momentum, recorded
SWING re-entry, leading-SCALP waits, candle caching/parity, neutral exits, quote
flow, conviction, broker demo execution, continuous operation, cooldown recovery,
broker clocks and candle confirmation. These tests validate software behavior.

[Investing.com technicals](https://www.investing.com/currencies/xau-usd-technical)
showed a neutral hourly summary with mixed other timeframes at its 07:30 GMT
update. It was used as context, not a fresh scalp execution trigger. Earlier
checks of [TradingView technicals](https://www.tradingview.com/symbols/XAUUSD/technicals/)
did not expose complete indicator values. MT5 remained the executable-price source.

## State after monitoring

At **11:14:34 UTC**, the main bot was **RUNNING**, with no reported advisor
errors. Three 0.01-lot SELL positions remained open, floating **-$8.76**:

| Lane | Ticket | Broker SL |
| --- | ---: | ---: |
| SCALP | 58819282931 | 4119.98 |
| INTRADAY | 58819288175 | 4120.05 |
| SWING | 58819281991 | 4120.00 |

Those positions and P/L can change after this snapshot. The bot remains running
as requested. Active interactive monitoring has ended; this report does not
imply unattended model-driven supervision continues after the session.

Baseline clarification: the previous position's -$0.90 exit at 06:08:17 occurred
before this recording. Early continuation commentary included it; the baseline
was corrected explicitly. All figures here use the actual 06:08:30 recording
baseline of -$21.65 main realized P/L. For the preceding observation, see the
[initial report](../20261008T040208Z/REPORT.md).
