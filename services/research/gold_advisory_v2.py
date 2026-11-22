from __future__ import annotations

from datetime import datetime, timezone

from models.scalping_state import ScalpingSnapshotState
from services.research.gold_advisory import build_gold_advisory


def build_gold_advisory_v2(snapshot: ScalpingSnapshotState, *, data_source: str = "Twelve Data XAU/USD OHLC") -> dict:
    """Run the advisory model on an independent API feed and mark its limitations."""
    report = build_gold_advisory(snapshot)
    m1 = snapshot.candles.get("M1") if isinstance(snapshot.candles, dict) else None
    source_bar_time = None
    source_bar_age_seconds = None
    if m1 is not None and not m1.empty and "time" in m1:
        parsed = m1.iloc[-1]["time"]
        if hasattr(parsed, "to_pydatetime"):
            parsed = parsed.to_pydatetime()
        if isinstance(parsed, datetime):
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
            source_bar_time = parsed.isoformat()
            source_bar_age_seconds = round(max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds()), 3)
    report.update({
        "advisor_name": "GOLD MARKET ADVISOR V2 - API FEED",
        "version": "2.0",
        "data_source": data_source,
        "reference_price_only": True,
        "mid": snapshot.mid,
        "source_bar_time": source_bar_time,
        "source_bar_age_seconds": source_bar_age_seconds,
    })
    for item in report["horizons"].values():
        item["reasons"].append("Independent API OHLC feed; broker spread and executable price are unavailable.")
    return report
