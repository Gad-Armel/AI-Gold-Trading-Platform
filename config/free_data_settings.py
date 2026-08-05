"""Optional free/official context providers for V6.

These feeds are slow macro/news context only. They never replace MT5 executable
quotes, spreads, fills, or broker account state. A local ``.env`` file is read
without an extra dependency; existing process environment variables always win.
"""
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

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
BEA_API_KEY = os.getenv("BEA_API_KEY", "").strip()
BLS_API_KEY = os.getenv("BLS_API_KEY", "").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
HTTP_TIMEOUT_SECONDS = float(os.getenv("FREE_DATA_HTTP_TIMEOUT_SECONDS", "8"))
CACHE_PATH = os.getenv("FREE_DATA_CACHE_PATH", "data/context/free_macro_context.json")
