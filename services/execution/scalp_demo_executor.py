from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.execution.scalp_demo_execution_gate import (
    evaluate_scalp_demo_execution_gate,
)
from services.execution.scalp_demo_journal import append_demo_record
from services.execution.scalp_profit_calculator import find_price_for_profit
from services.risk.adaptive_spread_policy import evaluate_adaptive_spread_policy


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
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


def _normalize_volume(requested: float, info: Any) -> float:
    minimum = float(getattr(info, "volume_min", requested) or requested)
    maximum = float(getattr(info, "volume_max", requested) or requested)
    step = float(getattr(info, "volume_step", minimum) or minimum)
    value = min(max(float(requested), minimum), maximum)
    steps = math.floor((value - minimum) / step + 1e-9)
    normalized = minimum + steps * step
    decimals = max(0, len(str(step).split(".")[-1].rstrip("0")))
    return round(normalized, decimals)


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _tick_quote_age_seconds(tick: Any, now: datetime) -> float:
    time_msc = int(getattr(tick, "time_msc", 0) or 0)
    if time_msc > 0:
        return max(0.0, now.timestamp() - time_msc / 1000.0)
    tick_time = int(getattr(tick, "time", 0) or 0)
    if tick_time > 0:
        return max(0.0, now.timestamp() - float(tick_time))
    return 0.0


def _execution_preflight(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    tick: Any,
    *,
    decision_timestamp: datetime | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Revalidate price, cost and decision freshness immediately before send."""

    checked_at = _aware_utc(now)
    bid = _float(getattr(tick, "bid", snapshot.bid), snapshot.bid)
    ask = _float(getattr(tick, "ask", snapshot.ask), snapshot.ask)
    spread = max(0.0, ask - bid)
    quote_age = _tick_quote_age_seconds(tick, checked_at)
    current_snapshot = replace(
        snapshot,
        bid=bid,
        ask=ask,
        spread=spread,
        mid=(bid + ask) / 2.0,
        quote_age_seconds=quote_age,
    )
    spread_policy = evaluate_adaptive_spread_policy(current_snapshot, signal)

    decision_at = _aware_utc(decision_timestamp)
    decision_age = max(0.0, (checked_at - decision_at).total_seconds())
    direction = str(getattr(signal, "direction", "NEUTRAL")).upper()
    adverse_move = (
        max(0.0, ask - float(snapshot.ask))
        if direction == "BUY"
        else max(0.0, float(snapshot.bid) - bid)
        if direction == "SELL"
        else 999.0
    )
    metrics = getattr(signal, "metrics", {})
    m1 = metrics.get("M1", {}) if isinstance(metrics, dict) else {}
    atr = _float(m1.get("atr", m1.get("atr_usd", 0.0))) if isinstance(m1, dict) else 0.0
    absolute_limit = float(scalping_settings.SCALPING_DEMO_MAX_ADVERSE_PRICE_MOVE_USD)
    atr_limit = atr * float(scalping_settings.SCALPING_DEMO_MAX_ADVERSE_MOVE_ATR_RATIO) if atr > 0 else absolute_limit
    adverse_limit = min(absolute_limit, atr_limit) if atr_limit > 0 else absolute_limit

    checks = {
        "direction": direction in {"BUY", "SELL"},
        "fresh_decision": decision_age
        <= float(scalping_settings.SCALPING_DEMO_MAX_DECISION_AGE_SECONDS) + 1e-9,
        "fresh_quote": quote_age
        <= float(scalping_settings.SCALPING_MAX_QUOTE_STALE_SECONDS) + 1e-9,
        "spread_policy": bool(spread_policy.get("accepted", False)),
        "adverse_reprice": adverse_move <= adverse_limit + 1e-9,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "allowed": not failed,
        "checks": checks,
        "failed_checks": failed,
        "checked_at_utc": checked_at.isoformat(),
        "decision_age_seconds": round(decision_age, 6),
        "quote_age_seconds": round(quote_age, 6),
        "decision_bid": round(float(snapshot.bid), 8),
        "decision_ask": round(float(snapshot.ask), 8),
        "current_bid": round(bid, 8),
        "current_ask": round(ask, 8),
        "current_spread": round(spread, 8),
        "adverse_move_usd": round(adverse_move, 8),
        "adverse_move_limit_usd": round(adverse_limit, 8),
        "m1_atr": round(atr, 8),
        "spread_policy": spread_policy,
        "current_snapshot": current_snapshot,
        "reason": (
            "Execution preflight passed."
            if not failed
            else "Execution preflight blocked: " + ", ".join(failed) + "."
        ),
    }


def execute_demo_scalp(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    *,
    readiness_report: dict[str, Any] | None = None,
    mt5_module: Any | None = None,
    decision_timestamp: datetime | None = None,
    request_timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Open one controlled MT5 DEMO position after all independent gates pass."""

    if not signal.allowed or signal.direction not in {"BUY", "SELL"}:
        return {
            "success": False,
            "action": "SCALP_DEMO_SIGNAL_BLOCKED",
            "message": "A confirmed BUY or SELL scalp signal is required.",
        }

    if mt5_module is None:
        try:
            import MetaTrader5 as mt5_module  # type: ignore
        except ImportError:
            return {
                "success": False,
                "action": "SCALP_DEMO_MT5_UNAVAILABLE",
                "message": "MetaTrader5 Python package is unavailable.",
            }

    gate = evaluate_scalp_demo_execution_gate(
        symbol=snapshot.symbol,
        mt5_module=mt5_module,
        readiness_report=readiness_report,
        signal=signal,
    )
    if not gate["allowed"]:
        return {
            "success": False,
            "action": "SCALP_DEMO_GATE_BLOCKED",
            "message": " | ".join(gate["reasons"]),
            "gate": gate,
        }

    if not bool(scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED):
        return {
            "success": False,
            "action": "SCALP_DEMO_DISABLED",
            "message": "Demo execution is disabled; no order was sent.",
        }
    if bool(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED):
        return {
            "success": False,
            "action": "REAL_EXECUTION_SAFETY_BLOCK",
            "message": "Real-account execution safety flag is invalid.",
        }

    symbol = snapshot.symbol
    info = mt5_module.symbol_info(symbol)
    if info is None:
        return {
            "success": False,
            "action": "SCALP_DEMO_SYMBOL_UNAVAILABLE",
            "message": f"No symbol metadata returned for {symbol}.",
        }

    if not bool(getattr(info, "visible", True)):
        if not mt5_module.symbol_select(symbol, True):
            return {
                "success": False,
                "action": "SCALP_DEMO_SYMBOL_SELECT_FAILED",
                "message": f"Could not enable {symbol} in Market Watch.",
            }

    tick = mt5_module.symbol_info_tick(symbol)
    if tick is None:
        return {
            "success": False,
            "action": "SCALP_DEMO_TICK_UNAVAILABLE",
            "message": f"No current tick returned for {symbol}.",
        }

    preflight = _execution_preflight(
        snapshot,
        signal,
        tick,
        decision_timestamp=decision_timestamp,
        now=request_timestamp or datetime.now(timezone.utc),
    )
    if not preflight["allowed"]:
        return {
            "success": False,
            "action": "SCALP_DEMO_PREFLIGHT_BLOCKED",
            "message": preflight["reason"],
            "preflight": {k: v for k, v in preflight.items() if k != "current_snapshot"},
        }

    current_snapshot = preflight["current_snapshot"]
    direction = signal.direction
    is_buy = direction == "BUY"
    order_type = mt5_module.ORDER_TYPE_BUY if is_buy else mt5_module.ORDER_TYPE_SELL
    price = float(current_snapshot.ask if is_buy else current_snapshot.bid)
    volume = _normalize_volume(float(scalping_settings.SCALPING_LOT_SIZE), info)
    if volume > float(scalping_settings.SCALPING_DEMO_MAX_LOT_SIZE) + 1e-12:
        return {
            "success": False,
            "action": "SCALP_DEMO_VOLUME_SAFETY_BLOCK",
            "message": f"Normalized volume {volume} exceeds demo pilot cap {scalping_settings.SCALPING_DEMO_MAX_LOT_SIZE}.",
        }
    contract_size = float(
        getattr(info, "trade_contract_size", snapshot.contract_size)
        or snapshot.contract_size
    )
    point = float(getattr(info, "point", snapshot.point) or snapshot.point)

    target_price, target_method = find_price_for_profit(
        symbol=symbol,
        direction=direction,
        entry_price=price,
        lot_size=volume,
        contract_size=contract_size,
        target_profit_usd=float(signal.target_profit_usd),
        point=point,
    )
    stop_price, stop_method = find_price_for_profit(
        symbol=symbol,
        direction=direction,
        entry_price=price,
        lot_size=volume,
        contract_size=contract_size,
        target_profit_usd=-float(signal.stop_loss_usd),
        point=point,
    )

    filling_mode = _select_filling_mode(mt5_module, info)
    if filling_mode is None:
        return {
            "success": False,
            "action": "SCALP_DEMO_FILLING_MODE_UNAVAILABLE",
            "message": "No supported market-order filling mode was detected.",
        }

    request = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": stop_price,
        "tp": target_price,
        "deviation": int(scalping_settings.SCALPING_DEMO_ORDER_DEVIATION_POINTS),
        "magic": int(scalping_settings.SCALPING_MAGIC_NUMBER),
        "comment": str(scalping_settings.SCALPING_DEMO_COMMENT),
        "type_time": getattr(mt5_module, "ORDER_TIME_GTC"),
        "type_filling": filling_mode,
    }

    check = mt5_module.order_check(request)
    if check is None:
        return {
            "success": False,
            "action": "SCALP_DEMO_ORDER_CHECK_FAILED",
            "message": f"MT5 order_check returned None: {mt5_module.last_error()}",
            "request": request,
            "preflight": {k: v for k, v in preflight.items() if k != "current_snapshot"},
        }

    check_dict = _as_dict(check)
    check_retcode = int(check_dict.get("retcode", 0) or 0)
    successful_check_codes = {
        0,
        int(getattr(mt5_module, "TRADE_RETCODE_DONE", -99999)),
    }
    if check_retcode not in successful_check_codes:
        return {
            "success": False,
            "action": "SCALP_DEMO_ORDER_CHECK_REJECTED",
            "message": str(check_dict.get("comment", "MT5 order_check rejected request.")),
            "request": request,
            "check": check_dict,
            "preflight": {k: v for k, v in preflight.items() if k != "current_snapshot"},
        }

    request_sent_at = _aware_utc(request_timestamp)
    result = mt5_module.order_send(request)
    response_at = datetime.now(timezone.utc)
    result_dict = _as_dict(result)
    successful_codes = {
        int(getattr(mt5_module, name))
        for name in (
            "TRADE_RETCODE_DONE",
            "TRADE_RETCODE_DONE_PARTIAL",
            "TRADE_RETCODE_PLACED",
        )
        if hasattr(mt5_module, name)
    }
    retcode = int(result_dict.get("retcode", -1) or -1)
    success = retcode in successful_codes

    position_ticket = result_dict.get("order") or result_dict.get("deal")
    if success:
        try:
            positions = mt5_module.positions_get(symbol=symbol) or ()
            matching = [
                position
                for position in positions
                if int(getattr(position, "magic", -1))
                == int(scalping_settings.SCALPING_MAGIC_NUMBER)
            ]
            if matching:
                newest = max(
                    matching,
                    key=lambda item: int(
                        getattr(item, "time_msc", getattr(item, "time", 0)) or 0
                    ),
                )
                position_ticket = int(getattr(newest, "ticket"))
        except Exception:
            pass

    fill_price = float(result_dict.get("price", price) or price)
    entry_slippage_price = (fill_price - price) if direction == "BUY" else (price - fill_price)
    entry_slippage_usd = entry_slippage_price * volume * contract_size
    slippage_warning = entry_slippage_price > float(scalping_settings.SCALPING_DEMO_MAX_ENTRY_SLIPPAGE_USD)
    metrics = signal.metrics if isinstance(signal.metrics, dict) else {}
    v6_gate = metrics.get("v6_candidate_gate", {}) if isinstance(metrics, dict) else {}
    structure = metrics.get("v6_market_structure", {}) if isinstance(metrics, dict) else {}
    persistence = metrics.get("signal_persistence", {}) if isinstance(metrics, dict) else {}
    clean_preflight = {k: v for k, v in preflight.items() if k != "current_snapshot"}

    record = {
        "record_type": "OPEN",
        "status": "OPEN" if success else "REJECTED",
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "symbol": symbol,
        "direction": direction,
        "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "entry_price": price,
        "actual_entry_fill": fill_price,
        "entry_slippage_price": round(entry_slippage_price, 8),
        "entry_slippage_usd": round(entry_slippage_usd, 6),
        "entry_slippage_warning": slippage_warning,
        "decision_timestamp_utc": _aware_utc(decision_timestamp or request_sent_at).isoformat(),
        "order_request_timestamp_utc": request_sent_at.isoformat(),
        "broker_response_timestamp_utc": response_at.isoformat(),
        "decision_to_request_ms": round(max(0.0, (request_sent_at - _aware_utc(decision_timestamp or request_sent_at)).total_seconds() * 1000.0), 3),
        "request_to_response_ms": round(max(0.0, (response_at - request_sent_at).total_seconds() * 1000.0), 3),
        "volume": volume,
        "target_profit_usd": signal.target_profit_usd,
        "stop_loss_usd": signal.stop_loss_usd,
        "target_price": target_price,
        "stop_price": stop_price,
        "target_price_method": target_method,
        "stop_price_method": stop_method,
        "signal_key": signal.signal_key,
        "signal_score": signal.score,
        "signal_pattern": signal.pattern,
        "v6_candidate_gate": v6_gate,
        "v6_market_structure": structure,
        "entry_quality_index": v6_gate.get("structure_confidence"),
        "entry_profile": {
            "structure_direction": v6_gate.get("structure_direction"),
            "structure_votes": v6_gate.get("structure_votes"),
            "vwap_distance_atr": v6_gate.get("vwap_distance_atr"),
            "micro_confidence": v6_gate.get("micro_confidence"),
        },
        "spread_policy": preflight.get("spread_policy", {}),
        "signal_persistence": persistence,
        "execution_preflight": clean_preflight,
        "order_check": check_dict,
        "order_ticket": result_dict.get("order"),
        "deal_ticket": result_dict.get("deal"),
        "position_ticket": position_ticket,
        "retcode": retcode,
        "broker_comment": result_dict.get("comment", ""),
        "request": request,
    }
    journal_path = append_demo_record(record)

    message = str(result_dict.get("comment", ""))
    if success and slippage_warning:
        message = (message + " | " if message else "") + (
            f"Entry slippage warning: {entry_slippage_price:.3f} exceeds "
            f"${float(scalping_settings.SCALPING_DEMO_MAX_ENTRY_SLIPPAGE_USD):.2f}."
        )
    return {
        "success": success,
        "action": "SCALP_DEMO_ORDER_SENT" if success else "SCALP_DEMO_ORDER_REJECTED",
        "message": message,
        "retcode": retcode,
        "request": request,
        "result": result_dict,
        "preflight": clean_preflight,
        "entry_slippage_warning": slippage_warning,
        "journal_path": journal_path,
    }
