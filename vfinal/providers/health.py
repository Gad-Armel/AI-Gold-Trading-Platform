from __future__ import annotations

from ..config import env_status
from .bls import health_check as bls_health
from .fred import build_current_context


def run_health_checks() -> dict:
    result = {"environment": env_status(), "providers": {}}
    try:
        result["providers"]["fred"] = {"available": bool(build_current_context().get("available"))}
    except Exception as exc:
        result["providers"]["fred"] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        result["providers"]["bls"] = bls_health()
    except Exception as exc:
        result["providers"]["bls"] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    return result
