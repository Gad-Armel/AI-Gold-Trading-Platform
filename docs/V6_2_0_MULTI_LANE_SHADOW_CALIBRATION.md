# V6.2 Multi-Lane Shadow Calibration

## Problem addressed

A strict strategy can be safe yet impossible to validate when it opens almost no simulated trades. Relaxing the production gate directly would create a new unproven strategy. V6.2 separates evidence collection from executable permission.

## Lane design

### STRICT

Exact V6 executable hypothesis. Only this lane is demo eligible and only its history is used by the approval system.

### BALANCED

Research-only. Requires matching 2-of-3 structural consensus, safe location room, positive aggregate tape and at least one aligned micro window. It broadens score, VWAP, relative-volume and persistence limits without changing broker safety.

### EXPLORATORY

Research-only. Requires positive aggregate tape and at least one structural family in the trade direction, while rejecting any opposite 2-of-3 consensus. Micro-window agreement is recorded but not mandatory. It estimates whether the strict window rule adds or destroys edge.

## Isolation guarantees

- Each lane has an independent simulated book.
- The demo application function raises an exception for any non-STRICT lane.
- Walk-forward approval reads only the STRICT history path.
- Real-account execution remains disabled.

## Feed pause

Quotes older than three seconds cause an early return before signal, agent, structure-map and shadow-position processing. The loop sleeps for two seconds and throttles pause messages to one every 30 seconds.

## Telemetry

A sampled JSONL record stores each lane's score, margin, spread/ATR, VWAP, volume, microstructure, persistence, structure and failed checks. This supports later calibration without filling disk with every polling loop.
