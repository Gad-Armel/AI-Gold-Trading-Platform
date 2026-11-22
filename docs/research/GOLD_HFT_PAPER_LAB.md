# Gold HFT paper-replay lab

This is a paper-only event replay mode in the main Python bot. It does not
submit orders or claim to be HFT. It replays observed MT5 bid/ask tick archives
created by `tools/export_gold_tick_probe.py`; it does not generate market data.
Replay runs do not initialize MT5 and can be run without `--mode`.

## Collect and replay

Collect a historical broker quote sample using the existing read-only probe:

```powershell
python -B tools/export_gold_tick_probe.py
```

Then pass the resulting `.npz` archive to the replay lab:

```powershell
python -B tools/gold_hft_paper_lab.py --ticks .\data\research\entry_efficiency\tick_probe\<archive>.npz
```

The same engine is available through the main bot:

```powershell
python -B run_gold_consensus_bot.py --hft-paper-replay .\data\research\entry_efficiency\tick_probe\<archive>.npz
```

This mode is exclusive with `--mode shadow`/`--mode demo`; the CLI rejects
combining them. It does not create an MT5 connection, initialize the dashboard,
or call any trading function. Optional `--hft-*` arguments control the replay
lookback, price threshold, spread cap, assumed latency, holding time, gap policy,
hourly entry cap, and price-unit cost/slippage assumptions. Defaults are
research parameters, not calibrated values.

The replay uses a deliberately simple midpoint-momentum trigger, a configurable
quote lookback, spread gate, assumed submission delay, and holding interval.
Paper entries and exits use the first recorded quote at or after their simulated
due time: buys cross at ask and sells at bid. Results are reported in price
units only; optional fee and slippage assumptions are user-supplied price-unit
scenarios, not verified account fees. Financing, queue priority, partial fills,
market impact, and exchange execution are not modeled. The assumed delay is a
scenario input, not a measured live latency. A quote gap while a position is
open marks settlement unresolved and blocks further simulated entries rather
than inventing a fill.

## Interpretation and boundaries

The source is one broker's top-of-book XAUUSD feed, not a centralized exchange
order book. Local replay handler timing is not end-to-end order latency. This
tool cannot establish an HFT edge, profitability, fill probability, or
readiness for live execution. A genuine HFT project needs an appropriate
exchange-traded instrument, authorized depth feed and execution venue, plus
venue-specific queue/fill modeling and independently measured latency.

Do not use the reported price-unit results as account-currency P&L. Synthetic
fixtures in the unit tests verify code invariants only; they are not market
data, performance tests, training data, or strategy evidence. The existing MT5
EA and Python demo execution path retain their current safety boundaries.

## Free quote-provider note

The `biquote` package is published on PyPI and its documentation describes
unauthenticated quote REST endpoints and SignalR streaming for MT5-backed
Forex/CFD feeds. It provides market data, not an exchange order-entry API or
full-depth exchange order book. A free feed can therefore be considered later
as an optional read-only quote adapter; it cannot provide exchange HFT
execution. It has not been installed or connected by this implementation.
Sources: [PyPI package metadata](https://pypi.org/project/biquote/) and
[biquote API documentation](https://biquote.io/docs/).
