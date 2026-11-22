# Evidence-led rethink of the scalper

Read-only 24-hour broker/journal audit on the approved demo, October 29 2026.
Raw grouped audit: data/research/exit_review_20261029.json. 131 closed positions,
34 wins/97 losses, net -56.06 USD including recorded commission/swap/fees; profit
factor .424. Average win 1.2153, average loss -1.0039. All entries matched journal.
This window includes several changed strategies and is not a controlled test.

Three-source allocation: 77 positions, 18 wins/59 losses, net -35.62, PF .270.
55 of these positions stopped out for -47.74. Across all strategies 69 stop
exits lost -77.11. Median holding time in the vote group was 27.899 seconds.
One-dollar profit-lock exits: 16 positions, 15 wins/1 loss, net +13.02. This
does not establish that those exits were optimal; their positive conditional
outcomes are selection-biased. It does establish that stop losses dominate
observed losses. Delaying winner exits alone is not supported as the fix.

## Resource hierarchy

1. Executable broker bid/ask ticks, arrival rate, spread, quote age, measured
   fill slippage/latency. These are mandatory for sizing realistic net movement.
2. Price-pressure and directional persistence across short horizons, combined
   with acceleration/volatility regime and pullback/retest structure. They must
   be tested jointly rather than counted as independent votes.
3. M1/M5 structure and session/news context as regime and liquidity information,
   not an automatic order every time a slowly refreshed score remains high.
4. Genuine order-book/transaction imbalance only when the data exists. Current
   XAUUSD subscription succeeded but returned zero depth levels in this check;
   reported metadata depth 32 is not evidence of usable live orders. Quote
   changes must not be relabelled as exchange buy/sell aggressor volume.
5. Independent external gold futures data, if available and timestamp-aligned,
   is a research candidate, not permission to assume futures lead this feed.

MT5/API candle scores can share the same price information; agreement is not
proof of statistical independence. A score of 75 is heuristic strength, not a
75% win probability. A second position multiplies the same setup exposure and
does not provide another independent success trial.

## Replacement evaluation design

Keep a context analyzer, a fast executable-flow analyzer and a cost/execution
analyzer. Train/calibrate a small model only after collecting correctly aligned
broker data and cost labels. Target post-cost expected return and drawdown,
not trade count or win rate alone. Use chronological walk-forward splits,
purging overlapping labels, then frozen forward paper comparisons before demo
promotion. Separate trend continuation from range reversion; no automatic
promotion from this retrospective sample (S5's 10 trades are insufficient).

Evaluate exits with executable maximum-favorable/adverse excursion, realized
capture ratio and fixed post-exit 5/15/30-second markouts. These are diagnostic
counterfactuals, not realizable alternative fills or evidence that a stopped
trade should have been held indefinitely. Compare identical frozen entry sets,
same initial SL/risk and measured costs. Only then choose wider adaptive
giveback or a sustained momentum-reversal exit. Never widen hard loss limits
merely to make the win percentage look better.

## Primary sources and limits

- https://arxiv.org/abs/1011.6402 — Cont, Kukanov, Stoikov: order-flow imbalance
  and short-horizon price changes in equity order books. Not an XAUUSD alpha proof.
- https://arxiv.org/abs/1512.03492 — Gould, Bonart: queue imbalance prediction
  for ten Nasdaq stocks; requires real queue sizes and market-specific validation.
- https://arxiv.org/abs/2404.15478 — spot precious-metals market making and
  futures/spot relationships. Different execution model from a retail CFD scalper.
- https://www.mql5.com/tr/book/advanced/python/python_marketbook — official MT5
  depth subscription/read API. Availability must be verified at runtime.
- https://www.gold.org/gold-market-structure/global-gold-market — venue context;
  no single retail feed represents all global gold liquidity.

No live strategy/stop/exit settings were changed in this research turn. Main
continues under the user's previously activated strategy. Findings do not
establish positive future expectancy. Self-check: reconciled account-specific
outcomes; explicit changing-strategy/selection caveats; no speculative alpha
claim; no blind exit relaxation; primary-source research links retained.
