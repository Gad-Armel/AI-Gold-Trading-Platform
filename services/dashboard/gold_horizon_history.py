from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import gold_consensus_settings as settings
from services.utils.atomic_json import atomic_write_json


def load_history_resets() -> dict[str, str]:
    path = Path(settings.HISTORY_RESET_PATH)
    try:
        import json
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {name: str(payload.get(name, "")) for name in settings.HORIZON_LANES}
    except (OSError, ValueError, TypeError):
        return {name: "" for name in settings.HORIZON_LANES}


def reset_history(horizon: str, now: datetime | None = None) -> dict[str, Any]:
    horizon = str(horizon).upper()
    if horizon not in settings.HORIZON_LANES:
        raise ValueError("Unknown horizon")
    payload = load_history_resets()
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    payload[horizon] = stamp
    atomic_write_json(settings.HISTORY_RESET_PATH, payload, indent=2)
    return {"success": True, "horizon": horizon, "reset_at": stamp}


def parsed_reset(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
