# Aurum Market Risk & Execution Platform

A research-first market intelligence and risk-control platform for XAUUSD (gold). It combines market analysis, validation workflows, a native MetaTrader 5 expert advisor, Python research services, and a local command center designed to make trading decisions more observable, testable, and controlled.

> This is a research and demo-execution system—not a promise of profitability. Live trading remains disabled by design unless explicitly configured and separately validated.

## Real-world problem

Gold-trading workflows often scatter signals, account state, execution permissions, and risk decisions across disconnected scripts and terminal windows. That makes it difficult to answer basic operational questions: why was a signal accepted, which safeguards were active, what data supported the decision, and what happened during execution?

Aurum addresses this by providing a single, auditable workflow for research, signal review, risk gating, demo execution, and post-run validation.

## What the platform provides

- XAUUSD market-state analysis and research reports.
- Python consensus and advisory services for signal investigation.
- Native MQL5 execution components for MetaTrader 5.
- Demo-only safeguards, position limits, permission checks, and paper/shadow modes.
- Local dashboards for account state, positions, signal sources, risk filters, and system timing.
- Replay, deterministic self-tests, regression checks, and validation tooling.
- Clear separation between research, advisory logic, and execution.

## Technology and skills demonstrated

- **Languages:** Python, MQL5, PowerShell, YAML, Markdown.
- **Analytics:** pandas, NumPy, scikit-learn, Joblib, statistical validation, time-series research.
- **Trading integration:** MetaTrader 5, MT5 Expert Advisors, symbol/session metadata, account and position controls.
- **Engineering:** modular architecture, configuration management, safety gates, reproducible validation, logging, auditability, and defensive error handling.
- **Quality practices:** regression suites, deterministic test scripts, replay validation, point-in-time data discipline, and explicit research limitations.

## Run the demo workspace

```powershell
python -B tools\launch_gold_demo.py
```

To open the dashboard without starting the bot:

```powershell
python -B run_gold_unified_dashboard.py
```

Default address: `http://127.0.0.1:8777/`

The native EA can be compiled and validated with the PowerShell scripts in `tools/`. Read the project safety and validation documentation before connecting MetaTrader 5.

## Safety and scope

The default posture is paper/shadow mode. Demo execution requires explicit configuration. Real-account execution is not enabled by default. Historical validation does not establish future performance, and retail MT5 timing is not HFT infrastructure.

## Project structure

- `run_gold_unified_dashboard.py` — local command center.
- `tools/` — launch, validation, audit, compilation, and test utilities.
- `mql5/` — native MetaTrader 5 execution components.
- `docs/` — architecture, research, validation, and operating guidance.
- `data/` — research outputs and local snapshots.

## Responsible use

Use only authorized market data and accounts. Validate broker-specific symbol sessions, permissions, spreads, and execution behavior on a demo account before any operational use.