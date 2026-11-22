# Separate inverse demo executor

The user explicitly selected the current demo account, with FOUR positions
total across both executors. This requires an MT5 hedging account, not netting.
No real-money mode exists. Advisor1 is not modified.

## Behavior

- Watches confirmed open XAUUSD positions owned by the main SCALP magic 631011.
- Sends one 0.01-lot opposite order for each newly discovered main position,
  tagged `INV:<source position identifier>`, under independent magic 631021.
- Starts with a baseline: existing main positions are not backfilled. Sources
  older than five seconds are skipped, not chased.
- Stores a durable intent BEFORE submission. A restart, timeout, accepted
  pending order or early inverse SL never causes a duplicate or re-entry for
  the same source. Failed/skipped source links are also not automatically retried.
- Source disappearance from a successful same-account position snapshot
  requests closure of its linked inverse. A failed position query never means
  the source closed. Only the inverse ticket is closed, never the main ticket.
- Polls every 250 ms plus broker/runtime work; simultaneous fills/closes are
  not guaranteed. The main can close during the mirror's submission race;
  the next successful poll requests inverse closure.
- Each inverse has a mandatory broker SL and TP=0. Its initial stop distance
  derives from the source's current entry-to-SL distance, independently applied
  to its own execution price and rounded to the broker tick grid. A minimum
  stop-distance/risk violation is skipped; no naked-stop fallback exists.
- Planned gross stop risk is capped at 5 USD, not a guaranteed all-in loss cap.
  Commission, slippage and stop gaps can exceed the estimate.

## Shared capacity

With `PAIRING_ENABLED=True` in `config/gold_inverse_settings.py`, the main
reserves two of the four total slots for mirrors and admits at most two
controlled main positions. The reservation is intentionally independent of
heartbeat file availability: a transient file read failure cannot release
reserved slots and race an inverse entry. It remains reserved when the inverse
is stopped. Both sides check pending orders and total capacity.
There may be fewer than two complete pairs: quote quality, margin, unsupported
SLs, age limits or uncertain execution can prevent a mirror. No acceptance
quota overrides safety checks.

The main recognizes only the explicitly authorized companion magic during
its live heartbeat. A stopped/stale companion with leftover positions blocks
new main entries as external exposure until resolved; main exits still run.
To retire pairing and restore four main-only slots, first stop the inverse,
verify no inverse positions or pending/uncertain orders remain, then set
`PAIRING_ENABLED=False` and restart the main. Never release pairing slots
while the inverse executor can still open orders.
The independent inverse state is locked to account login/server/demo mode;
switching accounts never permits it to trade the new account. Corrupt or
mismatched state fails closed rather than resetting and duplicating trades.

## Why inverse P/L is not the negative of main P/L

Both sides pay spread and possibly fees/slippage. Entry and exit detection
delays differ. A protective inverse SL can close earlier than the main.
Running both on the same account mostly hedges directional exposure while
adding costs; it is an experiment, not a profit recovery mechanism.

## Launch

Main must be the updated companion-capable version. These scripts refuse a
second instance rather than start duplicate executors.

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1 -ScalpTimeframe AUTO
```

In another PowerShell window:

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_inverse.ps1
```

Inverse status: `data/runtime/gold_inverse_status.json`.
The main dashboard at `http://127.0.0.1:8765/` displays both bots, inverse
positions linked to main IDs, separate closed history and P/L, and a matched
experiment total. Main session P/L and inverse seven-day broker history use
different baselines and are not directly added. Matched-pair totals exclude
unmirrored main trades. Stale or mismatched-account inverse data is not shown
as live. Reporting refreshes from broker history approximately every five
seconds; this UI change does not authorize orders or change exit rules.
Durable links: `data/runtime/gold_inverse_state.json`.
Submission journal: `data/demo/gold_inverse_journal.jsonl` (requests/results,
not a replacement for reconciled MT5 deal history).

## Stop only inverse

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\stop_gold_inverse.ps1
```

It requests closure of inverse positions only and then stops. The stop flag
persists. Inspect MT5 and status before removing exactly
`data/runtime/stop_gold_inverse.flag` for a later restart. Ctrl+C also attempts
inverse cleanup. An ambiguous close is never blindly resent: unresolved
positions retain broker SLs and require inspection/manual intervention.
Stop processing is bounded to 30 seconds before reporting unresolved exposure.

## Validation

Main strategy close decisions now publish an account-bound source-position
notification before sending the main close request. The inverse worker closes
the linked position on its next polling cycle (nominally 250 ms), without waiting
for the main fill. Independent MT5 requests cannot guarantee simultaneous fills.
If the main request fails, its inverse may already have closed. Broker SL/manual
closures still use confirmed source absence as the fallback trigger.

The dashboard shows separate main/inverse profit panels and closed-trade
histories. Gains are green and losses red. `Reset BOTH bots: P/L + history`
sets one account-bound display baseline for both panels and linked-pair totals.
It does not delete MT5 history, close positions, or reset execution risk limits.
With open trades, aggregate floating P/L shows the change since reset; individual
position cards retain their actual broker P/L. Before resetting, history covers
the most recent seven days. Reporting refreshes approximately every five seconds.

148 targeted tests pass, including opposite directions, linked closure,
no startup backfill, restart/timeout deduplication, early SL no re-entry,
missing position snapshots, account changes, planned risk/capacity/pending
guards, independent stopping and main companion slot reservation.
Pending inverse orders and unresolved submission intents prevent a false
flat/shutdown confirmation even when no inverse position is visible yet.
This is behavior validation, not a profitable forward-trading result.

First broker-reconciled pair on 23 October: main BUY net -1.74 USD, inverse
SELL net +0.87 USD, combined -0.87 USD. Both used 0.01 lot and broker SLs.
Inverse entry followed the main fill by 226 ms; its source-linked exit
followed the main exit by 245 ms in deal timestamps. See
`data/research/inverse_demo_20261023/first_pair.json`. One pair validates this
observed execution path only, not an expected return or future latency bound.

Official MT5 semantics checked:
- https://www.mql5.com/en/docs/constants/environment_state/accountinformation
- https://www.mql5.com/en/docs/trading/ordersend
