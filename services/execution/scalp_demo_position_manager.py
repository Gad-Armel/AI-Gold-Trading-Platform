from __future__ import annotations

from datetime import datetime
from typing import Any

from config import scalping_settings
from config import settings as core_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.execution.scalp_demo_journal import load_demo_history, save_demo_history
from services.execution.demo_session_guard import validate_demo_session_identity


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "_asdict"):
        try:
            return value._asdict()
        except Exception:
            return {}
    return {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_direction(value: Any) -> str:
    text = str(value or "NEUTRAL").strip().upper()
    if text in {"BUY", "BULL", "BULLISH", "LONG"}:
        return "BUY"
    if text in {"SELL", "BEAR", "BEARISH", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def _opposite_exit_confirmed(
    signal: ScalpSignalState,
    current_direction: str,
    hold_seconds: int,
) -> tuple[bool, dict[str, Any]]:
    """Require a persistent, tick-confirmed opposite signal before closing.

    The previous demo manager closed direct-score positions on any allowed score
    flip. In a noisy XAUUSD tape this can crystallize many small losses. Broker
    TP/SL remains authoritative; this helper only governs discretionary closes.
    """

    metrics = _as_dict(getattr(signal, "metrics", {}))
    diagnostics = _as_dict(metrics.get("score_diagnostics"))
    direct = _as_dict(diagnostics.get("direct_score_decision"))
    micro = _as_dict(metrics.get("microstructure"))

    candidate = _normalize_direction(getattr(signal, "direction", "NEUTRAL"))
    current = _normalize_direction(current_direction)
    winner_score = _float(direct.get("winner_score", getattr(signal, "score", 0.0)))
    margin = _float(direct.get("margin", diagnostics.get("direction_margin", 0.0)))
    micro_direction = _normalize_direction(micro.get("direction"))
    micro_confidence = _float(micro.get("confidence"))

    checks = {
        "signal_allowed": bool(getattr(signal, "allowed", False)),
        "opposite_direction": candidate in {"BUY", "SELL"} and candidate != current,
        "minimum_hold": hold_seconds
        >= int(scalping_settings.SCALPING_DEMO_MIN_HOLD_BEFORE_OPPOSITE_EXIT_SECONDS),
        "winner_score": winner_score + 1e-9
        >= float(scalping_settings.SCALPING_DEMO_OPPOSITE_EXIT_MIN_SCORE),
        "score_margin": margin + 1e-9
        >= float(scalping_settings.SCALPING_DEMO_OPPOSITE_EXIT_MIN_MARGIN),
        "micro_confirmation": bool(
            micro_direction == candidate
            and micro_confidence + 1e-9
            >= float(
                scalping_settings.SCALPING_DEMO_OPPOSITE_EXIT_MIN_MICRO_CONFIDENCE
            )
        ),
    }
    return all(checks.values()), {
        "checks": checks,
        "candidate": candidate,
        "winner_score": winner_score,
        "score_margin": margin,
        "micro_direction": micro_direction,
        "micro_confidence": micro_confidence,
    }


def _profit_protection_reason(
    peak_profit: float,
    current_profit: float,
    target_profit: float | None = None,
    hold_seconds: int = 999,
) -> str:
    if not bool(scalping_settings.SCALPING_DEMO_PROFIT_PROTECTION_ENABLED):
        return ""

    # V5.2 scales profit protection to the actual target. This avoids closing
    # a $1.20 setup using thresholds originally calibrated for a $0.50 target.
    # Optional arguments retain the fixed-threshold behavior used by legacy
    # regression tests and old journal rows.
    dynamic = bool(
        getattr(
            scalping_settings,
            "SCALPING_DEMO_DYNAMIC_PROFIT_PROTECTION_ENABLED",
            False,
        )
    )
    target = float(target_profit or 0.0)
    minimum_hold = int(
        getattr(
            scalping_settings,
            "SCALPING_DEMO_PROFIT_PROTECTION_MIN_HOLD_SECONDS",
            0,
        )
    )
    if dynamic and target > 0.0:
        if hold_seconds < minimum_hold:
            return ""
        stages = (
            (
                3,
                float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_3_TRIGGER_RATIO),
                float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_3_FLOOR_RATIO),
            ),
            (
                2,
                float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_RATIO),
                float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_FLOOR_RATIO),
            ),
            (
                1,
                float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_RATIO),
                float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_FLOOR_RATIO),
            ),
        )
        for stage, trigger_ratio, floor_ratio in stages:
            trigger = target * trigger_ratio
            floor = target * floor_ratio
            if peak_profit + 1e-9 >= trigger and current_profit <= floor + 1e-9:
                return f"Demo dynamic stage-{stage} profit giveback protection"
        return ""

    if (
        peak_profit >= float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_TRIGGER_USD)
        and current_profit <= float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_2_FLOOR_USD)
    ):
        return "Demo stage-2 profit giveback protection"
    if (
        peak_profit >= float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_TRIGGER_USD)
        and current_profit <= float(scalping_settings.SCALPING_DEMO_PROFIT_STAGE_1_FLOOR_USD)
    ):
        return "Demo stage-1 profit giveback protection"
    return ""


def _hold_extension_allowed(
    signal: ScalpSignalState,
    current_direction: str,
    current_profit: float,
) -> tuple[bool, dict[str, Any]]:
    metrics = _as_dict(getattr(signal, "metrics", {}))
    micro = _as_dict(metrics.get("microstructure"))
    signal_direction = _normalize_direction(getattr(signal, "direction", "NEUTRAL"))
    position_direction = _normalize_direction(current_direction)
    micro_direction = _normalize_direction(micro.get("direction"))
    micro_confidence = _float(micro.get("confidence"))
    strong_opposite = bool(
        micro_direction in {"BUY", "SELL"}
        and micro_direction != position_direction
        and micro_confidence + 1e-9
        >= float(scalping_settings.SCALPING_DEMO_STRONG_OPPOSITE_MICRO_CONFIDENCE)
    )
    checks = {
        "profitable": current_profit > 0.0,
        "signal_allowed": bool(getattr(signal, "allowed", False)),
        "same_direction_signal": signal_direction == position_direction,
        "no_strong_opposite_tape": not strong_opposite,
    }
    return all(checks.values()), {
        "checks": checks,
        "signal_direction": signal_direction,
        "micro_direction": micro_direction,
        "micro_confidence": micro_confidence,
    }





def _v6_thesis_exit_reason(
    signal: ScalpSignalState,
    current_direction: str,
    hold_seconds: int,
    peak_profit: float,
    current_profit: float,
) -> str:
    """Mirror the V6 shadow triple-barrier thesis exits in approved demo mode."""
    if not str(getattr(scalping_settings, "SCALPING_STRATEGY_ID", "")).startswith(
        "XAUUSD_SCALP_V6_"
    ):
        return ""

    if (
        hold_seconds >= int(scalping_settings.SCALPING_V6_NO_PROGRESS_CHECK_SECONDS)
        and peak_profit < float(scalping_settings.SCALPING_V6_NO_PROGRESS_MAX_MFE_USD)
        and current_profit <= float(scalping_settings.SCALPING_V6_NO_PROGRESS_EXIT_PNL_USD)
    ):
        return "V6 no-progress thesis exit"

    if (
        peak_profit >= float(scalping_settings.SCALPING_V6_BREAKEVEN_TRIGGER_USD)
        and current_profit <= float(scalping_settings.SCALPING_V6_BREAKEVEN_FLOOR_USD)
    ):
        return "V6 break-even protection"

    metrics = _as_dict(getattr(signal, "metrics", {}))
    micro = _as_dict(metrics.get("microstructure"))
    micro_direction = _normalize_direction(micro.get("direction"))
    micro_confidence = _float(micro.get("confidence"))
    opposite = "SELL" if _normalize_direction(current_direction) == "BUY" else "BUY"
    if (
        hold_seconds >= int(scalping_settings.SCALPING_V6_MIN_HOLD_BEFORE_THESIS_EXIT_SECONDS)
        and current_profit < 0.0
        and micro_direction == opposite
        and micro_confidence + 1e-9
        >= float(scalping_settings.SCALPING_V6_STRONG_OPPOSITE_EXIT_CONFIDENCE)
    ):
        return "V6 strong-opposite-tape thesis exit"
    return ""

def _select_filling_mode(mt5_module: Any, info: Any) -> int | None:
    flags = int(getattr(info, "filling_mode", 0) or 0)
    fok_flag = int(getattr(mt5_module, "SYMBOL_FILLING_FOK", 1))
    ioc_flag = int(getattr(mt5_module, "SYMBOL_FILLING_IOC", 2))
    if flags & fok_flag:
        return int(getattr(mt5_module, "ORDER_FILLING_FOK"))
    if flags & ioc_flag:
        return int(getattr(mt5_module, "ORDER_FILLING_IOC"))
    market_execution = getattr(mt5_module, "SYMBOL_TRADE_EXECUTION_MARKET", None)
    execution_mode = getattr(info, "trade_exemode", None)
    if market_execution is None or execution_mode != market_execution:
        return int(getattr(mt5_module, "ORDER_FILLING_RETURN"))
    return None


def _close_safety(mt5_module: Any) -> tuple[bool, str]:
    if not bool(scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED):
        return False, "Demo execution is disabled."
    if bool(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED):
        return False, "Real-account execution flag must remain False."
    if bool(getattr(core_settings, "EMERGENCY_STOP", False)):
        # Emergency stop blocks new entries, but open demo positions still need
        # to be closable. Continue to the account-only checks below.
        pass

    account = mt5_module.account_info()
    terminal = mt5_module.terminal_info()
    if account is None or terminal is None:
        return False, "MT5 account or terminal information is unavailable."
    identity_ok, identity_reason = validate_demo_session_identity(account, mt5_module)
    if not identity_ok:
        return False, identity_reason
    if not bool(getattr(terminal, "connected", False)):
        return False, "MT5 terminal is not connected."
    if bool(getattr(terminal, "tradeapi_disabled", False)):
        return False, "MT5 Python trading API is disabled."
    return True, "Demo close safety passed."


def _history_profit(mt5_module: Any, ticket: int) -> float | None:
    try:
        deals = mt5_module.history_deals_get(position=int(ticket))
    except Exception:
        return None
    if not deals:
        return None
    total = 0.0
    for deal in deals:
        total += float(getattr(deal, "profit", 0.0) or 0.0)
        total += float(getattr(deal, "commission", 0.0) or 0.0)
        total += float(getattr(deal, "swap", 0.0) or 0.0)
        total += float(getattr(deal, "fee", 0.0) or 0.0)
    return round(total, 2)


def _close_position(mt5_module: Any, position: Any, symbol_info: Any) -> dict[str, Any]:
    safe, reason = _close_safety(mt5_module)
    if not safe:
        return {"success": False, "message": reason}

    symbol = str(getattr(position, "symbol"))
    tick = mt5_module.symbol_info_tick(symbol)
    if tick is None:
        return {"success": False, "message": "No tick available for demo close."}

    position_type = int(getattr(position, "type"))
    buy_type = int(getattr(mt5_module, "POSITION_TYPE_BUY", 0))
    closing_buy = position_type != buy_type
    order_type = (
        mt5_module.ORDER_TYPE_BUY if closing_buy else mt5_module.ORDER_TYPE_SELL
    )
    price = float(getattr(tick, "ask" if closing_buy else "bid"))

    filling_mode = _select_filling_mode(mt5_module, symbol_info)
    if filling_mode is None:
        return {"success": False, "message": "No supported close filling mode."}

    request = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "position": int(getattr(position, "ticket")),
        "symbol": symbol,
        "volume": float(getattr(position, "volume")),
        "type": order_type,
        "price": price,
        "deviation": int(scalping_settings.SCALPING_DEMO_ORDER_DEVIATION_POINTS),
        "magic": int(scalping_settings.SCALPING_MAGIC_NUMBER),
        "comment": str(scalping_settings.SCALPING_DEMO_COMMENT) + "_CLOSE",
        "type_time": getattr(mt5_module, "ORDER_TIME_GTC"),
        "type_filling": filling_mode,
    }
    result = mt5_module.order_send(request)
    result_dict = _as_dict(result)
    successful = {
        int(getattr(mt5_module, name))
        for name in (
            "TRADE_RETCODE_DONE",
            "TRADE_RETCODE_DONE_PARTIAL",
            "TRADE_RETCODE_PLACED",
        )
        if hasattr(mt5_module, name)
    }
    retcode = int(result_dict.get("retcode", -1) or -1)
    return {
        "success": retcode in successful,
        "message": str(result_dict.get("comment", "")),
        "retcode": retcode,
        "request": request,
        "result": result_dict,
    }


def manage_demo_scalp_positions(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    *,
    mt5_module: Any | None = None,
) -> dict[str, Any]:
    """Monitor only positions created by the controlled scalp demo magic number."""

    if mt5_module is None:
        try:
            import MetaTrader5 as mt5_module  # type: ignore
        except ImportError:
            return {
                "success": False,
                "action": "SCALP_DEMO_MT5_UNAVAILABLE",
                "message": "MetaTrader5 package is unavailable.",
            }

    positions_result = mt5_module.positions_get(symbol=snapshot.symbol)
    if positions_result is None:
        return {
            "success": False,
            "action": "SCALP_DEMO_POSITION_READ_FAILED",
            "message": str(mt5_module.last_error()),
        }

    magic = int(scalping_settings.SCALPING_MAGIC_NUMBER)
    positions = {
        int(getattr(position, "ticket")): position
        for position in positions_result
        if int(getattr(position, "magic", -1)) == magic
    }
    history = load_demo_history()
    changed = False
    messages: list[str] = []
    closed_count = 0

    # Reconcile broker-side SL/TP or manual closures.
    for record in history:
        if str(record.get("status", "")).upper() != "OPEN":
            continue
        ticket = int(record.get("position_ticket", 0) or 0)
        if ticket and ticket not in positions:
            final_profit = _history_profit(mt5_module, ticket)
            record["status"] = "CLOSED"
            record["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record["final_profit_usd"] = final_profit
            record["close_reason"] = "Broker-side SL/TP, manual close, or external close"
            changed = True
            closed_count += 1
            messages.append(f"Reconciled closed demo position {ticket}.")

    records_by_ticket = {
        int(record.get("position_ticket", 0) or 0): record
        for record in history
        if str(record.get("status", "")).upper() == "OPEN"
    }

    for ticket, position in positions.items():
        record = records_by_ticket.get(ticket)
        if record is None:
            record = {
                "record_type": "RECOVERED_POSITION",
                "status": "OPEN",
                "position_ticket": ticket,
                "symbol": snapshot.symbol,
                "direction": (
                    "BUY"
                    if int(getattr(position, "type"))
                    == int(getattr(mt5_module, "POSITION_TYPE_BUY", 0))
                    else "SELL"
                ),
                "opened_at": datetime.fromtimestamp(
                    int(getattr(position, "time", 0) or 0)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "target_profit_usd": scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD,
                "stop_loss_usd": scalping_settings.SCALPING_MIN_STOP_LOSS_USD,
            }
            history.append(record)
            changed = True

        profit = float(getattr(position, "profit", 0.0) or 0.0)
        opened_epoch = int(getattr(position, "time", 0) or 0)
        hold_seconds = max(0, int(datetime.now().timestamp() - opened_epoch))
        record["unrealized_profit_usd"] = round(profit, 2)
        record["hold_seconds"] = hold_seconds
        record["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        previous_peak = _float(record.get("peak_profit_usd"), profit)
        peak_profit = max(previous_peak, profit)
        record["peak_profit_usd"] = round(peak_profit, 2)
        changed = True

        target = float(
            record.get("target_profit_usd", scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD)
        )
        stop = float(
            record.get("stop_loss_usd", scalping_settings.SCALPING_MIN_STOP_LOSS_USD)
        )
        close_reason = ""
        v6_thesis_reason = _v6_thesis_exit_reason(
            signal,
            str(record.get("direction", "NEUTRAL")),
            hold_seconds,
            peak_profit,
            profit,
        )
        record["v6_thesis_exit_reason"] = v6_thesis_reason
        profit_protection_reason = _profit_protection_reason(peak_profit, profit, target, hold_seconds)
        opposite_confirmed, opposite_detail = _opposite_exit_confirmed(
            signal,
            str(record.get("direction", "NEUTRAL")),
            hold_seconds,
        )
        record["opposite_exit_diagnostics"] = opposite_detail
        if profit >= target:
            close_reason = "Demo scalp dollar target reached"
        elif profit <= -stop:
            close_reason = "Demo scalp dollar stop reached"
        elif v6_thesis_reason:
            close_reason = v6_thesis_reason
        elif profit_protection_reason:
            close_reason = profit_protection_reason
        elif hold_seconds >= int(scalping_settings.SCALPING_DEMO_MAX_HOLD_SECONDS):
            base_hold = int(scalping_settings.SCALPING_DEMO_MAX_HOLD_SECONDS)
            extension = int(scalping_settings.SCALPING_DEMO_MAX_HOLD_EXTENSION_SECONDS)
            extension_allowed, extension_detail = _hold_extension_allowed(
                signal,
                str(record.get("direction", "NEUTRAL")),
                profit,
            )
            record["hold_extension_diagnostics"] = extension_detail
            if extension_allowed and hold_seconds < base_hold + extension:
                record["hold_extension_active"] = True
            else:
                record["hold_extension_active"] = False
                close_reason = (
                    "Demo scalp absolute extended hold reached"
                    if hold_seconds >= base_hold + extension
                    else "Demo scalp evidence-based maximum hold reached"
                )
        elif snapshot.spread >= float(
            scalping_settings.SCALPING_EMERGENCY_EXIT_SPREAD_USD
        ):
            close_reason = "Demo scalp emergency spread exit"
        elif scalping_settings.SCALPING_CLOSE_ON_OPPOSITE_SIGNAL and opposite_confirmed:
            close_reason = "Tick-confirmed opposite demo scalp signal"

        if close_reason:
            info = mt5_module.symbol_info(snapshot.symbol)
            result = _close_position(mt5_module, position, info)
            if result["success"]:
                record["status"] = "CLOSED"
                record["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                record["final_profit_usd"] = round(profit, 2)
                record["close_reason"] = close_reason
                record["close_retcode"] = result.get("retcode")
                closed_count += 1
                messages.append(f"Closed demo position {ticket}: {close_reason}.")
            else:
                messages.append(
                    f"Failed to close demo position {ticket}: {result['message']}"
                )

    if changed:
        path = save_demo_history(history)
    else:
        path = ""

    return {
        "success": True,
        "action": "SCALP_DEMO_POSITIONS_MANAGED",
        "open_position_count": len(positions) - closed_count,
        "closed_count": closed_count,
        "message": " | ".join(messages) if messages else "No demo position action required.",
        "history_path": path,
    }



def close_all_demo_scalp_positions(*, mt5_module: Any | None = None) -> dict[str, Any]:
    """Flatten only positions carrying this controlled-demo magic number."""
    if mt5_module is None:
        try:
            import MetaTrader5 as mt5_module  # type: ignore
        except ImportError:
            return {"success": False, "closed_count": 0, "message": "MetaTrader5 package is unavailable."}
    positions_result = mt5_module.positions_get(symbol=scalping_settings.SCALPING_SYMBOL)
    if positions_result is None:
        return {"success": False, "closed_count": 0, "message": str(mt5_module.last_error())}
    magic = int(scalping_settings.SCALPING_MAGIC_NUMBER)
    positions = [p for p in positions_result if int(getattr(p, "magic", -1)) == magic]
    info = mt5_module.symbol_info(scalping_settings.SCALPING_SYMBOL)
    closed = 0
    messages: list[str] = []
    for position in positions:
        result = _close_position(mt5_module, position, info)
        if result.get("success"):
            closed += 1
            messages.append(f"Closed demo position {getattr(position, 'ticket', '')}.")
        else:
            messages.append(f"Failed to close {getattr(position, 'ticket', '')}: {result.get('message', '')}")
    return {"success": closed == len(positions), "closed_count": closed, "found_count": len(positions), "message": " | ".join(messages) if messages else "No controlled demo positions were open."}
