# Entry confirmations and opposite setups

Main fast demo mode no longer uses neutral entry confirmation as an adaptive
neutral-thesis exit. Protective stops, profit locks, flow, structural, news and
risk exits remain independent. An opposite setup must pass the existing fast
entry confirmation gate and remain valid for one second on healthy data before
requesting a full lane close. Failed confirmation resets this timer.

No opposite position is opened inside the close path. The next normal entry
cycle rechecks broker positions and all entry controls, including post-exit
analysis, trade/loss cooldowns, capacity, freshness, costs and dollar risk.
This preserves close-before-open behavior and does not guarantee a reversal fill
or institutional HFT latency. Existing five-second post-exit pause remains.

Validation: 88 focused tests passed plus runner syntax check. Tests cover
opposite persistence, reset on failed cost/data checks, neutral/same-direction
rejection and exit-signal isolation. Safe restart verified one broker-protected
main position before replacing the worker on the explicitly approved demo.

Self-check: correctness supported by unit boundaries, risk controls retained,
main fast mode scope only, new fast_reversal telemetry, no profitability claim.

Follow-up correction: existing exposure pinned the main selector to its entry
period, unintentionally hiding faster opposite setups. Reversal scanning now
independently checks S5, S15 and S30 with a required opposite direction, full
entry confirmation and stop-risk checks. Same-direction candidates cannot mask
the opposite candidate. Additions remain pinned to the original timeframe.
The full candidate scan is exposed under fast_reversal.selection. Ninety focused
tests and runner syntax checks passed; safely reloaded with one protected
position. This fixes scanning scope, not proven live reversal profitability.
