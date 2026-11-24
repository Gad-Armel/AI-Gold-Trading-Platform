# CLAUDE.md — XAUUSD AI Trading Platform

## What this project is
A XAUUSD research project with a protected Gold Advisor 1, a Python consensus
bot (`run_gold_ai.py` / `run_gold_consensus_bot.py`), V-FINAL research tools,
and the new native EA `mql5/Experts/GoldScalpAI/GoldScalpAI.mq5`.
The retired V6 execution engines are not current entry points. Their five
archived source ZIPs were deleted after explicit user confirmation; the audit
is in `data/research/project_cleanup/deleted_v6_archives.json`.

Current native EA architecture, research, limits and validation are documented
in `docs/GOLD_SCALP_NATIVE_FR.md`. Earlier WIP documents are historical context.

## Non-negotiable rule
**Never modify `run_gold_advisor.py` (Gold Advisor v1) or its transitive local
dependencies.** The 18 protected paths and baseline hashes are recorded in
`data/research/project_cleanup/inventory_before.json`. If an improvement is relevant
to it, build it as a new/parallel file (a new advisor version or variant)
instead of editing v1 in place.

## Working method — apply to every file you touch
1. Before changing a file, check how it is actually used elsewhere (imports,
   call sites, tests). Don't treat it as a standalone script.
2. Verify uncertain technical claims — library/API behavior, MT5 specifics,
   statistics/ML practices, data-source documentation — with research rather
   than relying purely on memory.
3. Reason independently about whether the existing logic is the most reliable
   way to handle that step. Don't just patch the reported symptom: look for a
   genuinely better approach (more robust to edge cases, less prone to
   look-ahead bias/overfitting/leakage, clearer safety gating) and explain why
   the change is actually better, not just different.
4. When you edit a file, keep the change complete and consistent: update every
   call site, related test, and doc that the change touches.
5. Preserve existing test coverage. When behavior changes, update or add
   tests rather than deleting coverage.

## Codebase quirks to watch for
- Two parallel "eras" of code seem to coexist: an older, simpler layer
  (`config.settings`, `models.market_state` — e.g. `structure_detector.py`,
  `trend_detector.py`, `volatility_detector.py`, `trend_confirmation.py`,
  `structure_confirmation.py`, `daily_review_report.py`) and a newer V6.x/
  V6.3.x layer (`config.scalping_settings`, `models.scalping_state`). Don't
  assume one silently replaces the other — confirm which is actually wired
  into the live entry points before changing either.
- Several advisors coexist (Gold Advisor v1/v2/v3, V-FINAL). Don't merge,
  delete, or silently deprecate one without flagging it explicitly first.

## Safety posture — preserve unless explicitly told otherwise
- Python defaults to paper/shadow mode. The native EA observes by default on
  charts and simulates orders in the Strategy Tester. Demo orders require the
  explicit relevant runner option. Experimental learning does not prove edge.
- Real-account execution stays disabled. The user's latest limits are at most
  **3 positions on the account and exactly 0.01 lot per new position**.
- No synthetic market data is ever generated for training or for testing
  "real" performance.
- Historical macro features must use point-in-time/vintage data (e.g. FRED
  `realtime_start`/`realtime_end`), never current revised values — this
  avoids look-ahead bias.

## Handy commands already in the repo
- `python -B tools/validate_gold_changes.py` — Python regression suite.
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools/compile_gold_scalp.ps1` — native compilation.
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_gold_scalp.ps1` — native deterministic self-tests.
- `python -B tools/audit_python_reachability.py` — import audit, not a deletion list.
- Keep useful tests and empirical research evidence. Do not claim a backtest
  passed merely because a terminal launched or a program compiled.
