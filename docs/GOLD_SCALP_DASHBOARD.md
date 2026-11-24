# Unified Gold Demo Desk

The only supported browser dashboard is the local Gold Demo Desk:

```powershell
python -B run_gold_unified_dashboard.py
```

It is served only on `http://127.0.0.1:8777/`. The desktop shortcut
**Aurum Gold Demo Desk** starts the dashboard and MT5 preflight; it then checks
for a DEMO account and asks for the locally configured confirmation before
starting the Python demo bot.

## Combined views

- **Overview:** native EA session/close-out status, current health, combined
  engine summaries, and snapshot freshness.
- **Native:** MT5 XAUUSD chart, account/equity, open and closed positions,
  native decisions, and EA safety controls.
- **Consensus:** SCALP/INTRADAY/SWING entry gates, blockers, adaptive exits,
  position state, tick-flow context, source freshness, news/risk context, and
  measured tick-fetch, cycle, cache, and phase timings.
- **Advisor, Manual, V-FINAL:** existing reports, with their own freshness and
  execution limitations visible.
- **System:** active engine states, report-bridge health, and execution policy.

This dashboard presents existing engine decisions and telemetry; it does not
calculate a new trading signal. Broker tick and loop timings are diagnostic
measurements, not proof of high-frequency trading infrastructure, colocated
execution, or a latency guarantee. Offline HFT/replay research remains research
and does not authorize broker orders.

## Execution and safety

Live mode remains locked. The desktop launcher refuses non-DEMO MT5 accounts,
requires a hidden confirmation phrase on each bot launch, and starts the Python
bot only after confirmation. The native EA remains a separate executor and
must be attached to its XAUUSD chart manually; do not enable both executors
without an explicit test plan.

Snapshots or reports that are stopped, stale, disconnected, or unavailable are
identified as such. Old dashboard runners and the disconnected Expo sample
cockpit have been retired. The feed readers and command mailbox remain as
backend services used by the unified desk.

For broker session details and the five-minute pre-close attempt, see
[GOLD_SCALP_NATIVE_FR.md](./GOLD_SCALP_NATIVE_FR.md).
