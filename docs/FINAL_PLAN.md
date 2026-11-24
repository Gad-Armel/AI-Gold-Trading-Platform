# V-FINAL completion checklist

## Completed in this package

- Canonical point-in-time snapshot schema.
- Rich multi-timeframe candle features.
- Tick/microstructure features.
- Verified structure/context feature ingestion.
- News and macro feature ingestion.
- FRED collector with optional API/vintage capability.
- BLS health adapter.
- CFTC normalization adapter.
- Triple-barrier, executable-quote-aware labels.
- Cost-aware outcome/PnL labels.
- Chronological walk-forward model suite.
- Chronological probability calibration.
- Untouched holdout gate.
- Expected-value decision gate.
- No-trade default without an approved model.
- CLI and configuration.
- Source links.

## Existing V6.3 components to retain

- Existing shadow lanes and conservative fills.
- Existing market structure engine.
- Existing news hard blocks.
- Existing account/risk protections.
- Existing drift/PSI monitoring.
- Existing champion/challenger artifacts, until the V-FINAL artifact proves superior.

## Integration still requires the user's actual live runner

The exact final wiring point is the existing runner's candidate creation/shadow
recording path. This package deliberately does not rewrite the order-sending
code blindly because that would risk changing MT5 execution semantics without
seeing every execution/risk module.

The safe migration is:

1. Record V-FINAL feature rows in parallel with V6.3.
2. Generate labels after future data arrives.
3. Train V-FINAL in research-only mode.
4. Compare V-FINAL probability/EV against V6.3 on the same untouched episodes.
5. Enable V-FINAL as a filter only after the holdout and forward-demo gates pass.
6. Keep V6.3 as a fallback until V-FINAL has stable forward evidence.
