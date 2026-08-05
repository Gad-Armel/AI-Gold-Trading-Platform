from __future__ import annotations

from typing import Any

from config import scalping_settings


def research_outcome_eligible(row: dict[str, Any]) -> bool:
    """Return whether a closed shadow row represents monitored research."""
    explicit = row.get("research_eligible")
    if explicit is not None:
        return bool(explicit)
    if str(row.get("close_reason", "")).upper() == "UNMONITORED_SESSION_GAP":
        return False
    try:
        ignored = float(row.get("feed_pause_seconds_ignored", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    maximum = float(scalping_settings.SCALPING_V6_MAX_RESEARCH_MONITORING_GAP_SECONDS)
    return ignored <= maximum


def research_exclusion_reason(row: dict[str, Any]) -> str:
    if research_outcome_eligible(row):
        return ""
    reason = str(row.get("research_exclusion_reason", "")).strip()
    return reason or "Position crossed the outcome barrier after an unmonitored process gap."
