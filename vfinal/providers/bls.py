from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from ..config import BLS_API_URL


def fetch_series(series_ids: list[str], start_year: int, end_year: int) -> dict:
    payload = json.dumps({"seriesid": series_ids, "startyear": str(start_year), "endyear": str(end_year)}).encode()
    request = Request(BLS_API_URL, data=payload, headers={"Content-Type": "application/json", "User-Agent": "XAUUSD-VFINAL/1.0"})
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def health_check() -> dict:
    year = datetime.now(timezone.utc).year
    try:
        result = fetch_series(["CUUR0000SA0"], year - 1, year)
        return {"available": result.get("status") == "REQUEST_SUCCEEDED", "status": result.get("status")}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
