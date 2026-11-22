# Explicit S1 demo trial

The current execution strategy is same-direction completed midpoint candles,
not a trained probability forecast: three candles for the initial signal,
staged confirmation for additions, and a heuristic body/range evidence score.
Structural stops use the fast candle extrema plus a spread/M1 ATR buffer.
Consequently, reducing the entry candle period does not necessarily reduce
the loss per stop. Dynamic exits, persistence and spacing remain unchanged.

An explicit `--scalp-timeframe S1` option now supports completed one-second
candles. AUTO still selects only S5/S15/S30; S1 is not automatically promoted.
This is an experimental demo execution option, not validated profitability.
No cost veto, session loss stop, or Advisor1 settings were changed.

Preserved checks: demo account, 0.01 lot, four-position cap, broker SLs,
entry persistence/spacing, six-second quote coverage, spread expansion,
same-direction profitable additions, and account-bound cost inputs.
S1 requires real quotes throughout each second (maximum gap one third of a
second); missing coverage is rejected, never fabricated. It can therefore
trade less frequently on a sparse feed. One-second candles are not a promise
of one-second execution or an institutional high-frequency system.

The main was restarted explicitly in S1 on 22 October. A SELL was opened by
the old worker between the initial flat check and restart preflight; the
restart verified its broker SL and the new worker recovered that position.
The status subsequently reported `S1_PRIMARY` and entry timeframe `S1`.
Existing positions were not manually closed. Advisor1's 18 protected hashes
matched their baseline before restart.

At startup the dashboard's session realized P/L was -25.56 USD. That includes
earlier trades and is not an S1 result. Faster candles do not resolve this
loss history or demonstrate positive expectancy. Compare subsequent fills,
net P/L, stop distances, and slippage separately before drawing conclusions.

Start when stopped:

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1 -ScalpTimeframe S1
```

The launcher does not change the timeframe of an already running instance.
Reverting a running main to AUTO uses the reviewed restart helper with
`-ScalpTimeframe AUTO -AllowProvisionalCosts`.
