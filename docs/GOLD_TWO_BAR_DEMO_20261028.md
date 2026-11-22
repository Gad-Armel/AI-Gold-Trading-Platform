# Experimental fast-entry demo profile

The main AUTO selector now uses two completed S5/S15/S30 candles and requires
median recent range greater than 1.5 times estimated round-trip costs. Previously
it required three candles and three times costs. Higher staged addition counts
remain intact. Even-count medians now use the arithmetic middle pair.

This increases eligible patterns, not proven profitability. A frozen comparison
over 9,792 broker ticks (22:24:57–22:54:57 UTC) found zero eligible patterns under
the control and four under the experiment: three S5 and one S15. All four had
negative executable 15-second markouts after assumed costs. Overlapping labels
are neither independent trades nor a replay of the bot's adaptive exits.
Artifacts: data/research/two_bar_demo_20261028.

The profile retains fresh executable bid/ask confirmation, continuous tick
coverage, six-second follow-through, mandatory SL, 0.01 lot, configured capacity
and $5 trade risk limit. Provisional account-bound demo costs still expire after
24 hours. Advisor1 and inverse strategy code are unchanged.

Validation: 111 focused unit tests passed. Updated an obsolete stale-cost test
to assert the existing 24-hour rejection policy rather than weaken that policy.
The restart helper found no existing main worker; the normal duplicate-safe
launcher subsequently started one main instance. No orders are forced.

Rollback: set FAST_CONFIRMATION_BARS=3 and FAST_RANGE_COST_MULTIPLE=3.0 in
config/gold_consensus_settings.py and reload the demo worker safely.

Self-check: correctness supported by focused tests; safety guards preserved;
scope limited to main candidate selection and launch text; tick comparison is
reproducible from saved ticks; trading performance remains unproven and the
small comparison was unfavorable after costs.

Live observation 22:57:57–23:01:05 UTC: 37 dashboard samples, 6 BUY/5 SELL/26
WAIT, no observed positions and no main/inverse deals in the final broker
history query. Follow-through, executable bid/ask confirmation, cost range,
and intermittent quote gaps blocked entries. Initial broker snapshot timed out
over IPC, so the monitor could not establish start/end account continuity;
separate connection checks verified the current demo and enabled trading.
This observation does not demonstrate continuous scalping. Main remains running.
