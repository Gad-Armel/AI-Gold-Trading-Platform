# Review of the centralized XAUUSD proposal

## Outcome

Adopt the separation between observed market features, verified macro context,
position management and protected execution. Much of it already exists in the
main runner. Do not install the supplied execution loop or describe its weighted
formula as a trained AI. The two-position global limit, exact 0.01-lot entries,
$100 capital profile and Advisor 1 protection remain binding.

## Changes applied

- Added completed-candle three-bar gap sizes normalized by ATR, range-reclaim
  sweep flags, directional efficiency and a simple regime diagnostic to adaptive
  context. These fields are explicitly `RESEARCH_ONLY`; they do not authorize
  trades or change the existing exit conditions. They describe observable price
  geometry, not demonstrated institutional activity.
- Forward recording now captures new or revised release values, entry permission
  changes, position changes and exit-reason changes within the same candle.
  Refresh timestamps alone do not create duplicate decision rows.
- Position and exit details are recorded for later evaluation of continuation
  versus closing. These observations do not supply a trained exit model by themselves.

## Corrections and rejected claims

| Proposal | Assessment |
|---|---|
| PPO/SAC central brain | Sample contains no trained policy, environment, reward, optimizer or weights. Its hand-written formula is not a neural-network forward pass. PPO requires policy training; its original paper does not establish a gold-trading edge. |
| FinBERT score as gold direction | Financial text sentiment is not a calibrated XAUUSD return forecast. A positive economy headline can have different implications for gold. Require timestamped, instrument-specific validation. |
| Fixed macro score `0.15` | Fabricated bullish input. Retain verified data and explicit missingness. |
| Lot multiplier | Violates the fixed 0.01-lot instruction. Rejected. |
| Stop calculation | `equity_risk / (volume * contract_size)` is already price distance for the assumed linear USD gold contract. Multiplying by `point` again makes the stop 100 times tighter when point is 0.01. For $100 equity, 1.5% risk and 0.01 lot on a 100-ounce contract, the intended distance is $1.50, not $0.015. Existing execution uses broker-valued risk checks. |
| `US10Y - CPI` as real yield | Trailing CPI is not a maturity-matched market real yield. Existing FRED DFII10 input is the inflation-indexed 10-year Treasury yield; keep its publication cadence explicit. |
| `high - low` as ATR | One-bar range omits previous-close gaps and averaging. Existing adaptive code uses smoothed true range. |
| Forming candle features | Sample requests position zero and uses its last row. Keep explicit completed-bar filtering for these diagnostics. |
| Close every XAUUSD position | Sample lacks ownership checks and may close manual or other-system positions. Retain controlled magic-number/account identity checks. |
| `1 - conviction` as exit confidence | No calibration or learned continuation value. A weak entry signal does not prove a position should close. |
| Asynchronous order placement | The example actually calls `order_send` synchronously. Concurrent sends would complicate the shared position cap; keep the serialized execution boundary. |
| Sub-2ms VPS execution | Unsupported by a city/location label. Network round trips and broker execution require measurement. No VPS purchase or migration is justified by this claim. |
| AI handles 99% of exits | No evidence supplied. Do not publish this statistic. |
| Weekly automatic retraining | A schedule alone does not validate a policy. New models must remain outside execution until independent evaluation passes. |

These are implementation and evidence findings, not a claim that every suggested
model family or candle pattern is ineffective. The new diagnostic features must
earn their place through point-in-time evaluation before affecting decisions.

## Sources

- Supplied `pasted-text.txt` in attachment `37815a12-2b39-476d-86f8-f4699982d71b`.
- MetaQuotes, [order_calc_profit](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py): broker estimate in account currency.
- Federal Reserve Bank of St. Louis, [DFII10](https://fred.stlouisfed.org/series/DFII10): daily inflation-indexed Treasury yield.
- Araci, [FinBERT: Financial Sentiment Analysis with Pre-trained Language Models](https://arxiv.org/abs/1908.10063), 2019.
- Schulman et al., [Proximal Policy Optimization Algorithms](https://arxiv.org/abs/1707.06347), 2017.

Sources checked September 10, 2026. No performance improvement is claimed from
the newly recorded diagnostics; no trades were sent as part of this review.
