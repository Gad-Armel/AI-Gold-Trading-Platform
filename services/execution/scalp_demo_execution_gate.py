from __future__ import annotations

from typing import Any

from models.scalping_state import ScalpSignalState

from config import scalping_settings
from config import settings as core_settings
from services.bot.scalping_readiness_checker import build_scalping_readiness_report
from services.execution.demo_session_guard import validate_demo_session_identity
from services.research.v6_approval import load_v6_approval
from services.research.v63_self_learning import load_v63_champion_status


def _failure(reasons: list[str], **extra: Any) -> dict[str, Any]:
    return {"allowed": False, "action": "SCALP_DEMO_GATE_BLOCKED", "reasons": reasons, **extra}


def evaluate_scalp_demo_execution_gate(
    *,
    symbol: str,
    mt5_module: Any | None = None,
    readiness_report: dict[str, Any] | None = None,
    signal: ScalpSignalState | None = None,
) -> dict[str, Any]:
    """Defense-in-depth gate checked again immediately before every order."""
    reasons: list[str] = []
    readiness = readiness_report or {}

    if not bool(scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED):
        reasons.append("SCALPING_DEMO_EXECUTION_ENABLED is False.")
    if bool(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED):
        reasons.append("Real-account execution must remain disabled.")
    if bool(scalping_settings.SCALPING_PAPER_ONLY):
        reasons.append("SCALPING_PAPER_ONLY must be False for the separate demo runner.")
    if bool(getattr(core_settings, "ENABLE_LIVE_TRADING", False)):
        reasons.append("Core ENABLE_LIVE_TRADING must remain False.")
    if bool(getattr(core_settings, "EMERGENCY_STOP", False)):
        reasons.append("The core emergency stop is enabled.")
    if float(scalping_settings.SCALPING_LOT_SIZE) > float(scalping_settings.SCALPING_DEMO_MAX_LOT_SIZE) + 1e-12:
        reasons.append("Configured lot size exceeds the controlled demo pilot cap.")

    if bool(getattr(scalping_settings, "SCALPING_V6_DEMO_APPROVAL_REQUIRED", True)):
        approval = load_v6_approval()
        if not bool(approval.get("approved", False)):
            reasons.append(str(approval.get("reason", "V6 demo approval is missing.")))
    if bool(getattr(scalping_settings, "SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL", True)):
        model_status = load_v63_champion_status()
        if not bool(model_status.get("approved", False)):
            reasons.append(str(model_status.get("reason", "V6.3 calibrated model is missing.")))

    if bool(scalping_settings.SCALPING_REQUIRE_PAPER_READINESS_FOR_DEMO):
        readiness = readiness_report or build_scalping_readiness_report()
        if not bool(readiness.get("stages", {}).get("demo_review", {}).get("passed", False)):
            reasons.append("Paper-scalping demo-readiness requirements have not passed.")

    if reasons:
        return _failure(reasons, symbol=symbol, readiness=readiness)

    if mt5_module is None:
        try:
            import MetaTrader5 as mt5_module  # type: ignore
        except ImportError:
            return _failure(["MetaTrader5 Python package is unavailable."], symbol=symbol, readiness=readiness)

    terminal = mt5_module.terminal_info()
    account = mt5_module.account_info()
    identity_ok, identity_reason = validate_demo_session_identity(account, mt5_module)
    if not identity_ok:
        reasons.append(identity_reason)

    if terminal is None:
        reasons.append("MT5 terminal information is unavailable.")
    else:
        if not bool(getattr(terminal, "connected", False)):
            reasons.append("MT5 terminal is not connected.")
        if not bool(getattr(terminal, "trade_allowed", False)):
            reasons.append("MT5 terminal automated trading is not allowed.")
        if bool(getattr(terminal, "tradeapi_disabled", False)):
            reasons.append("MT5 external Python trading API is disabled.")

    if account is None:
        reasons.append("MT5 account information is unavailable.")
    else:
        if not bool(getattr(account, "trade_allowed", False)):
            reasons.append("Trading is not allowed on the connected account.")
        if not bool(getattr(account, "trade_expert", False)):
            reasons.append("Expert/algorithmic trading is not allowed on the account.")

    positions = mt5_module.positions_get(symbol=symbol)
    open_count = 0
    external_count = 0
    if positions is None:
        reasons.append("Unable to read existing MT5 positions for the symbol.")
    else:
        magic = int(scalping_settings.SCALPING_MAGIC_NUMBER)
        open_count = sum(int(getattr(p, "magic", -1)) == magic for p in positions)
        external_count = len(positions) - open_count
        if open_count >= int(scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS):
            reasons.append(f"Demo scalp position limit reached: {open_count}/{scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS}.")
        if external_count and bool(scalping_settings.SCALPING_DEMO_REQUIRE_ZERO_EXTERNAL_SYMBOL_POSITIONS):
            reasons.append(f"{external_count} non-bot {symbol} position(s) are open; pilot entry blocked.")


    if reasons:
        return _failure(reasons, symbol=symbol, readiness=readiness, open_demo_positions=open_count, external_positions=external_count)

    return {
        "allowed": True,
        "action": "SCALP_DEMO_GATE_ALLOWED",
        "reasons": [],
        "symbol": symbol,
        "readiness": readiness,
        "pilot_readiness_override": not bool(scalping_settings.SCALPING_REQUIRE_PAPER_READINESS_FOR_DEMO),
        "open_demo_positions": open_count,
        "external_positions": external_count,
        "account_login": getattr(account, "login", None),
        "account_server": getattr(account, "server", None),
        "account_trade_mode": getattr(account, "trade_mode", None),
    }
