# XAUUSD validation — 22 October 2026 (Lagos)

## Scope

Read-only MT5 demo capture and offline replay of the existing A/B/C research
engines. No orders were sent, no entry hold was removed, no strategy parameters
were optimized, and no native EA was installed during this continuation.

## Data and method

- Capture: `data/research/external_regime_20261022/capture/metadata.json`.
- Window: 20 October 23:21:33 to 21 October 23:21:33 UTC.
- 417,439 quotes; median spread 0.37, 90th percentile 0.45 in price units.
- Replay: `data/research/external_regime_20261022/abc_replay.json`.
- Existing assumptions retained: 0.35-second modeled latency and 0.30 price-unit
  round-trip costs in addition to bid/ask spread. These are assumptions, not
  measured execution guarantees. Independent engine paths are not a combined
  four-position portfolio.
- This window overlaps earlier research; it is not an independent holdout or a
  prospective live performance test. Session/news restrictions are not fully
  modeled. Results concern completed simulated trades only.

## Results

| Engine | Closed trades | Wins / losses | Net price units | Profit factor |
| --- | ---: | ---: | ---: | ---: |
| A: trend pullback | 4 | 3 / 1 | -2.73 | 0.67 |
| B: opening range breakout | 1 | 0 / 1 | -5.33 | 0.00 |
| C: range re-entry | 0 | 0 / 0 | 0.00 | unavailable |

Engine A illustrates why win rate alone is insufficient: three wins did not
cover one larger loss and modeled costs. These very small samples do not
establish positive expectancy. Engine C's lack of trades is not a success.
The internal `PAPER_ACTIVE` score is a research state, not permission to trade;
all three reports explicitly retain `execution_enabled: false`.

## Checks and decision

- 24 targeted tests passed: external regime integration, capture boundaries,
  and causal replay.
- All 18 protected Advisor1 files match their baseline SHA256 hashes.
- Main status was updating during inspection, in demo mode. A fresh broker
  history capture succeeded; this does not imply entry conditions were met.
- Keep new entries on research hold. Keep the configured 0.01 lot and maximum
  four positions unchanged. Do not enable a losing variant merely to generate
  activity or select new parameters against this reused window.
- The existing dashboard research widget still reads the 21 October report
  directory; this new dated replay is an offline artifact, not a live widget
  update.

## Launch main and dashboard

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1
```

The launcher preserves the research entry hold and avoids a duplicate main
executor. Dashboard: `http://127.0.0.1:8765/`.
