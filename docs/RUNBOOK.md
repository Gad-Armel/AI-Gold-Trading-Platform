# V-FINAL runbook

## A. Install

From the existing project root, copy the `vfinal/` package and the integration
patch. Install the dependencies in `requirements.txt` if missing.

## B. Free macro key

The FRED graph CSV path can work without a key for current observations. For
proper vintage/release-aware historical research, register a FRED API key and
put it in `.env` as `FRED_API_KEY=...`.

## C. Start shadow collection

Run the integration collector. It never sends an order.

```text
python integration_patch/run_vfinal_shadow_collector.py --interval 5
```

Keep it running through multiple sessions and regimes. Do not judge the model
from a single London/NY day.

## D. Tick archive

The V-FINAL labeler needs future executable bid/ask ticks. If the existing
project's tick archive can be exported to CSV, use that directly. Otherwise:

```text
python run_vfinal.py collect-ticks --symbol XAUUSD --start 2026-08-01T00:00:00Z --end 2026-08-20T23:59:59Z --output data/raw/xauusd_ticks.csv
```

## E. Build labels

```text
python run_vfinal.py build-dataset --ticks data/raw/xauusd_ticks.csv
python run_vfinal.py status
```

## F. Train

Do not train per direction/horizon until enough samples exist. The first useful
milestone is 1,000+ candidate rows per research slice; several thousand are
preferable. The code blocks promotion if the holdout is weak.

```text
python run_vfinal.py train --horizon SCALP_60S --direction BUY
python run_vfinal.py train --horizon SCALP_60S --direction SELL
```

Repeat for the horizons with enough data.

## G. Forward demo validation

Keep V6.3 as the active demo guard initially. V-FINAL should run as a shadow
filter and record its own probability/EV alongside the actual V6.3 decision.
Only after a meaningful forward sample should the V-FINAL gate be enabled.

## H. Live

There is intentionally no command here that arms live execution. Promotion is
a project-level decision after demo validation and independent review.

## First checks in VS Code PowerShell

```powershell
python run_vfinal.py env
python run_vfinal.py health
python run_vfinal.py macro
python run_vfinal.py macro-vintage --as-of 2026-08-01T00:00:00Z
```

`env` loads the existing project's `.env` automatically; no `python-dotenv` package is required.

Do not train until the dataset contains a sufficiently large number of real, point-in-time observations across multiple market regimes.
