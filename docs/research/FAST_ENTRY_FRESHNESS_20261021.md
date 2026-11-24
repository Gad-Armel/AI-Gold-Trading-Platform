# Fast-entry freshness correction — 21 October 2026

The live loop had about five seconds of accumulated analysis work before entry
checks. Its tick history was fetched earlier in that loop, so the last-six-second
coverage check could reject observations because of our processing delay rather
than a broker data outage. Live market health could simultaneously show fresh
top-of-loop quotes, which made this difficult to interpret.

Fast modes now refresh incremental tick history and the executable bid/ask after
slow context, news and history processing, immediately before constructing the
fast decision and running entry checks. A local dataclass copy updates quotes;
protected Advisor 1 calculation and original candle objects are not modified.
Market health is reassessed from the new quote and terminal status. Refresh errors
explicitly block fast entries rather than authorizing against old data.

Heavy V3 advisor calculations return to their existing five-second cadence. The
fast history refresh is independent and runs each loop. This does not promise a
half-second loop: remaining context work and broker latency still determine actual
wall time. A new `fast_entry_refresh` phase is recorded in status.

75 targeted tests passed, including refreshed quotes without mutation, invalid
quotes/history failure rejection, provisional-account binding and existing fast
entry/risk tests. Existing provisional demo assumptions, 0.01 lot and four-position
maximum remain. No filters or cost thresholds were relaxed in this repair.

Separate limitation: a sampled S5 median range was 0.295 while live spread plus
provisional fee/slippage was about 0.67; the configured three-times-cost screen
required about 2.01. Fixing freshness cannot make such a move pass the cost screen
or prove profitability. No order is forced merely to demonstrate activity.
