# Main-bot MT5 connection recovery

20 October 2026, Africa/Lagos.

The main worker was already running, not failing to launch. Its snapshot loop
repeatedly reported no live XAUUSD price. A separate initialized MT5 connection
read a current quote and confirmed a connected hedging demo account. This is
consistent with a stale process-local IPC connection; the initiating cause was
not established.

Added main-only recovery on snapshot failure: at most one attempt per 15 seconds,
2-second initialization timeout, original demo login/server/mode pinned, no
credential changes, no rearming and no orders from the recovery helper. A fresh
snapshot and the existing trading guards are still required. Candle caches are
cleared after reconnection. Advisor 1 source is not modified.

Targeted verification: 71 tests and 5 subtests passed, including reconnection,
throttling, failed initialization and account-change rejection.

Controlled restart preflight found zero managed open positions. New launcher
15956 and child worker 29528 form one main instance. Startup stderr was empty.
At 00:10:42 Lagos the status was RUNNING / Fresh executable quote; dashboard
HTTP 200 at http://127.0.0.1:8765. The SMC layer loaded in observe mode and reported
unavailable candle continuity/history, not a trading permission.

Startup log: logs/monitored-main-20261019T231009Z.stdout.log.
No profitability or uninterrupted future connectivity is implied.
