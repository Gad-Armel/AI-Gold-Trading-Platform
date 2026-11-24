# Aurum Quant AI — current architecture

## Supported desktop

The supported browser interface is the local **Gold Demo Desk** at
`http://127.0.0.1:8777/`, served by `run_gold_unified_dashboard.py`. It combines
existing native EA, Python consensus, Advisor 1, manual-advisor, and V-FINAL
status/report sources. It displays the freshness and availability reported by
those sources; it does not invent a live feed when a source is absent or stale.

The unified page is a local monitor and control surface, not a new trading
engine. It reports available MT5 tick and processing-loop timings as
diagnostics, not as evidence of exchange colocation, HFT capability, or
guaranteed performance. The retired Expo sample UI showed demo data and was not
connected to the broker; it is no longer part of the application.

## Runtime and execution boundaries

- **Python consensus bot:** the default is paper/shadow. The supported one-click
  launcher starts the XAUUSD demo bot only after the terminal is connected to a
  DEMO account and the locally configured confirmation phrase is entered.
- **Native GoldScalpAI EA:** remains a distinct MT5 executor. It observes by
  default and uses the Strategy Tester for simulation. Demo execution requires
  its explicit configuration and MT5 permissions.
- **Advisor 1:** remains protected and unchanged. The unified desk may read its
  reports; it is not a replacement for that advisor.
- **Live trading:** remains disabled. Do not run both the Python and native EA
  executors against the same account exposure.

The desktop shortcut **Aurum Gold Demo Desk** targets `Start Gold Demo.cmd`.
That launcher opens the unified dashboard, initializes or connects MT5, checks
the account mode, and prompts before starting the Python demo bot. Use
`tools/open_gold_unified_dashboard.ps1` or `python -B
run_gold_unified_dashboard.py` when only the dashboard is wanted.

## Data flow

The unified server reads local MT5 Common/Files EA snapshots and existing
runtime reports. Its source/provider helpers remain in `services/dashboard/`
because the desk and read-only monitoring tools use them. Legacy browser
dashboard launchers and the disconnected Expo frontend are retired.

## Validation boundary

Dashboard/API tests verify rendering, feed classification, and safe local
configuration writes; they do not prove a live market feed, profitable
strategy, successful broker order, or market-open readiness. Use only a demo
account for execution testing. Current account risk limits and native EA
behavior remain documented in [GOLD_SCALP_NATIVE_FR.md](./GOLD_SCALP_NATIVE_FR.md).
