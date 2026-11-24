from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import gold_consensus_settings as settings
from services.utils.atomic_json import atomic_write_json


def load_loss_reset() -> datetime | None:
    try:
        payload = json.loads(Path(settings.LOSS_RESET_PATH).read_text(encoding="utf-8"))
        value = datetime.fromisoformat(str(payload["reset_at"]).replace("Z", "+00:00"))
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def reset_loss_baseline(now: datetime | None = None) -> dict[str, Any]:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {"reset_at": stamp.isoformat(), "scope": "three_horizon_demo_pnl",
               "note": "MT5 history retained; only the loss-breaker baseline changed."}
    atomic_write_json(settings.LOSS_RESET_PATH, payload, indent=2)
    return {"success": True, **payload}
