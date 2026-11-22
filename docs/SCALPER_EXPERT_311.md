# Scalper Expert 3.11 — continuous analysis during safety pauses

September 30, 2026 diagnosis: both feeds were live, the London session was open,
native news was fresh, and the only reported environment blocker was the existing
account loss lock. It expires at 2026-09-30 22:17:04 MT5 server time, corresponding
to 20:17:04 Africa/Lagos with the currently observed broker offset.

The previous OnTick path returned at the account gate before evaluating the scalp
signal. Quote tracking and position protection continued, but the evidence score
stayed at zero after restart under a lock, obscuring the bot's activity.

3.11 evaluates fresh signal evidence before checking permission to enter. It
exports the signal explanation and quote timestamp separately from execution
status. Signal persistence is still armed only after every environment check;
an opportunity seen during a lock cannot become an order by bypassing that lock.
The browser shows the remaining protection duration and estimated end in its local
timezone. Stale/disconnected feeds explicitly stop presenting a live countdown.

Execution policy remains [3.10](SCALPER_EXPERT_310.md): 0.01 lot, max three positions,
fixed loss limits, continuous broker-hour monitoring except the existing 21–23 UTC
rollover entry restriction. No risk lock was shortened or erased. Policy cohort
comments remain `ScalperExpert310:S0..3` because entry/exit eligibility is unchanged.
Advisor 1 remains intact.

After lock expiry, entry evaluation resumes automatically subject to fresh quotes,
signals, costs, news, exposure and risk checks; this does not guarantee an order.
Do not leave VS Code open merely for operation. MT5 and the dashboard server are
the required running processes. Refresh existing browser tabs with Ctrl+F5.

Restart the main EA after closing MT5 normally:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_scalp_mt5.ps1 -DemoOrders
```

Restart the main and Advisor 1 browser pages in a separate PowerShell:

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\restart_gold_dashboards.ps1
```

Validation is recorded in `mql5/validation/scalper-expert-311-validation.json`.
These checks establish continued analysis and preserved execution gates; they do
not establish profitability or justify taking positions without a qualifying signal.
