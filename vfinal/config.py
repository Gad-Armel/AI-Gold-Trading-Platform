from __future__ import annotations

import os
from pathlib import Path

# V-FINAL is designed to be copied into the existing project root.  Load the
# project's .env ourselves so no extra dotenv dependency is required.
ROOT = Path(__file__).resolve().parents[1]


def _find_project_root(start: Path) -> Path:
    explicit = os.getenv("VFINAL_PROJECT_ROOT")
    if explicit:
        return Path(explicit).resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".env").exists() or (candidate / "run_gold_consensus_bot.py").exists():
            return candidate
    return start


PROJECT_ROOT = _find_project_root(ROOT)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # Do not overwrite a process environment variable.
        os.environ.setdefault(key, value)

# Search the V-FINAL root first, then the containing project root. This lets
# the package work both standalone and when copied into the user's existing repo.
_load_env_file(ROOT / ".env")
if PROJECT_ROOT != ROOT:
    _load_env_file(PROJECT_ROOT / ".env")

DATA = ROOT / "data"
RAW = DATA / "raw"
SNAPSHOTS = DATA / "snapshots"
LABELS = DATA / "labels"
MODELS = DATA / "models"
REPORTS = DATA / "reports"
CACHE = DATA / "cache"

SYMBOL = os.getenv("XAUUSD_SYMBOL", "XAUUSD")
TIMEZONE = "UTC"
SNAPSHOT_INTERVAL_SECONDS = float(os.getenv("VFINAL_SNAPSHOT_INTERVAL_SECONDS", "5"))

HORIZONS_SECONDS = {
    "SCALP_15S": 15,
    "SCALP_30S": 30,
    "SCALP_60S": 60,
    "INTRADAY_120S": 120,
    "INTRADAY_300S": 300,
    "INTRADAY_900S": 900,
    "SWING_3600S": 3600,
    "SWING_14400S": 14400,
}

TARGET_ATR = float(os.getenv("VFINAL_TARGET_ATR", "0.80"))
STOP_ATR = float(os.getenv("VFINAL_STOP_ATR", "0.65"))
MIN_TARGET_USD = float(os.getenv("VFINAL_MIN_TARGET_USD", "0.80"))
MIN_STOP_USD = float(os.getenv("VFINAL_MIN_STOP_USD", "0.70"))
COST_SPREAD_MULTIPLE = float(os.getenv("VFINAL_COST_SPREAD_MULTIPLE", "1.25"))
SLIPPAGE_USD = float(os.getenv("VFINAL_SLIPPAGE_USD", "0.03"))

MIN_ROWS_TO_TRAIN = int(os.getenv("VFINAL_MIN_ROWS_TO_TRAIN", "300"))
PREFERRED_ROWS = int(os.getenv("VFINAL_PREFERRED_ROWS", "1000"))
MIN_FOLDS = int(os.getenv("VFINAL_MIN_FOLDS", "5"))
MIN_TRAIN_ROWS_PER_FOLD = int(os.getenv("VFINAL_MIN_TRAIN_ROWS_PER_FOLD", "100"))
HOLDOUT_FRACTION = float(os.getenv("VFINAL_HOLDOUT_FRACTION", "0.20"))
CALIBRATION_FRACTION = float(os.getenv("VFINAL_CALIBRATION_FRACTION", "0.15"))
PURGE_SECONDS = int(os.getenv("VFINAL_PURGE_SECONDS", "900"))

MIN_PROBABILITY = float(os.getenv("VFINAL_MIN_PROBABILITY", "0.55"))
MIN_EV_USD = float(os.getenv("VFINAL_MIN_EV_USD", "0.02"))
MIN_HOLDOUT_TRADES = int(os.getenv("VFINAL_MIN_HOLDOUT_TRADES", "20"))
MIN_HOLDOUT_WIN_RATE = float(os.getenv("VFINAL_MIN_HOLDOUT_WIN_RATE", "0.52"))
MIN_HOLDOUT_PF = float(os.getenv("VFINAL_MIN_HOLDOUT_PF", "1.05"))
MAX_HOLDOUT_BRIER = float(os.getenv("VFINAL_MAX_HOLDOUT_BRIER", "0.25"))
MAX_HOLDOUT_ECE = float(os.getenv("VFINAL_MAX_HOLDOUT_ECE", "0.12"))
MAX_PSI_BLOCK = float(os.getenv("VFINAL_MAX_PSI_BLOCK", "0.30"))

# Existing project's providers are optional confirmations. MT5 remains the
# executable source of truth.
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "").strip()
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice").strip() or "practice"
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
BEA_API_KEY = os.getenv("BEA_API_KEY", "").strip()
BLS_API_KEY = os.getenv("BLS_API_KEY", "").strip()

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
FRED_TIMEOUT = float(os.getenv("FRED_TIMEOUT", os.getenv("FREE_DATA_HTTP_TIMEOUT_SECONDS", "10")))
FRED_BASE_URL = "https://api.stlouisfed.org/fred"
FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
ALFRED_GRAPH_URL = "https://api.stlouisfed.org/fred/series/observations"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CFTC_COT_URL = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"

FRED_SERIES = {
    "us10y": "DGS10",
    "us10y_real": "DFII10",
    "us2y": "DGS2",
    "usd_broad": "DTWEXBGS",
    "fed_funds": "DFF",
    "vix": "VIXCLS",
    "cpi": "CPIAUCSL",
    "pce": "PCEPI",
    "unemployment": "UNRATE",
    "payrolls": "PAYEMS",
}

BLS_SERIES = {
    "cpi_all_items": "CUUR0000SA0",
    "unemployment": "LNS14000000",
    "total_nonfarm": "CES0000000001",
}

CFTC_GOLD_KEYWORDS = ("GOLD", "COMEX GOLD")


def env_status() -> dict[str, object]:
    return {
        "project_root": str(PROJECT_ROOT),
        "env_file_found": (PROJECT_ROOT / ".env").exists() or (ROOT / ".env").exists(),
        "fred": bool(FRED_API_KEY),
        "bls": bool(BLS_API_KEY),
        "bea": bool(BEA_API_KEY),
        "oanda": bool(OANDA_API_TOKEN),
        "twelve_data": bool(TWELVE_DATA_API_KEY),
        "alpha_vantage": bool(ALPHA_VANTAGE_API_KEY),
        "cftc": True,
        "mt5": True,
    }


def ensure_dirs() -> None:
    for path in (RAW, SNAPSHOTS, LABELS, MODELS, REPORTS, CACHE):
        path.mkdir(parents=True, exist_ok=True)

# Training-vs-execution quality separation. Raw history is retained; execution is stricter.
TRAINING_MAX_SPREAD_USD = float(os.getenv('VFINAL_TRAINING_MAX_SPREAD_USD','5.0'))
EXECUTION_MAX_SPREAD_USD = float(os.getenv('VFINAL_EXECUTION_MAX_SPREAD_USD','0.38'))
EXECUTION_MIN_TICK_QUALITY = float(os.getenv('VFINAL_EXECUTION_MIN_TICK_QUALITY','0.70'))
EXECUTION_MAX_GAP_MS = float(os.getenv('VFINAL_EXECUTION_MAX_GAP_MS','5000'))
