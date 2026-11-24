# Scalper Expert intelligence integration

GoldScalpAI 3.28 incorporates the parts of `xauusd_ai_market_intelligence_engine` and `mql5/Experts/Exness_XAUUSD_Titan` that are appropriate for a tick-led XAUUSD scalper:

- causal M1/M5/M15/H1 trend confluence;
- breakout-expansion and ranging-regime classification;
- abnormal-volatility detection using current ATR against a 60-bar completed-bar reference;
- a small score adjustment for full multi-timeframe agreement; and
- a hard abnormal-volatility entry veto.

The implementation is native in `mql5/Experts/GoldScalpAI/GoldScalpIntelligence.mqh`. It reads only the completed-bar state already refreshed by `CGoldMarket` in the timer lane. `OnTick()` therefore retains its low-latency tick-flow and position-management path.

The imported Python engine and Titan EA remain research/reference components. They are not attached alongside the main EA because their standalone execution paths can compute dynamic lots or run a slower M15 strategy. The production path remains the main EA's fixed `0.01` lot, maximum three positions, broker-stop, spread, risk, and exit controls. Advisor 1 is unchanged.

The external model can later be connected as a fresh advisory source only after a walk-forward result and a stable bridge contract have been verified. It must never override the native risk and execution rules.
