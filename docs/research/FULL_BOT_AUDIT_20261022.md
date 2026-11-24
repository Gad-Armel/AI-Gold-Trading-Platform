# Main bot retrospective audit — 22 October 2026

## Evidence and scope

Audited main-demo broker deals over the preceding 24 hours, reconciled all
315 closed positions to exact entry deal IDs in the journal, and reconstructed
their executable-side favorable/adverse excursions from a fresh broker tick
capture. This is a retrospective execution/strategy audit, not a causal
counterfactual backtest or an independent walk-forward validation.

Artifacts:
- `data/research/full_audit_20261022/trade_audit.json`
- `data/research/full_audit_20261022/capture/metadata.json`
- `data/research/full_audit_20261022/excursions.json`

As of 17:10 UTC / 18:10 Lagos approximately, the reconciled history contains:

| Entry frame | Closed trades | Net USD | Wins / losses |
| --- | ---: | ---: | ---: |
| S1 | 13 | -14.41 | 1 / 12 |
| S5 | 191 | -52.32 | 72 / 118, plus one flat |
| S15 | 72 | -9.87 | 34 / 38 |
| S30 | 39 | -46.15 | 14 / 25 |
| Total | 315 | -122.75 | 121 / 193, plus one flat |

Win rate 38.41%, profit factor 0.573, average win +1.359 USD and average
loss -1.488 USD. Net includes recorded profit, commission, swap and fees,
including manual closes of bot-opened positions. Open/partial/reversal or
window-truncated entries are excluded by the audit tool. These dollars are
broker results, not a percentage of the nominal 100 USD configuration label.

## What is wrong

### Strategy weakness, not just missed exits

The current trading authority is a heuristic run of same-direction fast
candles with a body/range score. Neither the score nor a research tier is a
calibrated winning probability. Structural and ML research remain diagnostic.
Shortening the timeframe does not establish an edge: every sampled frame lost.
Choosing S15 just because it lost less on this reused sample would be fitting
the selection policy to historical outcomes, not validating it.

255 entries failed the existing six-second directional micro-confirmation
condition but were admitted because that check was warnings-only. They lost
106.93 USD. The 60 passing entries also lost 15.82 USD. Restoring this
confirmation is an experimental noise reduction, not proof of profitability.
The existing condition requires directional six-second displacement greater
than current spread and sampled path efficiency at least 0.65.

HTF-aligned/neutral trades lost 61.97 USD; opposed trades lost 60.78 USD.
Simply banning countertrend trades is not established as the solution.
Successful entry journal records show no repeated setup IDs in this day's
review: duplicate fills of one setup were not the observed cause.

### Risk and consistency defects

1. ANALYSIS stop mode deliberately bypassed `MAX_TRADE_RISK_USD`, while the
   setting remained 5 USD. Twelve audited initial stop distances exceeded
   5 price units (approximately 5 USD at 0.01 lot / contract 100). The broker
   entry now enforces its monetary stop estimate in all modes. It rejects an
   over-budget setup; it does not squeeze its structural stop or alter volume.
   The dashboard now reports the enforced planned cap rather than null.
   This is planned price-to-SL exposure, NOT an all-in guaranteed loss limit:
   adverse fills, stop gaps, fees and commission can exceed it.
2. S1 was absent from the existing fast-stop tick-grid normalization path,
   so otherwise valid three-decimal stops could fail broker-grid checks.
   S1 now follows the same normalization and validation as S5/S15/S30.
3. Direct entry quote checks rejected stale quotes but not nonfinite or
   excessively future-dated ages/prices. Both entry routes now reject these.
4. Signal persistence could carry a BUY/SELL timer across S5/S15/S30 source
   changes. Persistence now resets when the source timeframe changes, even
   if the direction remains the same.
5. The account-bound exit-state snapshot omitted the entry period. Restarting
   AUTO could pin an existing fast position to the fallback S30 instead of
   its entry frame. Valid periods are now saved and restored; old snapshots
   without this information cannot retroactively recover it.

### Exit findings

315 positions had quote coverage. Of 193 losing positions, 105 were briefly
gross-positive, but only eight reached an observed +0.6R. Many small positive
excursions do not clear costs or justify a universal early exit.
Four of those eight explicitly closed through break-even protection with
small negative fills; other cases include intraloop peaks and giveback/SL
outcomes. Tick extrema do not prove those peaks were attainable exits.
Do not infer that tightening every exit would recover 122.75 USD.

Exit thresholds were therefore not optimized to this history. Existing broker
SLs, quote-flow protection, adaptive exits, profit lock and dynamic no-fixed-TP
policy remain. Their software-based trailing cannot guarantee a fill at the
observed high-water mark or replace broker stop execution guarantees.

## Deployed changes and preserved constraints

- Restore directional micro-confirmation, separate from the range/cost veto.
- Keep `FAST_RANGE_COST_FILTER_ENABLED=False` and the user's session loss
  stop disabled; neither is silently re-enabled.
- Deploy AUTO selection (S5/S15/S30), removing S1 from the automatic live
  demo trial. Explicit S1/MICRO options remain experimental, not promoted.
- Keep demo only, fixed 0.01 lot, at most four positions globally, broker SLs,
  and Advisor1 unchanged. No naked-stop fallback or blind retry added.
- Hold new entries temporarily for deployment; verify flat before restart,
  then restore the user's previously enabled entry state after checks.

## Validation and limits

130 targeted tests pass, including broker execution tests and new regressions
for risk enforcement, future/nonfinite quotes, S1 tick-grid stops, exact
deal/fee reconciliation, source-specific confirmation and restart timeframe
recovery. All 18 protected Advisor1 hashes match the baseline.

Tests establish implemented behavior, not positive expectancy. Grouped
historical comparisons are selection-biased/correlated and cannot measure
the counterfactual performance of signals admitted by the new policy. A
fresh prospective demo sample is still needed. No claim is made that the
strategy is now profitable or that the entire repository suite is green.

Official execution semantics used for the safety review:
- https://www.mql5.com/en/docs/trading/ordercalcprofit — estimate in account currency.
- https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants — broker tick grid and stop-distance properties.

## Launch main and dashboard

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1 -ScalpTimeframe AUTO
```
