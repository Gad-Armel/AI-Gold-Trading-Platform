# Prospective evaluation before changing SCALP entries

This is a research plan, not an enabled trading policy. The three tested
proposal-derived setup families failed validation; their final chronological
holdout remains unused. Do not select a replacement threshold from this hour's
losses and call that a validated improvement.

1. Freeze the primary Advisor 1 candidate definition, feature version and
   management policy. Record eligible **and rejected** candidates at decision
   time, executable bid/ask, complete candle availability times, context ages,
   spread, broker contract facts and reason codes. Capture only information
   available then. Merely labelling executed trades creates selection bias.
2. State the prediction target explicitly. A fixed $6/$5/300-second target
   predicts that fixed policy, not the production adaptive exit. Evaluate
   policies separately. Track per-position money risk and basket management
   reference separately; the analysis TP1/SL ratio is neither broker reward/
   risk nor net expectancy.
3. Use executable ask to buy and bid to sell, with measured delay, stressed
   adverse slippage and independently specified charges. Bid/ask already
   charge spread. Do not subtract it again from a net label. Preserve ambiguous
   or missing-fill cases instead of imputing a successful trade.
4. Reconstruct full broker position histories, including entry/exit volumes,
   charges and partial fills. Keep intended orders, reported results and
   confirmed deals distinct. Pending responses do not authorize blind retries.
5. Group overlapping positions and immediate reentries into market episodes.
   Split chronologically, purge overlapping label horizons, and keep calibration
   separate from both training and final evaluation. Warm-up history must match
   the finite live candle cache. Historical dates already inspected are not a
   fresh blind test.
6. Compare an unchanged baseline against one frozen candidate change with the
   same exits, costs and exposure. Report net dollars, mean episode outcome,
   profit factor, drawdown, turnover, holding time, win/loss magnitudes and
   rejected opportunities. Report uncertainty and results by regime; an
   aggregate short positive total is insufficient.
7. If a small model is warranted by enough independent events, calibrate its
   probabilities on held-out chronological data. Assess probability reliability
   and net expectancy, not just classification accuracy. Correlated indicators
   are not independent votes, and the current heuristic score is not a win
   probability. Do not use it for Kelly sizing or automatic lot escalation.
8. Require positive prospective and cost-stressed evidence before promotion.
   First shadow the policy without order authority, then compare on the demo
   account with a documented version and rollback. Preserve SCALP-only capacity
   three, $5 planned stop per position, winning-only additions and continuous
   reassessment. Native terminal hosting would require a deliberate deployment
   redesign for this external Python process.

Specific unresolved hypotheses: whether a short-window negative M1 momentum
weakens primary BUY candidates in range conditions; whether nominal TP1 cost
and payout gates reflect actual $5 broker exposure; whether basket trailing
normalization changes outcomes after additions. Test each independently rather
than combining them into a tuned veto after seeing losses.
