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
   and requires the locally configured confirmation phrase before starting
   the Python bot. Leave the console open while the bot runs.

To open the dashboard without starting the bot, run
`python -B run_gold_unified_dashboard.py` or
`tools/open_gold_unified_dashboard.ps1`.

Live execution is locked. The native MT5 EA is a separate executor and must be
attached manually; do not enable it alongside the Python executor without a
specific demo test plan. Never place passwords, broker credentials, or
confirmation phrases in source code or Git.

## What the desk displays

The local page at `http://127.0.0.1:8777/` combines native EA snapshots,
consensus-bot state, Advisor 1 reports, manual analysis, and V-FINAL reports.
Unavailable or stale sources remain visibly unavailable/stale. Its latency
panels show observed retail-terminal timings, not guaranteed HFT performance.
