# Main bot research and promotion log

Research is iterative, but finding an interesting idea is not enough to activate
it. This is a manual review protocol, not an unattended research scheduler.

## Promotion protocol

1. Record the primary source, mechanism, instrument/feed assumptions, and a
   concrete failure mode in our implementation or a falsifiable hypothesis.
2. Separate correctness fixes from unvalidated predictive strategy changes.
3. Add focused tests, then broader broker, inverse, exit and dashboard regressions.
4. For predictive changes, retain raw ticks, cost assumptions, failed trials,
   chronological validation and an unseen forward segment. Do not repeatedly
   optimize to an already inspected holdout. Small positive samples do not pass.
5. Deploy supported correctness changes on demo only. Promote a new predictive
   strategy only after adequate cost-net evidence, not a seller's screenshot.
6. Preserve fixed 0.01 volume, four combined slots, broker SLs and Advisor1.
   Never loosen freshness/cost/risk controls just to increase activity.
7. Review broker-confirmed outcomes; keep negative findings. Never guarantee
   profitable automation or describe a heuristic score as a calibrated win rate.

## 26 October 2026 — executable quote revalidation

Sources:
- [MT5 Python order_send](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py)
- [Latest tick](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py)
- [Symbol execution properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants)

Finding: the main horizon executor captured bid/ask before several broker/risk
operations and `order_check`. Capacity was rechecked afterward, but quotes were
not. A valid signal can become a poor entry during those operations. Market
execution should not be treated as if the deviation request guarantees a fill
inside a fixed band.

Implemented: capture a new quote immediately before submission; reject missing,
invalid or stale quotes; reject movement outside the existing local deviation
budget (points converted using broker point size); recheck spread, analysed
reward/risk, actual stop grid/distance and planned dollar risk. Do not mutate or
blindly retry an obsolete request. Let the normal loop recompute the decision.
Journal the final quote, drift and check timestamp in successful entry context.

Scope: main horizon openings only. Protective exits and inverse source-linked
closures are not subjected to an entry-only drift veto. Inverse directions still
inherit the main's accepted fills. No new predictive model or sizing rule.

Limits: the quote can still change between this local check and broker execution;
this narrows a time-of-check/time-of-use gap but cannot make it atomic. The new
check is a correctness guard, not evidence of improved expected return. Its
extra broker calls can add latency, so evaluate their live cost rather than
claiming a guaranteed speedup.

Validation: 170 targeted tests pass, including quotes moving during order_check,
unchanged BUY/SELL requests, exact drift boundary, missing/invalid/stale quotes,
API exceptions and changed risk, plus prior main/inverse/exit regressions.

Previous research and negative markout results:
`docs/GOLD_ULTRASHORT_RESEARCH_20261026.md`.
