# V6.3.4 Cost-Aware Microstructure Gate

This change is a shadow-first hypothesis, not a profitability guarantee. The
implementation was informed by the following primary, academic, or regulatory
sources:

1. SEC, *Report to Congress on Algorithmic Trading* (2020): pre-set controls,
   testing and operational supervision.
2. CFTC, *Risk Controls and System Safeguards for Automated Trading
   Environments* (2013): pre-trade controls, monitoring and system safeguards.
3. ESMA, MiFID II Article 17: thresholds, limits, testing, monitoring and
   resilient algorithmic systems.
4. ESMA, *Supervisory Briefing on Algorithmic Trading in the EU* (2026):
   pre-trade controls, real-time monitoring and kill functionality.
5. BIS Markets Committee, *FX execution algorithms and market functioning*
   (2020): fragmented liquidity, execution risk and data architecture.
6. BIS Markets Committee, *Electronic trading in fixed income markets* (2016):
   liquidity-state monitoring and automated-trading governance.
7. Cont, Kukanov and Stoikov, *The Price Impact of Order Book Events* (2014):
   short-horizon price changes and order-flow imbalance.
8. Gould and Bonart, *Queue Imbalance as a One-Tick-Ahead Price Predictor in a
   Limit Order Book* (2015): imbalance as a probabilistic short-horizon feature.
9. Huang and Stoll, *The Components of the Bid-Ask Spread* (1997): transaction,
   adverse-selection and inventory components of spread.
10. Budish, Cramton and Shim, *The High-Frequency Trading Arms Race* (2015):
    continuous-market latency and bid/ask cost mechanics.
11. Aquilina, Budish and O'Neill, *Quantifying the High-Frequency Trading Arms
    Race* (2022): effective spread, price impact and latency-arbitrage costs.
12. Cont, Cucuringu and Zhang, *Cross-Impact of Order Flow Imbalance in Equity
    Markets* (2023): integrated order-flow imbalance and price impact.

## Implemented interpretation

- Fixed the live schema mismatch: the gate now accepts `1`, `3`, `5` (and keeps
  compatibility with `1s`, `3s`, `5s`).
- Uses the existing broker top-of-book quote-flow proxy; it is not mislabelled
  as true depth or exchange order-book imbalance.
- STRICT entry requires data quality >= 0.70 and aligned 3-second quote flow
  with absolute magnitude >= 0.10.
- STRICT entry blocks spread expansion above 0.04 M1 ATR and blocks `STALLED`
  or `DISLOCATED` micro-regimes.
- All checks are observable in gate telemetry. Demo remains approval-locked and
  real-account execution remains disabled.
