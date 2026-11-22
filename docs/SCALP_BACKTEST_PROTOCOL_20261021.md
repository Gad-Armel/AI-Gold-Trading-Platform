# GoldScalpAI 3.23 — real-tick backtest protocol (2026-10-21)

The one test that has never been completed is a full historical Strategy Tester
run. `mql5/validation/historical-test-blocker.txt` records the last attempt
failing with "tester not started because the account is not specified", and
`scalper-expert-321-validation.json` lists "Full historical EA backtest not
completed" as an open limitation. This document fixes the protocol **before**
any result exists, so the outcome cannot be reinterpreted after the fact.

Everything below is pre-registered: periods, delays, input variants, metrics
and pass/fail gates. No input may be tuned after an out-of-sample (OOS) result
is seen; a failed gate sends development back to the in-sample (IS) window only.

## 1. Decision question

Does the **shipped v3.23 default policy** (risk caps, plus the `BlockAsiaSession`
gate added the same day), executed at measured retail
latency and costs, have positive expectancy on calendar data that did not
influence its design? One question, one set of gates.

## 2. Prerequisites

1. Current build compiled and installed:
   `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\compile_gold_scalp.ps1`
   then `.\tools\install_gold_scalp.ps1` (startup launcher refuses mismatched hashes).
2. Advisor-1 replay export for REQUIRED-mode runs:
   `python -B .\tools\export_advisor1_replay.py` then copy
   `mql5\validation\advisor1_replay.csv` to
   `%APPDATA%\MetaQuotes\Terminal\Common\Files\GoldScalp\advisor1_replay.csv`.
   Current export coverage: **2026-08-05 → 2026-09-17, 11,672 reports**.
   Re-export to extend; REQUIRED-mode runs must stay inside coverage or they
   correctly block every entry.
3. MT5 tester: **Every tick based on real ticks**, local agents only, demo
   account specification saved in the tester profile (this is what failed last
   time), hedging, USD, the same XAUUSD symbol as the demo broker.
4. Deposit and costs: $100 deposit per the French guide, broker commission
   matching the live account (the demo measured `commission_price = 0.0`,
   spread-only), `RoundTripCommissionUSD` tested at both `0.00` (live parity)
   and `0.10` (shipped default).

## 3. Which calendar is which — contamination is the main trap

| Window | Status | Why |
|---|---|---|
| earliest real ticks → **2026-06-30** | **OOS-pre-development** | The 3.x policy family was designed during Jul–Oct 2026; earlier data did not influence it. Strongest backtest evidence available, subject to regime shift. |
| 2026-07-01 → 2026-08-04 | semi-IS | Early policy development, partial feedback. Report separately, never merge into OOS. |
| 2026-08-05 → present | **IS** | Live-demo feedback in this window drove versions 3 → 3.10 → 3.20 → 3.21 → 3.22 → 3.23, including the entry guards and the Asia gate (calibrated on the 2026-08-12 → 09-10 stop-out cohort). Reporting it as OOS would be look-ahead. |
| from protocol start → +4 weeks | **true OOS (forward)** | Nothing before it may change after it starts. |

If the broker provides fewer than 9 months of real ticks, shrink the IS window
first and keep **at least 8 complete weeks** of OOS-pre-development data.
Split OOS into **two disjoint sub-windows** of ≥4 weeks each (e.g. first half /
second half) and require both to pass — one aggregate can hide a regime that
never repeats.

## 4. Run matrix (pre-registered)

Delays are MT5 execution delays (not network latency): **0, 150, 350, 500 ms**.
350 ms anchors on the measured demo `order_send_p95_ms = 351.579`
(`data/research/goldhft_20261020/s30_execution_costs.json`).

| Variant | Inputs | Delays | Windows | Purpose |
|---|---|---|---|---|
| **V0** (mandatory) | shipped defaults | **350** | IS + both OOS | the claim |
| V0-robust | shipped defaults | 0, 150, 500 | both OOS | latency sensitivity |
| V0-commission | `RoundTripCommissionUSD=0.10` | 350 | both OOS | cost conservatism |
| **V1** | `Advisor1Mode=REQUIRED` + replay | 350 | replay window only (2026-08-05→09-17, IS) | required-confirmation policy behaves; **never** compared against REFERENCE results as if same policy |
| **V2** (diagnostic) | `ScalpEntryStartUTC=7` + `ScalpEntryEndUTC=16` | 350 | both OOS | the Asia half of the stop-out hypothesis now ships in V0 as v3.23's gate; V2 tests the *stricter* London+overlap-only restriction (adds NY and evening blocks) from `data/research/xauusd_audit/stopout_analysis_20261021.json` |
| **V3** (diagnostic grid) | `MinimumScalpScore` ∈ {55, 62, 70} × `FrequentEntryMode` ∈ {true, false} | 350 | both OOS | threshold sensitivity; **all six cells reported, no best-cell selection** |

No optimizer runs. `OnTester` (profit/max drawdown, ≥30 trades) is recorded per
run but is not a selection criterion in this protocol.

## 5. Metrics recorded for every run

From the tester report plus `VALIDATION_SUMMARY` in the journal: trades, net,
PF, expectancy, max equity DD %, win rate, avg win / avg loss, hold-time
median, stop-out share (gross loss from `[sl]` closes vs total), per-session
net (ASIA 00-07 / LONDON 07-12 / OVERLAP 12-16 / NY 16-21 / ROLL 21-24 UTC),
per-hour net, entries/hour vs the 36 cap, requotes/rejections, and a bootstrap
95% CI on per-trade expectancy (10,000 resamples).

Required cut — mirror of the live stop-out analysis:
broker-stop trades by session and by entry evidence band, so the live finding
(69 of 112 stops carried evidence ≥85; ASIA produced $236 of $398 stop damage)
can be confirmed or refuted on the EA's own history.

## 6. Pass / fail gates (pre-registered)

**Gate A — economics (both OOS sub-windows, V0 at 350 ms, commission 0.00):**
net > 0 **and** PF ≥ 1.10 **in each** sub-window.

**Gate B — statistical:** lower bound of the bootstrap 95% CI on per-trade
expectancy > 0 on pooled OOS at 350 ms (n ≥ 500 trades required; if the policy
cannot produce 500 OOS trades, that itself fails the gate — a strategy whose
sample is too thin cannot support any claim).

**Gate C — robustness:** net > 0 at both 150 ms and 500 ms; and no single
session contributes more than 100% of gross profit (i.e. profit is not one
session's lucky bucket — the live data shows exactly this fragility pattern).

**Decision table**

- A+B+C pass → freeze inputs, run the **true OOS forward demo for 4 weeks**
  (§3 last row) under this document unchanged; only a forward pass supports a
  "validated" claim. Real-account execution stays disabled regardless.
- A fails → the shipped policy has no edge at measured costs. Development
  returns to IS only, with the remaining stop-out findings (anti-chase entry
  timing; session gating already ships as v3.23) implemented as a **new version
  + new order-comment tag**, and the full matrix rerun from scratch.
- B or C fails → diagnostic variants (V2/V3) may explain *why*, but their
  results are hypotheses for the next version, not a promoted configuration.

## 7. Threats that must be stated in any result summary

1. **News filter is off in the tester.** `TesterWithoutNews=true` means every
   backtest is policy-minus-news-filter. Live blocks USD releases; the backtest
   neither pays their losses nor skips them. A backtest is therefore not a
   validation of the full live policy (French guide, "TesterWithoutNews").
2. **REFERENCE and REQUIRED are different policies.** Never merge their rows.
3. **Aug 2026 → present is IS**, not OOS, for anything in the 3.x family.
4. Tester fills ignore the broker's async queue and rejection behavior; the
   live path (`OrderSendAsync`, 8 s ambiguity window, retry ladder) is only
   exercised live.
5. Historical spread regimes differ from the observed live median 0.38–0.46;
   report the tester's average spread next to results.
6. The stop-out analysis cohort is the Python consensus bot, not this EA —
   V2 exists precisely to test transfer rather than assume it.
7. `OnTester`'s profit/DD objective invites overfitting if anyone later runs an
   optimization; this protocol forbids optimizing on any window here.

## 8. Commands

```powershell
# build + native invariants (236 checks)
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\compile_gold_scalp.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\test_gold_scalp.ps1

# Advisor-1 replay for V1
python -B .\tools\export_advisor1_replay.py
Copy-Item .\mql5\validation\advisor1_replay.csv "$env:APPDATA\MetaQuotes\Terminal\Common\Files\GoldScalp\advisor1_replay.csv"
```

Tester UI: profile → save a symbol/account specification (fixes the historical
blocker), modeling "Every tick based on real ticks", delay presets from the
variant table, deposit $100, then attach `GoldScalpAI` on XAUUSD M1 with
`EnableDemoOrders` irrelevant (tester simulates orders regardless).

Archive every report under `mql5/validation/backtest/` as
`<variant>_<delay>ms_<window>.html` plus a one-row CSV summary appended to
`mql5/validation/backtest/summary.csv`, so the full matrix — including failing
runs — stays on record.
