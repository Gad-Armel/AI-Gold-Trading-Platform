from __future__ import annotations

from typing import Any

from config import scalping_settings
from config import settings as core_settings
from services.research.v6_approval import load_v6_approval
from services.research.v63_self_learning import load_v63_champion_status


def build_demo_preflight(mt5_module: Any, symbol: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    terminal = mt5_module.terminal_info()
    account = mt5_module.account_info()
    info = mt5_module.symbol_info(symbol)
    tick = mt5_module.symbol_info_tick(symbol)

    checks["demo_execution_enabled"] = bool(scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED)
    approval = load_v6_approval()
    model_status = load_v63_champion_status()
    checks["v6_demo_approval"] = (not bool(scalping_settings.SCALPING_V6_DEMO_APPROVAL_REQUIRED)) or bool(approval.get("approved", False))
    checks["v63_approved_model"] = (not bool(getattr(scalping_settings, "SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL", True))) or bool(model_status.get("approved", False))
    checks["real_execution_disabled"] = not bool(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED)
    checks["core_live_disabled"] = not bool(getattr(core_settings, "ENABLE_LIVE_TRADING", False))
    checks["emergency_stop_clear"] = not bool(getattr(core_settings, "EMERGENCY_STOP", False))
    checks["terminal_available"] = terminal is not None
    checks["account_available"] = account is not None
    checks["symbol_available"] = info is not None
    checks["tick_available"] = tick is not None

    if terminal is not None:
        checks["terminal_connected"] = bool(getattr(terminal, "connected", False))
        checks["terminal_trade_allowed"] = bool(getattr(terminal, "trade_allowed", False))
        checks["python_trade_api_enabled"] = not bool(getattr(terminal, "tradeapi_disabled", False))
    else:
        checks.update({"terminal_connected": False, "terminal_trade_allowed": False, "python_trade_api_enabled": False})

    if account is not None:
        demo_mode = int(getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", 0))
        checks["account_is_demo"] = int(getattr(account, "trade_mode", -1)) == demo_mode
        checks["account_trade_allowed"] = bool(getattr(account, "trade_allowed", False))
        checks["account_expert_allowed"] = bool(getattr(account, "trade_expert", False))
    else:
        checks.update({"account_is_demo": False, "account_trade_allowed": False, "account_expert_allowed": False})

    if info is not None:
        requested = float(scalping_settings.SCALPING_LOT_SIZE)
        minimum = float(getattr(info, "volume_min", requested) or requested)
        maximum = float(getattr(info, "volume_max", requested) or requested)
        checks["lot_size_supported"] = minimum <= requested <= maximum
        checks["lot_size_within_pilot_cap"] = requested <= float(scalping_settings.SCALPING_DEMO_MAX_LOT_SIZE) + 1e-12
    else:
        checks.update({"lot_size_supported": False, "lot_size_within_pilot_cap": False})

    positions = mt5_module.positions_get(symbol=symbol)
    checks["positions_readable"] = positions is not None
    external_positions = []
    bot_positions = []
    if positions is not None:
        magic = int(scalping_settings.SCALPING_MAGIC_NUMBER)
        for position in positions:
            if int(getattr(position, "magic", -1)) == magic:
                bot_positions.append(position)
            else:
                external_positions.append(position)
    checks["no_external_symbol_positions"] = not external_positions or not bool(
        scalping_settings.SCALPING_DEMO_REQUIRE_ZERO_EXTERNAL_SYMBOL_POSITIONS
    )
    checks["bot_position_limit_available"] = len(bot_positions) < int(
        scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS
    )

    for name, passed in checks.items():
        if not passed:
            reasons.append(name.replace("_", " ").capitalize() + " failed.")

    return {
        "passed": not reasons,
        "checks": checks,
        "reasons": reasons,
        "symbol": symbol,
        "account_login": getattr(account, "login", None),
        "account_server": getattr(account, "server", None),
        "account_trade_mode": getattr(account, "trade_mode", None),
        "account_balance": getattr(account, "balance", None),
        "account_equity": getattr(account, "equity", None),
        "account_currency": getattr(account, "currency", None),
        "requested_lot_size": float(scalping_settings.SCALPING_LOT_SIZE),
        "pilot_max_lot_size": float(scalping_settings.SCALPING_DEMO_MAX_LOT_SIZE),
        "external_symbol_positions": len(external_positions),
        "bot_symbol_positions": len(bot_positions),
        "v6_approval": approval,
        "v63_model_status": model_status,
    }


def print_demo_preflight(report: dict[str, Any]) -> None:
    print("")
    print("=" * 70)
    print("CONTROLLED MT5 DEMO PREFLIGHT")
    print("=" * 70)
    print(f"Status: {'PASSED' if report['passed'] else 'BLOCKED'}")
    print(f"Account Login: {report.get('account_login')}")
    print(f"Server: {report.get('account_server')}")
    print(f"Trade Mode: {report.get('account_trade_mode')} (must be DEMO)")
    print(f"Balance/Equity: {report.get('account_balance')} / {report.get('account_equity')} {report.get('account_currency') or ''}")
    print(f"Symbol: {report.get('symbol')}")
    print(f"Lot: {report.get('requested_lot_size')} | hard pilot cap={report.get('pilot_max_lot_size')}")
    print(f"External symbol positions: {report.get('external_symbol_positions')}")
    approval = report.get("v6_approval", {}) or {}
    print(f"V6 Demo Approval: {'VALID' if approval.get('approved') else 'MISSING/BLOCKED'} — {approval.get('reason', '')}")
    model = report.get("v63_model_status", {}) or {}
    print(f"V6.3 Calibrated Model: {'VALID' if model.get('approved') else 'MISSING/BLOCKED'} — {model.get('reason', '')}")
    if report.get("reasons"):
        print("Block reasons:")
        for reason in report["reasons"]:
            print(f"  - {reason}")
    else:
        print("All demo-only checks passed.")
    print("=" * 70)
