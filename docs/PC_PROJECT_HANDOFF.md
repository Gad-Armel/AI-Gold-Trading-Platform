# Aurum Quant AI — Windows desktop handoff

This repository contains the XAUUSD research/runtime code and the supported
unified Gold Demo Desk. It is not the former standalone Expo sample or its
sample-data cockpit.

## Launch

1. Install Python dependencies from `requirements.txt` and install MetaTrader 5.
2. Connect MT5 to a DEMO account.
3. Double-click `Start Gold Demo.cmd` or the Desktop shortcut **Aurum Gold Demo
   Desk**.
4. The unified dashboard opens first. The launcher checks the account is DEMO
   and validates the XAUUSD-only, 0.01-lot and three-position hard limits before
   starting the Python bot. It waits for a fresh `RUNNING` heartbeat and then
   exits; the bot continues in the background, so the console and VS Code may
   be closed.

The equivalent PowerShell command from the project root is:

```powershell
python -B tools\launch_gold_demo.py --background --yes-demo-risk
```

To open the dashboard without starting the bot, run
`python -B run_gold_unified_dashboard.py` or
`tools/open_gold_unified_dashboard.ps1`.

Live execution is locked. The native MT5 EA is a separate executor and must be
attached manually; do not enable it alongside the Python executor without a
specific demo test plan. Never place passwords or broker credentials in source
code or Git.

## What the desk displays

The local page at `http://127.0.0.1:8777/` combines native EA snapshots,
consensus-bot state, Advisor 1 reports, manual analysis, and V-FINAL reports.
Unavailable or stale sources remain visibly unavailable/stale. Its latency
panels show observed retail-terminal timings, not guaranteed HFT performance.
