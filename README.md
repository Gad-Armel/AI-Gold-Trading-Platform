# XAUUSD Market Intelligence and Risk Platform

This project provides a research and demo-oriented market-intelligence workspace
for XAUUSD analysis. It combines market data, economic-calendar context, replay,
consistency checks, risk controls, and an optional MetaTrader 5 demo execution layer.

The purpose is to help users study market conditions and validate decision workflows,
not to guarantee trading performance or provide financial advice.

## Real-world problems addressed

- Consolidate price, event, and macroeconomic context for XAUUSD review.
- Compare analytical signals and identify conflicting market conditions.
- Enforce demo-account and risk controls before an execution workflow runs.
- Capture replay and audit information for repeatable analysis.
- Separate research, advisory, dashboard, and execution responsibilities.

## Components

- Python market-analysis and decision engines.
- Unified local dashboard for positions, risk state, source health, and reports.
- MQL5 native expert advisor with demo-account safeguards.
- Replay, validation, and automated test suites.
- Local launch tools for dashboard-only and demo workflows.

## Run in demo mode

On Windows, launch:

```text
Start Gold Demo.cmd
```

Or use PowerShell from the repository root:

```powershell
python -B tools\launch_gold_demo.py --background --yes-demo-risk
```

The launcher verifies that MT5 is connected to a demo account, checks the
fixed 0.01-lot/three-position/XAUUSD-only limits, and waits for a fresh AIGold
heartbeat. After it reports `RUNNING`, the PowerShell window and VS Code may be
closed; the local engine continues in the background.

The dashboard alone can be started with:

```powershell
python -B run_gold_unified_dashboard.py
```

The default dashboard address is `http://127.0.0.1:8777/`.

## Safety boundaries

- Live trading is not enabled by the demo launcher.
- Detached execution requires the explicit `--yes-demo-risk` launch flag and
  a connected MT5 demo account.
- Broker sessions and symbol behavior vary by account and server.
- Backtests, replay, and demo results do not predict future performance.
- Review and test the system independently before any real-account use.
