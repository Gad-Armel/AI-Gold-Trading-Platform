# User constraints

- October 15, 2026 review supersedes earlier three-position references: maximum
  five simultaneous SCALP positions, fixed 0.01 lot. Fourth/fifth positions need
  stronger current evidence and all existing addition/risk protections. Advisor 1
  remains protected. See `docs/XAUUSD_SCALPER_SPEC_FR.md` for the adapted proposal,
  actual risk profiles, research requirements and remaining validation gaps.

- October 8 monitored runtime: main loop interval 0.5 seconds with completed-
  candle analysis caching in the main only; current prices/levels still refresh.
  Confirmed neutral-thesis exits require two usable neutral sources, opposing
  momentum and loss beyond spread/ATR noise. Keep broker stops and per-lane
  confirmation timers. Missing sources are not neutral votes.

- October 8 live-monitoring authorization: user permits main-bot fixes and
  restarts during monitoring. All lane entries require fresh completed
  M1 candle agreement and wait for explicitly opposing available micro-flow.
  A pending leading SCALP two-M5 wait also delays same-direction INTRADAY/SWING
  entries (both directions while that pending signal is neutral).
  SCALP spread ceiling now matches the existing global $0.50 maximum, with
  relative target-cost checks retained. Preserve cooldown/candle waits across
  restarts. Advisor 1, fixed .01 lots, three-slot cap and $5 individual stops
  remain unchanged. Observe measured results; do not claim proven profitability.

- Main SCALP entry authority is now Advisor 1's existing M1/M5/M15 candle
  signal, exposed as MT5_CANDLES in consensus. Preserve its bias, evidence and
  analysis levels; optional API/tick-flow disagreement does not replace it.
  Unusable or stale Advisor 1 signals block SCALP. Tick flow remains exit context.
  Advisor 1 implementation remains unchanged. The actual broker stop remains
  the separately configured $5 individual money stop.

- October 8, 2026 update supersedes the main consensus bot's earlier money-stop
  defaults: each position has a planned $5 individual broker stop. Session
  loss does not terminate the main bot. After a detected closure, all new
  entries pause for 30 seconds while analysis and protective exits continue.
  Explicit emergency stop and user shutdown remain available. Fixed 0.01 lots
  and three total positions remain. SCALP loss cooldown is also 30 seconds;
  two-M5-candle confirmation may delay a qualifying next entry longer.

- October 6, 2026 follow-up: after strong lane evidence weakens (100 to about
  76 is the example), confirm the next move using two completed M5 candles.
  Implementation defaults: prior strength >=85, drop >=10 points to <=80,
  or a direction change after strength >=85. Applies to new entries per lane;
  protective exits continue. Only consecutive post-trigger candles count.

- October 6, 2026: main demo bot uses continuous independent directional
  entries with a 15/100 evidence floor. Below 15 is very weak; when all three
  lanes are very weak, pause new entries. SCALP may lead slower candle signals.
  Valid data, trade levels, news protection and execution risk limits still apply.
  Advisor 1 remains unchanged.

- Preserve Advisor 1: do not delete or modify its entry point, implementation,
  or behavior. This includes `run_gold_advisor.py` and
  `services/research/gold_advisory.py`; shared changes must preserve its behavior.
- The main trading bot may hold at most **three positions total**, across all
  horizons combined. Each new position must be exactly **0.01 lot**. No automatic
  size increases as the balance grows.
- The intended starting capital is **USD 100**. This is a strategy budget,
  not a claim that software has funded or reset the broker account.
- Initial engineering risk defaults: $2 planned stop exposure per trade and
  a $50 rolling 24-hour realized-plus-floating loss circuit breaker for the native
  scalper (user update, October 2, 2026). Execution
  costs, gaps and slippage can exceed these nominal thresholds.
- October 2, 2026 user update: native daily equity pause disabled. Keep the
  $50 rolling loss limit with a persistent stop until explicit dashboard reset.
  Reset starts a new loss session on a flat, reconciled account, preserving broker
  history and daily results. Three consecutive losses pause entries for one minute. Emergency Close All cancels pending orders and closes every position on
  the demo account, including manual/other-strategy positions. Entry pause keeps
  protective exits active. Advisor 1 remains unchanged and is read via snapshots.
- The user authorizes creating, editing and deleting files within this project
  except Advisor 1. This permission does not require deleting unrelated files.
- Review forthcoming Claude, Gemini and DeepSeek proposals critically. Apply
  useful changes after checking the implementation and evidence; do not accept
  performance claims or model promotion without validation.
