"""Free/official context provider configuration for XAUUSD research."""

from __future__ import annotations

import os
from pathlib import Path


def _load_local_env() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / ".env"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

# Optional paid/secondary providers remain available for comparison.
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "").strip()
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice").strip().lower()
BEA_API_KEY = os.getenv("BEA_API_KEY", "").strip()
BLS_API_KEY = os.getenv("BLS_API_KEY", "").strip()

# Fast official-release monitor used only by the display-only Economic Advisor
# V6.  Census and Federal Reserve RSS supply publication timestamps.  BEA's
# official API is polled conservatively and emits a release only after the
# running process observes a new period or a changed value.  No headline alone
# receives directional confidence.
OFFICIAL_RELEASE_MONITOR_ENABLED = (
    os.getenv("OFFICIAL_RELEASE_MONITOR_ENABLED", "1").strip().lower()
    not in {"0", "false", "no"}
)
OFFICIAL_RELEASE_REFRESH_SECONDS = float(
    os.getenv("OFFICIAL_RELEASE_REFRESH_SECONDS", "60")
)
OFFICIAL_RELEASE_CACHE_PATH = os.getenv(
    "OFFICIAL_RELEASE_CACHE_PATH",
    "data/context/official_release_monitor.json",
)
CENSUS_ECONOMIC_RSS_URL = os.getenv(
    "CENSUS_ECONOMIC_RSS_URL",
    "https://www.census.gov/economic-indicators/indicator.xml",
).strip()
FED_MONETARY_RSS_URL = os.getenv(
    "FED_MONETARY_RSS_URL",
    "https://www.federalreserve.gov/feeds/press_monetary.xml",
).strip()

# Official/free macro context.  A configured key uses the faster official
# observations API; without one, the collector falls back to FRED graph CSV.
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
FRED_ENABLED = os.getenv("FRED_ENABLED", "1").strip().lower() not in {"0", "false", "no"}

HTTP_TIMEOUT_SECONDS = float(os.getenv("FREE_DATA_HTTP_TIMEOUT_SECONDS", "8"))
FREE_MACRO_REFRESH_SECONDS = float(os.getenv("FREE_MACRO_REFRESH_SECONDS", "1800"))
CACHE_PATH = os.getenv(
    "FREE_DATA_CACHE_PATH",
    "data/context/free_macro_context.json",
)
WORLD_BANK_GEP_ENABLED = (
    os.getenv("WORLD_BANK_GEP_ENABLED", "1").strip().lower()
    not in {"0", "false", "no"}
)

# Official institutional gold context used by Economic Advisor V6.  CFTC's
# public API works without a token at lower rate limits.  Goldhub is queried
# only a few times per day and cached locally.
INSTITUTIONAL_AUTO_REFRESH_ENABLED = (
    os.getenv("INSTITUTIONAL_AUTO_REFRESH_ENABLED", "1").strip().lower()
    not in {"0", "false", "no"}
)
INSTITUTIONAL_REFRESH_SECONDS = float(
    os.getenv("INSTITUTIONAL_REFRESH_SECONDS", "21600")
)
INSTITUTIONAL_CACHE_PATH = os.getenv(
    "INSTITUTIONAL_CACHE_PATH", "data/context/gold_institutional_context.json",
)
CFTC_SODA_APP_TOKEN = os.getenv("CFTC_SODA_APP_TOKEN", "").strip()

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
    "global_policy_uncertainty": "GEPUCURRENT",
    "us_policy_uncertainty": "USEPUINDXD",
    "financial_stress_stl": "STLFSI4",
    "financial_conditions_chicago": "NFCI",
    "inflation_expectation_10y": "T10YIE",
    "recession_indicator": "SAHMREALTIME",
}
