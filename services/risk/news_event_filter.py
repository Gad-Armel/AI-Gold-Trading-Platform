import json
import os
from datetime import datetime, timedelta

from config import settings


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _load_news_events():
    file_path = getattr(settings, "NEWS_EVENTS_FILE", "data/economic_events.json")

    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        events = data.get("events", [])

        if isinstance(events, list):
            return events

        return []

    except Exception:
        return []


def _parse_event_time(value):
    try:
        return datetime.strptime(value, DATETIME_FORMAT)
    except Exception:
        return None


def _is_relevant_to_symbol(event, symbol):
    currency = str(event.get("currency", "")).upper()
    symbol = str(symbol).upper()

    if currency in ["ALL", "GOLD", "XAU", "XAUUSD"]:
        return True

    if symbol == "XAUUSD" and currency == "USD":
        return True

    return False


def _is_unverified_conservative_event(event):
    """Return True for estimated windows that are not verified release dates.

    Older project versions stored these estimates as HIGH impact events.  They
    are useful as watch markers, but they must not impersonate an official
    scheduled release and stop the scalper.
    """

    title = str(event.get("title", "")).lower()
    source_detail = str(event.get("source_detail", "")).lower()
    confidence = str(event.get("calendar_confidence", "")).upper()

    return (
        "conservative watch" in title
        or source_detail.startswith("conservative_")
        or confidence in {"ESTIMATED", "UNVERIFIED"}
    )


def assess_news_event_risk(symbol=None, current_time=None, *, extra_events=None):
    """
    Blocks trading around high-impact manually listed news events.

    This does not fetch news automatically yet.
    It reads:
    data/economic_events.json
    """

    symbol = symbol or getattr(settings, "SYMBOL", "XAUUSD")
    current_time = current_time or datetime.now()

    if not getattr(settings, "ENABLE_NEWS_RISK_FILTER", True):
        return {
            "allowed": True,
            "action": "NEWS_FILTER_DISABLED",
            "message": "News risk filter is disabled.",
            "block_reasons": [],
            "active_events": [],
        }

    events = _load_news_events()
    if extra_events:
        # Optional caller-owned schedules stay in memory. Existing callers and
        # the shared economic_events.json retain their original behavior.
        events = list(events) + [event for event in extra_events if isinstance(event, dict)]

    block_before = int(getattr(settings, "NEWS_BLOCK_BEFORE_MINUTES", 30))
    block_after = int(getattr(settings, "NEWS_BLOCK_AFTER_MINUTES", 15))

    block_high = bool(getattr(settings, "BLOCK_HIGH_IMPACT_NEWS", True))
    block_medium = bool(getattr(settings, "BLOCK_MEDIUM_IMPACT_NEWS", False))

    active_events = []
    block_reasons = []

    for event in events:
        if not event.get("enabled", True):
            continue

        if not _is_relevant_to_symbol(event, symbol):
            continue

        impact = str(event.get("impact", "")).upper()
        event_time = _parse_event_time(event.get("event_time", ""))

        if event_time is None:
            continue

        window_start = event_time - timedelta(minutes=block_before)
        window_end = event_time + timedelta(minutes=block_after)

        inside_window = window_start <= current_time <= window_end

        if not inside_window:
            continue

        should_block = False
        unverified_estimate = _is_unverified_conservative_event(event)
        block_unverified = bool(
            getattr(settings, "BLOCK_UNVERIFIED_CONSERVATIVE_EVENTS", False)
        )

        if impact == "HIGH" and block_high:
            should_block = True

        if impact == "MEDIUM" and block_medium:
            should_block = True

        # Estimated fallback windows are watch-only by default. This also
        # neutralizes legacy V5.0.2 HIGH records such as the false weekly FOMC
        # entry, even when an old economic_events.json survives an upgrade.
        if unverified_estimate and not block_unverified:
            should_block = False

        event_payload = {
            "title": event.get("title", ""),
            "currency": event.get("currency", ""),
            "impact": impact,
            "event_time": event.get("event_time", ""),
            "window_start": window_start.strftime(DATETIME_FORMAT),
            "window_end": window_end.strftime(DATETIME_FORMAT),
            "verified": not unverified_estimate,
            "blocking": should_block,
            "source_detail": event.get("source_detail", ""),
        }

        active_events.append(event_payload)

        if should_block:
            block_reasons.append(
                f"Blocked by {impact} news event: {event.get('title', '')} at {event.get('event_time', '')}"
            )

    allowed = len(block_reasons) == 0

    return {
        "allowed": allowed,
        "action": "NEWS_ALLOWED" if allowed else "NEWS_BLOCKED",
        "message": "No blocking news event active." if allowed else "News risk filter blocked trading.",
        "symbol": symbol,
        "checked_at": current_time.strftime(DATETIME_FORMAT),
        "active_events": active_events,
        "block_reasons": block_reasons,
    }


def apply_news_filter_to_ai(ai_result, news_risk):
    if news_risk.get("allowed", False):
        return ai_result

    return {
        "action": "NO_TRADE",
        "can_trade": False,
        "confidence": 0.0,
        "reason": "News risk filter blocked trading.",
        "original_ai_result": ai_result,
        "news_block_reasons": news_risk.get("block_reasons", []),
    }
