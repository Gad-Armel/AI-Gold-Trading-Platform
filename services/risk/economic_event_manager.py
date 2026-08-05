import json
import os
from datetime import datetime

from config import settings


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _get_events_file_path():
    return getattr(settings, "NEWS_EVENTS_FILE", "data/economic_events.json")


def _ensure_events_file():
    file_path = _get_events_file_path()
    folder = os.path.dirname(file_path)

    if folder:
        os.makedirs(folder, exist_ok=True)

    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump({"events": []}, file, indent=4)

    return file_path


def load_events():
    file_path = _ensure_events_file()

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        events = data.get("events", [])

        if isinstance(events, list):
            return events

        return []

    except Exception:
        return []


def save_events(events):
    file_path = _ensure_events_file()

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump({"events": events}, file, indent=4)

    return file_path


def add_event(title, currency, impact, event_time, enabled=True):
    """
    Adds one economic event.

    event_time format:
    YYYY-MM-DD HH:MM:SS
    """

    try:
        datetime.strptime(event_time, DATETIME_FORMAT)
    except Exception:
        return {
            "success": False,
            "message": f"Invalid event_time format. Use {DATETIME_FORMAT}",
            "file_path": _get_events_file_path(),
        }

    impact = str(impact).upper()
    currency = str(currency).upper()

    if impact not in ["LOW", "MEDIUM", "HIGH"]:
        return {
            "success": False,
            "message": "Impact must be LOW, MEDIUM, or HIGH.",
            "file_path": _get_events_file_path(),
        }

    events = load_events()

    event = {
        "title": title,
        "currency": currency,
        "impact": impact,
        "event_time": event_time,
        "enabled": bool(enabled),
    }

    events.append(event)
    file_path = save_events(events)

    return {
        "success": True,
        "message": "Economic event added.",
        "event": event,
        "file_path": file_path,
        "event_count": len(events),
    }


def clear_events():
    file_path = save_events([])

    return {
        "success": True,
        "message": "All economic events cleared.",
        "file_path": file_path,
        "event_count": 0,
    }


def list_events():
    events = load_events()

    return {
        "success": True,
        "file_path": _get_events_file_path(),
        "event_count": len(events),
        "events": events,
    }