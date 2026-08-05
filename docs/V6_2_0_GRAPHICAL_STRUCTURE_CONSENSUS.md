# V6.2 Graphical Structure Consensus

## Purpose

V6.2 adds an objective multi-timeframe market-structure layer before a scalp can become executable. It does not use screenshots as an opaque image-classification shortcut. It converts closed M15, H1 and H4 candles into reproducible numerical evidence and optionally renders an annotated market map for human audit.

## Three independent families

### 1. Higher-timeframe trend

- H4 weight: 45%
- H1 weight: 35%
- M15 weight: 20%
- Evidence: EMA20/EMA50 separation, EMA slope, and higher-high/higher-low or lower-high/lower-low sequences.

### 2. Support, resistance and liquidity behavior

- Confirmed swing highs/lows are clustered into price zones.
- H4 and H1 touches receive more weight than M15 touches.
- Old levels decay with time.
- The module detects rejection candles, breaks of structure and simple liquidity sweeps.
- A trade must have enough room to the next opposing zone for the target plus current spread.

### 3. Objective order blocks

An order block is accepted only when:

1. the origin is the last opposite candle;
2. the next three closed candles displace at least 1.10 ATR;
3. that displacement breaks the prior seven-candle range;
4. later closes do not invalidate the distal boundary;
5. the zone has not already been touched more than three times.

This is an auditable proxy, not proof of hidden institutional orders.

## Consensus rule

At least two of the three families must agree with the proposed BUY or SELL direction. The trade is also rejected when the next opposing structure is too close or an opposing order block is immediately in the way.

## Graphical audit

When enabled, the system writes annotated PNG maps to:

```text
logs/v6_market_maps/YYYY-MM-DD
```

The map contains recent candles, clustered support/resistance, active order-block zones, the current price and the final 2-of-3 consensus. Rendering is throttled to protect cycle latency and is forced for important structural candidates.

## Learning and adaptation

The structural features are written into every V6 shadow candidate and closed-trade record. Walk-forward validation therefore learns which combinations are profitable without allowing the bot to rewrite live parameters automatically. Automatic parameter mutation is intentionally disabled because the uploaded history contained only 59 matched trades and one dominant directional regime.

## Safety

- Shadow mode has no reachable MT5 `order_send` path.
- Controlled demo requires a valid, unexpired approval artifact for the exact settings hash.
- Shadow and approved demo call the same V6 candidate gate and the same structure module.
- Three consecutive controlled-demo losses revoke approval and force a return to shadow calibration.
- Real-account execution remains disabled.
