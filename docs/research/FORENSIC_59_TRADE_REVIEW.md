# Forensic Review of the Demo Scalping History

## Scope

The uploaded archive was separated into controlled-demo trade journals, execution audits, tick data, microstructure features, and legacy paper/test output. This report uses the **59 closed controlled-demo trades** that could be matched to the captured MT5 tick path.

## Baseline result

- Closed trades: **59**
- Wins / losses: **17 / 42**
- Win rate: **28.81%**
- Net result: **$-14.92**
- Expectancy: **$-0.253 per trade**
- Profit factor: **0.47**
- Average win: **$0.779**
- Average loss: **$-0.670**

The strategy was operational, but it did not demonstrate a positive edge. All three principal controlled-demo versions were negative.

## Result by version

| version                                                |   trades |   net |   win_rate |   expectancy |
|:-------------------------------------------------------|---------:|------:|-----------:|-------------:|
| scalping_v5_1_4_cursor_persistence_fix                 |       16 | -4.72 |      0.188 |       -0.295 |
| scalping_v5_2_0_evidence_gated_edge                    |       31 | -7.28 |      0.323 |       -0.235 |
| scalping_v5_2_1_candidate_persistence_edge_calibration |       12 | -2.92 |      0.333 |       -0.243 |

## Spread was the strongest observed separator

| spread_group   |   trades |   net |   win_rate |   expectancy |
|:---------------|---------:|------:|-----------:|-------------:|
| [0.24, 0.27)   |       11 |  3.79 |      0.727 |        0.345 |
| [0.27, 0.3)    |       20 | -8.09 |      0.2   |       -0.404 |
| [0.3, 0.33)    |       12 | -5.9  |      0.167 |       -0.492 |

Trades entered at approximately **$0.24-$0.26 spread** were positive in this sample. The bands above approximately **$0.27** were materially negative. This is an empirical hypothesis, not a guarantee; V6 therefore records every condition in shadow mode but allows executable candidates only at or below **$0.27** until out-of-sample validation proves otherwise.

## Entry location relative to VWAP

| vwap_group   |   trades |   net |   win_rate |   expectancy |
|:-------------|---------:|------:|-----------:|-------------:|
| [0, 1)       |       10 |  2.36 |      0.6   |        0.236 |
| [1, 2)       |       12 | -4.3  |      0.25  |       -0.358 |
| [2, 3)       |       11 | -2.34 |      0.364 |       -0.213 |
| [3, 4)       |        8 | -4.49 |      0.125 |       -0.561 |
| [4, 5)       |        2 | -1.43 |      0     |       -0.715 |

Only the entries within roughly **1 ATR of VWAP** were positive. Entries beyond 3 ATR were consistently poor and represent late trend chasing.

## Tick microstructure alignment

| micro_group   |   trades |   net |   win_rate |   expectancy |
|:--------------|---------:|------:|-----------:|-------------:|
| [-0.01, 0.01) |       21 | -9.03 |      0.19  |       -0.43  |
| [0.01, 0.5)   |        7 | -0.7  |      0.429 |       -0.1   |
| [0.5, 0.55)   |        4 | -3.11 |      0     |       -0.777 |
| [0.55, 0.6)   |        2 |  1.48 |      1     |        0.74  |
| [0.6, 0.65)   |        4 |  1.66 |      0.75  |        0.415 |
| [0.65, 0.7)   |        2 | -1.5  |      0     |       -0.75  |
| [0.7, 1.0)    |        3 |  1    |      0.667 |        0.333 |

Neutral or weak tape was strongly negative. The useful region was generally same-direction microstructure around **0.55-0.65**, although the sample is small and non-monotonic.

## Exit-path findings

- 42 of 59 trades lost.
- 27.37 USD of gross losses was produced by stop-like exits, versus 13.24 USD of gross profits from target-like exits.
- 15 of the 42 losing trades became positive at least once, but only 9 reached +$0.10 and 8 reached +$0.20.
- The median losing trade never established a useful favorable excursion; many positions moved against the bot immediately.
- Simple TP/SL widening could make the single historical path look better, but only by accepting larger unit losses and longer holding periods. That is not robust evidence.

## Chronological robustness check

A 60/40 chronological split was used rather than random cross-validation. The simple hypothesis `spread <= $0.27 and |VWAP distance| <= 3 ATR` was positive in both halves, but it selected only ten historical trades. The tighter `|VWAP| <= 1 ATR` rule is used as the initial executable hypothesis, while all broader candidates are still logged for shadow research.

## Decision

1. **Stop automatic demo promotion from the losing strategy.**
2. Run V6 in shadow mode on live MT5 demo ticks.
3. Use a cost-first gate: spread, VWAP location, aligned tape, persistence, and relative volume.
4. Label candidates with a triple barrier including the real bid/ask spread.
5. Require at least 200 closed shadow trades across at least three days and walk-forward profitability before creating a demo approval artifact.
6. Start approved demo with one position only. Pyramiding is disabled until the approved strategy itself proves profitable.

## Important limitation

All matched trades occurred on one trading date and were SELL trades. The evidence is insufficient to claim that the proposed thresholds generalize across sessions, days, or BUY regimes. That is why V6 is shadow-first and approval expires after seven days.
