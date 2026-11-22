from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from config import scalping_settings


@dataclass(frozen=True)
class DemoSessionState:
    armed: bool = False
    account_login: int | None = None
    account_server: str = ""
    account_trade_mode: int | None = None
    armed_at_utc: str = ""


_LOCK = RLock()
_STATE = DemoSessionState()


def get_demo_session_state() -> dict[str, Any]:
    with _LOCK:
        return asdict(_STATE)


def arm_demo_session(token: str, account: Any, mt5_module: Any) -> dict[str, Any]:
    global _STATE
    required = str(scalping_settings.SCALPING_REQUIRED_DEMO_CONFIRMATION or "")
    if not required or str(token or "") != required:
        return {"armed": False, "reason": "Exact demo-risk confirmation is invalid."}
    if account is None:
        return {"armed": False, "reason": "MT5 account information is unavailable."}
    demo_mode = int(getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", 0))
    actual_mode = int(getattr(account, "trade_mode", -1))
    if actual_mode != demo_mode:
        return {
            "armed": False,
            "reason": f"Connected account is not DEMO (trade_mode={actual_mode}).",
        }
    with _LOCK:
        _STATE = DemoSessionState(
            armed=True,
            account_login=int(getattr(account, "login", 0) or 0),
            account_server=str(getattr(account, "server", "") or ""),
            account_trade_mode=actual_mode,
            armed_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        return asdict(_STATE)


def disarm_demo_session() -> None:
    global _STATE
    with _LOCK:
        _STATE = DemoSessionState()


def validate_demo_session_identity(account: Any, mt5_module: Any) -> tuple[bool, str]:
    state = get_demo_session_state()
    if account is None:
        return False, "MT5 account information is unavailable."
    demo_mode = int(getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", 0))
    actual_mode = int(getattr(account, "trade_mode", -1))
    if actual_mode != demo_mode:
        return False, f"Connected account is not an MT5 demo account (trade_mode={actual_mode})."
    if not bool(state.get("armed", False)):
        return False, "The process-local demo session is not armed."
    if bool(getattr(scalping_settings, "SCALPING_DEMO_ACCOUNT_IDENTITY_LOCK", True)):
        actual_login = int(getattr(account, "login", 0) or 0)
        actual_server = str(getattr(account, "server", "") or "")
        if actual_login != int(state.get("account_login") or 0):
            return False, "MT5 account login changed after the demo session was armed."
        if actual_server != str(state.get("account_server") or ""):
            return False, "MT5 account server changed after the demo session was armed."
    return True, "Demo account identity is verified and locked."
