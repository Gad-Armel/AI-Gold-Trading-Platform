# V-FINAL controlled demo

The system has two modes:

1. **Bootstrap demo**: starts today without an approved ML artifact. It uses the live MT5 feed plus deterministic multi-timeframe/microstructure consensus, with strict spread/quality/position/risk limits. It is explicitly marked `bootstrap_mode=true` and `ml_model_approved=false` in the dashboard.
2. **ML mode**: after enough real chronological observations exist, `python run_vfinal.py train` can create an artifact. The existing approved-model gate remains conservative; no bootstrap trade is mislabeled as an ML-approved trade.

## Start the unified dashboard

```powershell
python -B run_gold_unified_dashboard.py
```
Open `http://127.0.0.1:8777/`. This is the single supported trading
dashboard and includes the V-FINAL report tab.

## Start controlled MT5 demo

The runner refuses a REAL account. It uses at most 0.01 lot, one position, a spread ceiling, a maximum holding time, and a consecutive-loss circuit breaker.

```powershell
python run_vfinal_demo.py --interval 2
```

Stop with `Ctrl+C`.

**Important:** keep the MT5 terminal connected to the intended demo account and do not run this against a real account. The runner itself checks the MT5 account trade mode before entering its loop.

## Collect multiple days

```powershell
python run_vfinal.py collect-range --symbol XAUUSD --start 2026-08-01T00:00:00Z --end 2026-08-20T00:00:00Z --days 19
```

Raw data is retained. Training eligibility and execution eligibility are separate: extreme spreads/gaps can remain useful as historical regime information while being blocked from new entries.
