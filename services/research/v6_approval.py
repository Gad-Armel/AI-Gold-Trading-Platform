from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import scalping_settings
from services.utils.atomic_json import atomic_write_json


def v6_settings_payload() -> dict[str, Any]:
    names = set(scalping_settings.SCALPING_V6_SETTINGS_HASH_FIELDS)
    names.update(
        name for name in dir(scalping_settings)
        if name.startswith("SCALPING_V63_")
    )
    return {name: getattr(scalping_settings, name) for name in sorted(names)}


def v6_settings_hash() -> str:
    raw = json.dumps(v6_settings_payload(), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def approval_path() -> Path:
    return Path(scalping_settings.SCALPING_V6_DEMO_APPROVAL_PATH)


def load_v6_approval(*, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    path = approval_path()
    if not path.exists():
        return {"approved": False, "reason": "No V6 demo approval artifact exists.", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"approved": False, "reason": f"V6 approval is unreadable: {exc}", "path": str(path)}
    expected_hash = v6_settings_hash()
    expires = data.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
    except ValueError:
        expires_at = datetime.min.replace(tzinfo=timezone.utc)
    checks = {
        "approval_flag": bool(data.get("approved", False)),
        "strategy_id": data.get("strategy_id") == scalping_settings.SCALPING_STRATEGY_ID,
        "settings_hash": data.get("settings_hash") == expected_hash,
        "not_expired": now <= expires_at,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        **data,
        "approved": not failed,
        "checks": checks,
        "failed_checks": failed,
        "reason": "V6 demo approval is valid." if not failed else "V6 demo approval failed: " + ", ".join(failed) + ".",
        "path": str(path),
        "expected_settings_hash": expected_hash,
    }


def write_v6_approval(metrics: dict[str, Any], *, approved: bool) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=int(scalping_settings.SCALPING_V6_PROMOTION_APPROVAL_VALID_DAYS))
    payload = {
        "approved": bool(approved),
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "settings_hash": v6_settings_hash(),
        "settings": v6_settings_payload(),
        "generated_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "metrics": metrics,
    }
    path = approval_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(str(path), payload, indent=2)


def revoke_v6_approval(reason: str = "Manual or safety revocation") -> str:
    return write_v6_approval({"revocation_reason": reason}, approved=False)
