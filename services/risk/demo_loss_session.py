from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from config import scalping_settings
from services.utils.atomic_json import atomic_write_json


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_demo_loss_session_path() -> str:
    path = str(scalping_settings.SCALPING_DEMO_LOSS_SESSION_STATE_PATH)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


def load_demo_loss_session() -> dict[str, Any]:
    path = get_demo_loss_session_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return dict(payload) if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _account_values(account: Any | None) -> tuple[int, str]:
    if account is None:
        return 0, ""
    return (
        int(getattr(account, "login", 0) or 0),
        str(getattr(account, "server", "") or ""),
    )


def reset_demo_loss_session(account: Any | None = None) -> dict[str, Any]:
    login, server = _account_values(account)
    state = {
        "version": 1,
        "status": "ACTIVE",
        "started_at": datetime.now().strftime(DATETIME_FORMAT),
        "account_login": login,
        "account_server": server,
        "loss_limit_usd": float(scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD),
        "stop_latched": False,
        "stopped_at": "",
        "stopped_profit_usd": None,
        "last_updated_at": datetime.now().strftime(DATETIME_FORMAT),
    }
    atomic_write_json(get_demo_loss_session_path(), state, indent=2)
    return state


def prepare_demo_loss_session(
    account: Any | None = None, *, reset: bool = False
) -> dict[str, Any]:
    if reset:
        state = reset_demo_loss_session(account)
        return {"allowed": True, "reset": True, "state": state, "reason": "Loss session reset to zero."}

    state = load_demo_loss_session()
    if not state:
        state = reset_demo_loss_session(account)
        return {"allowed": True, "reset": False, "state": state, "reason": "New cumulative loss session created."}

    login, server = _account_values(account)
    stored_login = int(state.get("account_login", 0) or 0)
    stored_server = str(state.get("account_server", "") or "")
    if stored_login and login and stored_login != login:
        return {
            "allowed": False,
            "reset": False,
            "state": state,
            "reason": "Cumulative loss session belongs to a different MT5 login. Use --reset-loss-session intentionally.",
        }
    if stored_server and server and stored_server != server:
        return {
            "allowed": False,
            "reset": False,
            "state": state,
            "reason": "Cumulative loss session belongs to a different MT5 server. Use --reset-loss-session intentionally.",
        }
    if bool(state.get("stop_latched", False)):
        return {
            "allowed": False,
            "reset": False,
            "state": state,
            "reason": "The cumulative -$100 loss stop is latched. Relaunch with --reset-loss-session to start from zero.",
        }
    return {"allowed": True, "reset": False, "state": state, "reason": "Existing cumulative loss session resumed."}


def latch_demo_loss_stop(profit_usd: float) -> dict[str, Any]:
    state = load_demo_loss_session()
    if not state:
        state = reset_demo_loss_session(None)
    state.update(
        {
            "status": "STOPPED",
            "stop_latched": True,
            "stopped_at": datetime.now().strftime(DATETIME_FORMAT),
            "stopped_profit_usd": round(float(profit_usd), 2),
            "last_updated_at": datetime.now().strftime(DATETIME_FORMAT),
        }
    )
    atomic_write_json(get_demo_loss_session_path(), state, indent=2)
    return state


def touch_demo_loss_session(**updates: Any) -> dict[str, Any]:
    state = load_demo_loss_session()
    if not state:
        state = reset_demo_loss_session(None)
    state.update(updates)
    state["last_updated_at"] = datetime.now().strftime(DATETIME_FORMAT)
    atomic_write_json(get_demo_loss_session_path(), state, indent=2)
    return state
