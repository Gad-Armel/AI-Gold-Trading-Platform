# Main bot speed and entry audit

User requested a stop, visible project terminal and investigation. Verified and
stopped only main process tree 33020/26064. Opened visible PowerShell in project.
SCALP cleanup returned zero remaining closes and no failures. Main remains stopped;
Advisor1's 18 protected file hashes are unchanged.

Last recorded processing phases total about 1,415 ms before status serialization:
snapshot 5.7; quote protection 2.5; cross-market 51.4; source/candle analysis
294.4; tick advisor 323.3; consensus 8.9; news 5.2; contexts 109.6; account history
15.3; fast-entry refresh 220.5; lanes 367.1; persistence 11.3 ms. This is one
recorded sample, not a latency distribution; the 500ms cadence is a target.

Change: context cache reuses candle analysis for five seconds in fast mode,
cross-market context for five seconds (one second in protective mode), SMC
observation for five seconds (0.5s when enforced). Deep copies prevent entry
decorations from mutating cached analysis. Expired fetch failures propagate
rather than silently serving expired values. Existing data freshness guards
remain authoritative. Quote protection, fast confirmation, broker risk and
execution checks are not cached by this helper. The slower tick advisor already
uses five-second cadence and was not further delayed.

Remaining deliberate constraints: one completed directional fast candle;
three-second net movement beyond spread and bid/ask agreement; .65 efficiency;
tick continuity/freshness; range above estimated costs; one-second signal and
post-exit confirmation; two-second entry spacing; 60 entries/hour ceiling;
30-second loss cooldown; profitable-only additions with strong evidence and a
fresh completed candle; slot capacity and $5 maximum trade risk. Opposite setup
scanning independently checks S5/S15/S30. These are strategy/exposure controls,
not CPU defects. No forced nonstop orders or loss averaging was introduced.

No live speed or profitability improvement is claimed: the executor was not
restarted, per the stop request. Measure phase distributions after a later
authorized restart. Self-check: scoped main caching; freshness/risk retained;
test mutation isolation and expiration; explicit measurement limitation.
