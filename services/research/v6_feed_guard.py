from __future__ import annotations

from typing import Any

from config import scalping_settings


def evaluate_v6_feed_guard(snapshot: Any) -> dict[str, Any]:
    try:
        quote_age = float(getattr(snapshot, "quote_age_seconds", 0.0) or 0.0)
    except (TypeError, ValueError):
        quote_age = 999.0
    limit = float(scalping_settings.SCALPING_V6_FEED_PAUSE_QUOTE_AGE_SECONDS)
    fresh = quote_age <= limit
    return {
        "fresh": fresh,
        "paused": not fresh,
        "quote_age_seconds": round(quote_age, 4),
        "maximum_quote_age_seconds": limit,
        "reason": "MT5 quote fresh." if fresh else f"MT5 quote stale for {quote_age:.1f}s > {limit:.1f}s.",
    }
