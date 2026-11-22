# SCALP losses and the requested fixed-stop removal

Broker audit: October 9, 2026, 17:58:18 UTC. The cohort starts at the
SCALP-only deployment at 01:33:26 UTC. This is actual closed position history,
including observed position charges, rather than a forecast or hypothetical
strategy comparison.

## What is going wrong

- 132 closed positions, **-$51.40 net**, profit factor 0.679. Win rate 46.2%;
  average winner $1.78 and average loser $2.26. At those observed magnitudes,
  breakeven requires approximately 55.9% winners. This is descriptive arithmetic,
  not a forecast of the next trade.
- Fifteen broker SL closures total **-$75.11**. All other 117 closures total
  **+$23.71**. The fixed stops are a major contributor to this sample's realized
  deficit. These numbers do **not** show what those trades would have done
  without stops; some may have recovered, some may have lost more.
- Other loss-taking rules remain: confirmed market thesis invalidation
  (15 closures, -$41.26), neutral thesis/opposing momentum (7, -$12.67), and
  executable quote reversal (4, -$6.32). Removing the broker $5 stop does not
  disable these rules. Their losses are offset elsewhere among the non-SL exits.
- The BUY trades alone were 103 positions for -$32.55; 29 SELL positions
  lost $18.85. The bot has not exclusively bought throughout the period.
- The primary SCALP bias combines completed M1/M5/M15 votes, and the main
  refreshes its ATR scenario levels with current prices. A persistent BUY bias
  can coexist with a negative short-window M1 move. At the investigation's
  first snapshot all three lanes were BUY, SCALP 96.78, but the open BUY was
  about $2 underwater and recent momentum was -1.28 ATR. A trend prediction
  does not establish the timing, duration or net payoff of each entry.
- Scores are heuristic indicator strength, not a measured success probability.
  Only 42 matched entries scored at least 85; that subgroup netted +$3.29.
  This small retrospective subgroup is not a validated reason to impose an
  85-point gate after seeing these outcomes.
- Some basket profit exits close a newer losing addition along with an older
  winner. For example, at 17:53:42 UTC the same fast-flow profit trigger closed
  one ticket at about +$0.96 and another at -$0.71. Earlier closes under that
  trigger belonged to the same profitable basket. This is basket management,
  not a per-position guarantee of banking a winner. A per-position alternative
  needs comparison because retaining the losing ticket also retains exposure.

## Prepared change and deployment state

The fixed-dollar SCALP stop has been replaced **in the working source** by
an ANALYSIS stop mode: use the entry's candle-derived ATR stop, without a $5
money-stop override or $5 entry-risk cap. Stop validity, broker tick grid,
broker valuation, DEMO identity and capacity checks remain. Adaptive R uses
the sum of actual stop exposure for the held basket, rather than a hidden $5
reference. Paper execution and dashboard labels follow the same mode.

**172 affected tests passed. This change has not been deployed.** The running
main still uses its previous fixed-$5 policy. Automatic approval review rejected
modifying the existing open position because the user had not explicitly
selected the proposed candle-based replacement. No indirect modification,
restart or stop removal was used to bypass that rejection.

The read-only plan at 18:05:09 UTC showed ticket 58844930110: existing SL
4192.22, proposed current-analysis SL 4194.74, planned loss from its actual
4197.25 fill $2.51. Thus a candle-based stop is **not necessarily wider** than
$5. This quote-dependent plan will need fresh verification if approved.
The user was asked whether to use candle-based stops or remove broker stops
entirely. Deployment remains pending that explicit choice.

Prepared tools: `tools/apply_gold_analysis_stops.py` defaults to a read-only
plan; `--apply` would submit SLTP changes only after authorization. The existing
main restart helper preserves positions. No instruction in this report grants
permission to bypass the rejected action.

Artifacts: `diagnosis.json` records ticket-history aggregates and journal exit
reasons; `analysis_stop_change.json` contains the latest read-only proposed stop
change. Journal reasons can describe basket triggers, and the cohort does not
include earlier positions whose entries are missing from today's history.
