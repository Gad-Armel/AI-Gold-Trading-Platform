# Explicit experimental demo activity profile

User authorized simplifying entry confirmation for frequent demo trading.
FAST_DEMO_ACTIVITY_MODE applies only when account.trade_mode == 0. It lowers
the three-second midpoint move floor from spread to 0.1*spread and directional
efficiency floor from .65 to .35. Both bid and ask must progress positively;
flat quotes, missing updates, stale data, spread expansion, extension, range
cost and stop-risk/capacity checks remain. One closed directional candle remains.
No changes to Advisor1, lots, protective stops or exposure limits.

Validation: 81 focused tests passed. New test demonstrates a small directional
move accepted by activity but rejected by control, and flat quotes rejected
by both. Safely reloaded with one broker-protected position. These thresholds
are user-requested experiments, not optimized or validated profitable values.
Rollback: FAST_DEMO_ACTIVITY_MODE=False and reload main safely.

Self-check: test confirms intended relaxed boundary; explicit demo-only gate;
risk preserved; telemetry exposes thresholds; no nonstop fill/profit guarantee.
