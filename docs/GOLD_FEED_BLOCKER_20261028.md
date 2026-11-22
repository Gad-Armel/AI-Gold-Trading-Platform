# Current no-trade cause — 28 October 2026

The aggressive main demo worker is running. Freshness and continuous fast-candle
coverage are the immediate blockers, not an idle executor or the prior invalid
one-bar/fast-frame configuration (that configuration bug was already fixed).

## Observed evidence

- Terminal connected, automated trading permitted, symbol full trading mode.
  Reported broker ping was approximately 112 ms.
- A fresh HTTPS Date comparison put the local PC roughly 1.1 seconds ahead of
  that server response, not enough to explain 15–60-second quote freezes. This
  comparison is diagnostic, not an authoritative NTP measurement.
- In a 15-second sample, XAUUSD bid/ask and time_msc were unchanged for the
  first 13 observations; tick age increased from 15.65 to 27.65 seconds before
  a fresh quote arrived.
- Three-minute tick-history request returned only 15 ticks. Inter-tick gaps:
  median 0.6435 seconds, p95 28.87175 seconds, p99 29.41515 seconds. A short burst
  is not equivalent to continuous tick coverage.
- Re-selecting XAUUSD in Market Watch succeeded, but the subsequent 20-second
  sample still included a frozen quote aging from 44.53 to 59.55 seconds.
- A same-account demo reconnect using MT5's saved credentials succeeded while
  the terminal was fully flat with no pending orders. The following 20-second
  sample remained unchanged, with quote age rising from 9.99 to 29.01 seconds.

## Actions and limits

No password was requested, exposed or changed. No order was sent by the
diagnostic tools. No account switch, terminal restart, risk increase, freshness
relaxation or synthetic tick interpolation was performed. The temporary entry
hold used during reconnect was removed afterward. Advisor1 code was untouched.

This demonstrates stalled/sparse quote delivery to this terminal/API, but does
not by itself distinguish the broker service, network path and terminal state.
It does not prove that the entire gold market is inactive. If the visible MT5
Market Watch updates continuously while the API does not, compare terminal
instances/account bindings next. If both freeze, restore a continuous demo
feed with the broker/terminal before expecting S5/S15 execution. Merely raising
the stale-quote limit cannot make that feed suitable for high-frequency scalping.
