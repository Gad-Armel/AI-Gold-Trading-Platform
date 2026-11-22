from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import gold_consensus_settings as settings
from config import settings as core_settings
from services.execution.demo_session_guard import validate_demo_session_identity
from services.execution.scalp_profit_calculator import find_price_for_profit
from services.execution.gold_execution_metrics import execution_metrics
from services.market_data.gold_broker_clock import to_broker_time, broker_epoch_to_utc, quote_age as broker_quote_age
from config import gold_inverse_settings as inverse_settings
from services.execution.gold_inverse_policy import inverse_active
from services.execution.gold_pair_exit import publish_exit
from services.research.gold_market_schedule import broker_entry_permission


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "_asdict"):
        try:
            return dict(value._asdict())
        except Exception:
            return {}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _retcode(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _journal(record: dict[str, Any]) -> None:
    path = Path(settings.JOURNAL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _filling_mode(mt5: Any, info: Any) -> int | None:
    flags = int(getattr(info, "filling_mode", 0) or 0)
    if flags & int(getattr(mt5, "SYMBOL_FILLING_FOK", 1)):
        return int(mt5.ORDER_FILLING_FOK)
    if flags & int(getattr(mt5, "SYMBOL_FILLING_IOC", 2)):
        return int(mt5.ORDER_FILLING_IOC)
    if getattr(info, "trade_exemode", None) != getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", None):
        return int(mt5.ORDER_FILLING_RETURN)
    return None


def _normalized_volume(requested: float, info: Any) -> float:
    minimum = float(getattr(info, "volume_min", requested) or requested)
    maximum = float(getattr(info, "volume_max", requested) or requested)
    step = float(getattr(info, "volume_step", minimum) or minimum)
    value = min(max(float(requested), minimum), maximum)
    steps = math.floor((value - minimum) / step + 1e-9)
    decimals = max(0, len(str(step).split(".")[-1].rstrip("0")))
    return round(minimum + steps * step, decimals)


def consensus_positions(mt5: Any) -> list[Any]:
    owned_magics = {int(settings.MAGIC_NUMBER)} | {
        int(config["magic"]) for config in getattr(settings, "HORIZON_LANES", {}).values()
    }
    return [
        position for position in (mt5.positions_get(symbol=settings.SYMBOL) or ())
        if int(getattr(position, "magic", -1)) in owned_magics
    ]


def horizon_positions(mt5: Any, horizon: str) -> list[Any]:
    config = settings.HORIZON_LANES[str(horizon).upper()]
    positions = mt5.positions_get(symbol=settings.SYMBOL)
    if positions is None:
        raise RuntimeError(f"Unable to read MT5 positions: {mt5.last_error()}")
    return [position for position in positions
            if int(getattr(position, "magic", -1)) == int(config["magic"])]


def horizon_exposure_slots(mt5: Any, horizon: str) -> int:
    return len(horizon_positions(mt5, horizon))


def _positions_snapshot(mt5: Any) -> tuple[bool, list[Any], str]:
    positions = mt5.positions_get(symbol=settings.SYMBOL)
    if positions is None:
        return False, [], f"Unable to read MT5 positions: {mt5.last_error()}"
    return True, list(positions), ""


def exposure_slots(mt5: Any) -> int:
    total = sum(float(getattr(position, "volume", 0.0) or 0.0) for position in consensus_positions(mt5))
    return int(math.ceil(max(0.0, total) / float(settings.LOT_SIZE) - 1e-9))


def consensus_position_details(mt5: Any) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for position in consensus_positions(mt5):
        direction = "BUY" if int(getattr(position, "type", -1)) == int(mt5.POSITION_TYPE_BUY) else "SELL"
        details.append({
            "ticket": int(getattr(position, "ticket", 0) or 0),
            "direction": direction,
            "volume": float(getattr(position, "volume", 0.0) or 0.0),
            "entry_price": float(getattr(position, "price_open", 0.0) or 0.0),
            "opened_epoch": broker_epoch_to_utc(float(getattr(position, "time", 0) or 0)).timestamp(),
            "current_price": float(getattr(position, "price_current", 0.0) or 0.0),
            "profit": float(getattr(position, "profit", 0.0) or 0.0),
            "sl": float(getattr(position, "sl", 0.0) or 0.0),
            "tp": float(getattr(position, "tp", 0.0) or 0.0),
        })
    return details


def recent_closed_consensus_trades(mt5: Any, *, limit: int = 50, lookback_days: int = 30,
                                   magic_number: int | None = None, reset_after: datetime | None = None,
                                   strict: bool = False, deals_snapshot: tuple | None = None) -> list[dict[str, Any]]:
    """Reconstruct the latest closed hedging positions from broker deal history."""
    try:
        end = datetime.now(timezone.utc)
        deals = (deals_snapshot if deals_snapshot is not None else
                 mt5.history_deals_get(to_broker_time(end - timedelta(days=max(1, lookback_days))), to_broker_time(end)))
    except Exception:
        if strict:
            raise
        return []
    if deals is None:
        if strict:
            raise RuntimeError('Broker deal history unavailable')
        return []
    entry_in = int(getattr(mt5, "DEAL_ENTRY_IN", 0))
    entry_out = int(getattr(mt5, "DEAL_ENTRY_OUT", 1))
    entry_out_by = int(getattr(mt5, "DEAL_ENTRY_OUT_BY", 3))
    buy_type = int(getattr(mt5, "DEAL_TYPE_BUY", 0))
    grouped: dict[int, list[Any]] = {}
    expected_magic = int(magic_number if magic_number is not None else settings.MAGIC_NUMBER)
    owned_ids = {int(getattr(deal,'position_id',0)) for deal in deals
                 if int(getattr(deal,'magic',-1)) == expected_magic}
    for deal in deals:
        if int(getattr(deal, 'position_id', 0)) not in owned_ids:
            continue
        deal_msc = int(getattr(deal, "time_msc", 0) or int(getattr(deal, "time", 0) or 0) * 1000)
        deal_time = broker_epoch_to_utc(deal_msc / 1000.0)
        if reset_after is not None and deal_time <= reset_after.astimezone(timezone.utc):
            continue
        position_id = int(getattr(deal, "position_id", 0) or 0)
        if position_id > 0:
            grouped.setdefault(position_id, []).append(deal)
    closed: list[dict[str, Any]] = []
    for position_id, rows in grouped.items():
        entries = [row for row in rows if int(getattr(row, "entry", -1)) == entry_in]
        exits = [row for row in rows if int(getattr(row, "entry", -1)) in {entry_out, entry_out_by}]
        if not entries or not exits:
            continue
        entries.sort(key=lambda row: int(getattr(row, "time_msc", 0) or 0))
        exits.sort(key=lambda row: int(getattr(row, "time_msc", 0) or 0))
        entry_volume = sum(float(getattr(row, "volume", 0.0) or 0.0) for row in entries)
        exit_volume = sum(float(getattr(row, "volume", 0.0) or 0.0) for row in exits)
        if exit_volume + 1e-9 < entry_volume:
            continue
        entry_price = sum(float(getattr(row, "price", 0.0) or 0.0) * float(getattr(row, "volume", 0.0) or 0.0) for row in entries) / max(entry_volume, 1e-12)
        exit_price = sum(float(getattr(row, "price", 0.0) or 0.0) * float(getattr(row, "volume", 0.0) or 0.0) for row in exits) / max(exit_volume, 1e-12)
        net_profit = sum(
            sum(float(getattr(row, field, 0.0) or 0.0) for field in ("profit", "commission", "swap", "fee"))
            for row in rows
        )
        opened_msc = int(getattr(entries[0], "time_msc", 0) or int(getattr(entries[0], "time", 0) or 0) * 1000)
        closed_msc = int(getattr(exits[-1], "time_msc", 0) or int(getattr(exits[-1], "time", 0) or 0) * 1000)
        opened_at = broker_epoch_to_utc(opened_msc / 1000.0) if opened_msc else None
        closed_at = broker_epoch_to_utc(closed_msc / 1000.0) if closed_msc else None
        direction = "BUY" if int(getattr(entries[0], "type", -1)) == buy_type else "SELL"
        close_comment = str(getattr(exits[-1], "comment", "") or "").strip()
        closed.append({
            "position_id": position_id, "direction": direction, "volume": round(entry_volume, 4),
            "entry_price": round(entry_price, 6), "exit_price": round(exit_price, 6),
            "profit": round(net_profit, 2), "result": "WIN" if net_profit > 0 else "LOSS" if net_profit < 0 else "FLAT",
            "opened_at": opened_at.isoformat() if opened_at else None,
            "closed_at": closed_at.isoformat() if closed_at else None,
            "hold_seconds": round(max(0.0, (closed_msc - opened_msc) / 1000.0), 1) if opened_msc and closed_msc else None,
            "close_comment": close_comment or "Broker or strategy close",
            "closed_time_msc": closed_msc,
        })
    closed.sort(key=lambda item: int(item["closed_time_msc"]), reverse=True)
    for item in closed:
        item.pop("closed_time_msc", None)
    return closed[:max(1, int(limit))]


def execution_safety(mt5: Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    account = mt5.account_info()
    identity_ok, identity_reason = validate_demo_session_identity(account, mt5)
    if not identity_ok:
        reasons.append(identity_reason)
    hedging_mode = int(getattr(mt5, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", 2))
    if account is not None and int(getattr(account, "margin_mode", -1)) != hedging_mode:
        reasons.append("Independent protected positions require an MT5 hedging account; netting mode is blocked.")
    terminal = mt5.terminal_info()
    if terminal is None or not bool(getattr(terminal, "connected", False)):
        reasons.append("MT5 terminal is not connected.")
    elif not bool(getattr(terminal, "trade_allowed", False)) or bool(getattr(terminal, "tradeapi_disabled", False)):
        reasons.append("MT5 automated trading is unavailable.")
    if bool(getattr(core_settings, "ENABLE_LIVE_TRADING", False)):
        reasons.append("Core live trading must remain disabled.")
    if bool(getattr(core_settings, "EMERGENCY_STOP", False)):
        reasons.append("Emergency stop is enabled.")
    positions_ok, all_symbol_positions, positions_error = _positions_snapshot(mt5)
    if not positions_ok:
        reasons.append(positions_error)
    owned_magics = {int(settings.MAGIC_NUMBER)} | {int(item["magic"]) for item in settings.HORIZON_LANES.values()}
    if inverse_active(account):
        owned_magics.add(inverse_settings.MAGIC)
    if not math.isclose(float(settings.LOT_SIZE), 0.01, abs_tol=1e-12):
        reasons.append('User constraint requires exactly 0.01 lot per new position.')
    external = [p for p in all_symbol_positions if int(getattr(p, "magic", -1)) not in owned_magics]
    if external:
        reasons.append(f"{len(external)} external {settings.SYMBOL} position(s) detected.")
    if hasattr(mt5, 'orders_get'):
        pending = mt5.orders_get(symbol=settings.SYMBOL)
        if pending is None:
            reasons.append('Unable to reconcile pending MT5 orders.')
        elif any(int(getattr(order, 'magic', -1)) in owned_magics for order in pending):
            reasons.append('A controlled MT5 order is still pending; reconcile before another entry.')
    return not reasons, reasons


def close_safety(mt5: Any) -> tuple[bool, list[str]]:
    """Allow protective closes after a stop, but never after an account identity change."""
    reasons: list[str] = []
    identity_ok, identity_reason = validate_demo_session_identity(mt5.account_info(), mt5)
    if not identity_ok:
        reasons.append(identity_reason)
    if bool(getattr(core_settings, "ENABLE_LIVE_TRADING", False)):
        reasons.append("Core live trading must remain disabled.")
    return not reasons, reasons


def _planned_risk_block(mt5: Any, direction: str, volume: float, price: float, sl: float, *, enforce_budget: bool = True) -> dict[str, Any] | None:
    """Broker-valued stop exposure. Never squeeze a structural stop to force entry."""
    try:
        if getattr(mt5.account_info(), 'currency', None) != 'USD':
            raise ValueError('The $100 profile requires a USD account.')
        value = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL,
                                     settings.SYMBOL, volume, price, sl)
        if value is None or not math.isfinite(float(value)) or float(value) >= 0:
            raise ValueError('Unable to value protective stop exposure.')
        if enforce_budget and -float(value) > float(settings.MAX_TRADE_RISK_USD) + 1e-7:
            return {'success': False, 'action': 'RISK_BUDGET_BLOCK',
                    'message': f'Planned stop loss ${-float(value):.2f} exceeds ${settings.MAX_TRADE_RISK_USD:.2f} budget.'}
    except Exception as error:
        return {'success': False, 'action': 'RISK_BUDGET_BLOCK', 'message': str(error)}
    return None


def _money_stop_price(mt5, info, direction, volume, price, budget):
    """Value the USD stop with this gateway, quantize inward to broker ticks.

    The final risk check still uses order_calc_profit: a nonlinear symbol must
    never pass merely because this local linear estimate suggested a price.
    """
    point = float(info.point)
    tick_size = float(getattr(info, 'trade_tick_size', point) or point)
    if not all(math.isfinite(v) and v > 0 for v in (point, tick_size, budget, volume, price)):
        raise ValueError('Invalid broker price grid or money stop budget')
    sign = 1 if direction == 'BUY' else -1
    kind = mt5.ORDER_TYPE_BUY if sign == 1 else mt5.ORDER_TYPE_SELL
    probe = max(1., tick_size)
    value = mt5.order_calc_profit(kind, settings.SYMBOL, volume, price, price-sign*probe)
    if value is None or not math.isfinite(float(value)) or value >= 0:
        raise ValueError('Broker cannot value the protective stop')
    raw = price-sign*budget*probe/(-float(value))
    units = math.ceil(raw/tick_size-1e-9) if sign == 1 else math.floor(raw/tick_size+1e-9)
    digits = int(getattr(info, 'digits', 10))
    stop = round(units*tick_size, digits)
    return stop


def _stop_grid_block(info, direction, bid, ask, sl):
    point = float(info.point)
    step = float(getattr(info, 'trade_tick_size', point) or point)
    minimum = float(getattr(info, 'trade_stops_level', 0) or 0)*point
    distance = bid-sl if direction == 'BUY' else sl-ask
    if (not all(math.isfinite(v) for v in (point, step, minimum, distance, sl))
            or min(point, step, sl) <= 0 or distance <= 0 or distance+1e-8 < minimum
            or abs(sl/step-round(sl/step)) > 1e-6):
        return dict(success=False, action='STOP_GRID_BLOCK',
                    message='Protective stop violates broker tick grid or minimum stop distance.')
    return None


def _final_entry_quote(mt5, info, request, analysis_tp, analysis_sl):
    try:
        tick = mt5.symbol_info_tick(settings.SYMBOL)
        if tick is None:
            raise ValueError('Latest quote unavailable')
        bid, ask = float(tick.bid), float(tick.ask)
        stamp = float(getattr(tick, 'time_msc', 0) or 0)/1000.
        if not stamp:
            stamp = float(getattr(tick, 'time', 0) or 0)
        age = broker_quote_age(stamp) if stamp > 0 else float('inf')
        point = float(info.point)
        if (not all(math.isfinite(value) for value in (bid, ask, age, point))
                or bid <= 0 or ask < bid or point <= 0
                or age > settings.MAX_QUOTE_AGE_SECONDS
                or age < -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS):
            raise ValueError('Latest quote is invalid, stale or future-dated')
        direction = 'BUY' if request['type'] == mt5.ORDER_TYPE_BUY else 'SELL'
        permission = broker_entry_permission(mt5.symbol_info(settings.SYMBOL), direction)
        if permission:
            return permission, None
        price = ask if direction == 'BUY' else bid
        drift = abs(price-request['price'])
        if drift > request['deviation']*point+1e-9:
            raise ValueError('Price moved beyond the local execution drift budget; re-evaluate next cycle')
        reward = analysis_tp-price if direction == 'BUY' else price-analysis_tp
        risk = price-analysis_sl if direction == 'BUY' else analysis_sl-price
        if (reward <= 0 or risk <= 0 or ask-bid > settings.MAX_SPREAD_USD
                or (ask-bid)/reward > settings.MAX_SPREAD_TO_ANALYSIS_TARGET_RATIO
                or reward/risk < settings.MIN_ANALYSIS_REWARD_RISK):
            raise ValueError('Updated quote no longer supports the analysed costs or reward/risk')
        block = _stop_grid_block(info, direction, bid, ask, request['sl'])
        if block is None and 'stop_mode' not in request:
            block = _planned_risk_block(mt5, direction, request['volume'], price, request['sl'])
        if block:
            raise ValueError(block['message'])
        return None, dict(bid=bid, ask=ask, age_seconds=age, drift_price=drift,
                          broker_epoch=stamp, checked_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        return dict(success=False, action='FINAL_QUOTE_BLOCK', message=str(error)), None


def _s30_grid_stop(info, direction, stop):
    step = float(getattr(info, 'trade_tick_size', info.point) or info.point)
    if direction not in ('BUY', 'SELL') or not all(math.isfinite(value) and value > 0 for value in (step, stop)):
        raise ValueError('Invalid S30 stop or broker tick size')
    units = math.ceil(stop/step-1e-9) if direction == 'BUY' else math.floor(stop/step+1e-9)
    return round(units*step, int(getattr(info, 'digits', 10)))


def _entry_capacity_block(mt5: Any) -> dict[str, Any] | None:
    ok, positions, error = _positions_snapshot(mt5)
    if not ok:
        return {'success': False, 'action': 'ENTRY_BLOCKED', 'message': error}
    magics = {int(settings.MAGIC_NUMBER)} | {int(c['magic']) for c in settings.HORIZON_LANES.values()}
    scalp_magic = int(settings.HORIZON_LANES['SCALP']['magic'])
    scalp_positions = [p for p in positions if int(getattr(p, 'magic', -1)) == scalp_magic]
    if inverse_settings.PAIRING_ENABLED or len(scalp_positions) >= inverse_settings.MAX_INVERSE_POSITIONS:
        source_positions = scalp_positions
        if len(source_positions) >= inverse_settings.MAX_INVERSE_POSITIONS:
            return dict(success=False, action='POSITION_CAP',
                        message='Inverse demo pairing configured: reserve two of three combined slots for mirrors.')
    magics.add(inverse_settings.MAGIC)
    if hasattr(mt5, 'orders_get'):
        try:
            pending = mt5.orders_get(symbol=settings.SYMBOL)
        except Exception:
            pending = None
        if pending is None:
            return {'success': False, 'action': 'ENTRY_BLOCKED', 'message': 'Unable to reconcile pending MT5 orders before send.'}
        if any(int(getattr(order, 'magic', -1)) in magics for order in pending):
            return {'success': False, 'action': 'ENTRY_BLOCKED', 'message': 'Controlled MT5 order pending; reconcile before send.'}
    controlled = [p for p in positions if int(getattr(p,'magic',-1)) in magics]
    volume = sum(float(getattr(p,'volume',0.0)) for p in controlled)
    limit = min(3, int(settings.MAX_POSITION_SLOTS))
    if len(controlled) >= limit or volume + 0.01 > limit * 0.01 + 1e-12:
        return {'success': False, 'action': 'POSITION_CAP',
                'message': f'Global cap: {limit} positions / {limit * 0.01:.2f} lot total across all horizons.'}
    return None


def open_consensus_position(mt5: Any, direction: str, consensus: dict[str, Any]) -> dict[str, Any]:
    safe, reasons = execution_safety(mt5)
    if not safe:
        return {"success": False, "action": "ENTRY_BLOCKED", "message": " | ".join(reasons)}
    capacity_block = _entry_capacity_block(mt5)
    if capacity_block:
        return capacity_block
    if direction not in {"BUY", "SELL"} or not bool(consensus.get("allowed", False)):
        return {"success": False, "action": "ENTRY_BLOCKED", "message": "Confirmed consensus is required."}
    slots = exposure_slots(mt5)
    limit = min(3, int(settings.MAX_POSITION_SLOTS))
    if slots >= limit:
        return {"success": False, "action": "POSITION_CAP", "message": f"Exposure cap reached: {slots}/{limit}."}
    info = mt5.symbol_info(settings.SYMBOL)
    tick = mt5.symbol_info_tick(settings.SYMBOL)
    if info is None or tick is None:
        return {"success": False, "action": "MARKET_UNAVAILABLE", "message": "MT5 symbol metadata or tick is unavailable."}
    if not bool(getattr(info, "visible", True)) and not mt5.symbol_select(settings.SYMBOL, True):
        return {"success": False, "action": "SYMBOL_BLOCK", "message": "Could not enable XAUUSD in Market Watch."}
    bid, ask = float(tick.bid), float(tick.ask)
    if not all(math.isfinite(value) for value in (bid, ask)) or bid <= 0 or ask <= 0 or ask < bid:
        return {"success": False, "action": "QUOTE_BLOCK", "message": "MT5 returned an invalid bid/ask quote."}
    tick_msc = int(getattr(tick, "time_msc", 0) or 0)
    tick_seconds = tick_msc / 1000.0 if tick_msc > 0 else float(getattr(tick, "time", 0) or 0)
    quote_age = broker_quote_age(tick_seconds) if tick_seconds > 0 else float("inf")
    if (not math.isfinite(quote_age) or quote_age < -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS
            or quote_age > float(settings.MAX_QUOTE_AGE_SECONDS)):
        return {"success": False, "action": "QUOTE_BLOCK", "message": f"MT5 quote is stale ({quote_age:.1f}s)."}
    volume = _normalized_volume(float(settings.LOT_SIZE), info)
    if not math.isclose(volume, 0.01, rel_tol=0.0, abs_tol=1e-12):
        return {"success": False, "action": "VOLUME_BLOCK", "message": "Broker minimum volume exceeds the 0.01-lot cap."}
    is_buy = direction == "BUY"
    price = ask if is_buy else bid
    contract_size = float(getattr(info, "trade_contract_size", 100.0) or 100.0)
    point = float(getattr(info, "point", 0.01) or 0.01)
    sl, _ = find_price_for_profit(
        symbol=settings.SYMBOL, direction=direction, entry_price=price,
        lot_size=volume, contract_size=contract_size,
        target_profit_usd=-float(settings.INDIVIDUAL_EMERGENCY_STOP_USD), point=point,
    )
    tp = 0.0  # Profit is managed across the complete strategy basket.
    risk_block = _planned_risk_block(mt5, direction, volume, price, sl)
    if risk_block:
        return risk_block
    filling = _filling_mode(mt5, info)
    if filling is None:
        return {"success": False, "action": "FILLING_BLOCK", "message": "No supported order filling mode."}
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": settings.SYMBOL, "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL, "price": price,
        "sl": sl, "tp": tp, "deviation": int(settings.ORDER_DEVIATION_POINTS),
        "magic": int(settings.MAGIC_NUMBER), "comment": settings.ORDER_COMMENT,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
    }
    checked = mt5.order_check(request)
    check_data = _as_dict(checked)
    if checked is None or _retcode(check_data.get("retcode")) not in {0, int(getattr(mt5, "TRADE_RETCODE_DONE", -999))}:
        return {"success": False, "action": "ORDER_CHECK_BLOCKED", "message": str(check_data.get("comment", mt5.last_error()))}
    capacity_block = _entry_capacity_block(mt5)
    if capacity_block:
        return capacity_block
    try:
        result = mt5.order_send(request)
    except Exception as error:
        _journal({"record_type": "OPEN", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                  "success": False, "direction": direction, "error": f"{type(error).__name__}: {error}"})
        return {"success": False, "action": "ORDER_EXCEPTION", "message": f"MT5 order send failed: {error}"}
    data = _as_dict(result)
    successful = {int(getattr(mt5, name)) for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_DONE_PARTIAL", "TRADE_RETCODE_PLACED") if hasattr(mt5, name)}
    success = _retcode(data.get("retcode")) in successful
    _journal({
        "record_type": "OPEN", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "success": success, "direction": direction, "volume": volume, "entry_price": price,
        "tp": tp, "sl": sl, "basket_target_profit_usd": settings.BASKET_TAKE_PROFIT_USD,
        "individual_emergency_stop_usd": settings.INDIVIDUAL_EMERGENCY_STOP_USD,
        "consensus_evidence": consensus.get("evidence"),
        "retcode": data.get("retcode"), "order": data.get("order"), "deal": data.get("deal"),
    })
    return {"success": success, "action": "ORDER_SENT" if success else "ORDER_REJECTED", "message": str(data.get("comment", ""))}


def _close_one(mt5: Any, position: Any, *, magic_number: int | None = None, comment: str = "GoldConsensusClose", reason: str = "protective close") -> dict[str, Any]:
    if getattr(position, 'magic', None) == inverse_settings.SOURCE_MAGIC:
        try:
            if inverse_active(mt5.account_info()):
                publish_exit(mt5, position, reason)
        except Exception:
            pass
    info = mt5.symbol_info(settings.SYMBOL)
    tick = mt5.symbol_info_tick(settings.SYMBOL)
    if info is None or tick is None:
        return {"success": False, "message": "Close quote unavailable."}
    filling = _filling_mode(mt5, info)
    if filling is None:
        return {"success": False, "message": "Close filling mode unavailable."}
    is_buy = int(position.type) == int(mt5.POSITION_TYPE_BUY)
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "position": int(position.ticket), "symbol": settings.SYMBOL,
        "volume": float(position.volume), "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "price": float(tick.bid if is_buy else tick.ask), "deviation": int(settings.ORDER_DEVIATION_POINTS),
        "magic": int(magic_number if magic_number is not None else settings.MAGIC_NUMBER), "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
    }
    checked = mt5.order_check(request)
    check_data = _as_dict(checked)
    if checked is None or _retcode(check_data.get("retcode")) not in {0, int(getattr(mt5, "TRADE_RETCODE_DONE", -999))}:
        return {"success": False, "message": str(check_data.get("comment", mt5.last_error()))}
    send_started = time.perf_counter()
    try:
        result = mt5.order_send(request)
    except Exception as error:
        return {"success": False, "message": f"MT5 close send failed: {error}"}
    data = _as_dict(result)
    metrics = execution_metrics(request, data, elapsed_ms=(time.perf_counter()-send_started)*1000,
                                point=getattr(info,'point',None), contract_size=getattr(info,'trade_contract_size',None))
    successful = {int(getattr(mt5, name)) for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_DONE_PARTIAL", "TRADE_RETCODE_PLACED") if hasattr(mt5, name)}
    success = _retcode(data.get("retcode")) in successful
    _journal({"record_type": "CLOSE", "timestamp_utc": datetime.now(timezone.utc).isoformat(), "success": success,
              "position_ticket": int(position.ticket), "retcode": data.get("retcode"),
              "reason": reason, "magic": request['magic'], "requested_price": request['price'],
              "volume": request['volume'], "deal": data.get('deal'),
              "execution_metrics": metrics,
              "estimated_floating_profit": float(getattr(position,'profit',0.0))})
    return {"success": success, "message": str(data.get("comment", "")), "execution_metrics": metrics}


def open_horizon_position(mt5: Any, horizon: str, decision: dict[str, Any]) -> dict[str, Any]:
    horizon = str(horizon).upper()
    config = settings.HORIZON_LANES[horizon]
    if not config.get('trade_enabled', True):
        return {"success": False, "action": "ANALYSIS_ONLY", "message": f"{horizon} is analysis only."}
    safe, reasons = execution_safety(mt5)
    if not safe:
        return {"success": False, "action": "ENTRY_BLOCKED", "message": " | ".join(reasons)}
    capacity_block = _entry_capacity_block(mt5)
    if capacity_block:
        return capacity_block
    direction = str(decision.get("direction", "WAIT")).upper()
    if direction not in {"BUY", "SELL"} or not bool(decision.get("allowed", False)):
        return {"success": False, "action": "ENTRY_BLOCKED", "message": f"{horizon} confirmed decision required."}
    if len(horizon_positions(mt5, horizon)) >= int(config["max_positions"]):
        return {"success": False, "action": "POSITION_CAP", "message": f"{horizon} position cap reached."}
    info, tick = mt5.symbol_info(settings.SYMBOL), mt5.symbol_info_tick(settings.SYMBOL)
    if info is None or tick is None:
        return {"success": False, "action": "MARKET_UNAVAILABLE", "message": "MT5 symbol metadata or tick unavailable."}
    permission = broker_entry_permission(info, direction)
    if permission:
        return permission
    bid, ask = float(tick.bid), float(tick.ask)
    if not all(math.isfinite(value) for value in (bid, ask)) or bid <= 0 or ask <= 0 or ask < bid:
        return {"success": False, "action": "QUOTE_BLOCK", "message": "MT5 returned an invalid quote."}
    tick_msc = int(getattr(tick, "time_msc", 0) or 0)
    tick_seconds = tick_msc / 1000.0 if tick_msc else float(getattr(tick, "time", 0) or 0)
    quote_age = broker_quote_age(tick_seconds) if tick_seconds else float("inf")
    if (not math.isfinite(quote_age) or quote_age < -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS
            or quote_age > float(settings.MAX_QUOTE_AGE_SECONDS)):
        return {"success": False, "action": "QUOTE_BLOCK", "message": f"MT5 quote is stale ({quote_age:.1f}s)."}
    volume = _normalized_volume(float(settings.LOT_SIZE), info)
    if not math.isclose(volume, 0.01, rel_tol=0.0, abs_tol=1e-12):
        return {"success": False, "action": "VOLUME_BLOCK", "message": "Broker minimum volume exceeds configured lot."}
    is_buy, price = direction == "BUY", ask if direction == "BUY" else bid
    if horizon == 'SCALP':
        from services.research.gold_scalp_additions import addition_blocks
        blocks = addition_blocks(decision, horizon_position_details(mt5, horizon), bid, ask)
        if blocks:
            return {"success": False, "action": "ADDITION_BLOCK", "message": ' | '.join(blocks)}
    analysis_tp, analysis_sl = float(decision.get("take_profit") or 0.0), float(decision.get("stop_loss") or 0.0)
    valid_levels = analysis_tp > price > analysis_sl if is_buy else analysis_tp < price < analysis_sl
    if not valid_levels:
        return {"success": False, "action": "LEVEL_BLOCK", "message": f"{horizon} dynamic TP/SL are invalid for current price."}
    spread = ask - bid
    if spread > float(settings.MAX_SPREAD_USD):
        return {"success": False, "action": "COST_BLOCK",
                "message": f"{horizon} spread exceeds the configured absolute ceiling."}
    reward_distance = abs(analysis_tp - price)
    risk_distance = abs(price - analysis_sl)
    cost_ratio = spread / reward_distance if reward_distance > 0 else float("inf")
    if cost_ratio > float(settings.MAX_SPREAD_TO_ANALYSIS_TARGET_RATIO):
        return {
            "success": False, "action": "COST_BLOCK",
            "message": (f"{horizon} spread consumes {cost_ratio:.0%} of the analysed target; "
                        f"maximum is {settings.MAX_SPREAD_TO_ANALYSIS_TARGET_RATIO:.0%}."),
        }
    reward_risk = reward_distance / risk_distance if risk_distance > 0 else 0.0
    if reward_risk < float(settings.MIN_ANALYSIS_REWARD_RISK):
        return {
            "success": False, "action": "RISK_REWARD_BLOCK",
            "message": (f"{horizon} analysed reward/risk is {reward_risk:.2f}; "
                        f"minimum is {settings.MIN_ANALYSIS_REWARD_RISK:.2f}."),
        }
    entry_zone = dict(decision.get("levels", {}) or {}).get("entry_zone", [])
    if isinstance(entry_zone, (list, tuple)) and len(entry_zone) == 2:
        zone_low, zone_high = sorted((float(entry_zone[0]), float(entry_zone[1])))
        tolerance = spread * float(settings.ENTRY_ZONE_TOLERANCE_SPREADS)
        if price < zone_low - tolerance or price > zone_high + tolerance:
            return {
                "success": False, "action": "ENTRY_ZONE_BLOCK",
                "message": (f"{horizon} execution price {price:.3f} is outside the analysed entry zone "
                            f"{zone_low:.3f}-{zone_high:.3f}."),
            }
    sl = analysis_sl
    if decision.get('entry_mode') in ('S1_PRIMARY', 'S30_PRIMARY', 'S15_PRIMARY', 'S5_PRIMARY', 'THREE_SOURCE_VOTE') and str(config.get('stop_mode')).upper() == 'ANALYSIS':
        try:
            sl = _s30_grid_stop(info, direction, sl)
        except (ValueError, TypeError, AttributeError, OverflowError) as error:
            return dict(success=False, action='STOP_GRID_BLOCK', message=str(error))
    if str(config.get("stop_mode", "CUMULATIVE")) == "INDIVIDUAL":
        try:
            sl = _money_stop_price(mt5, info, direction, volume, price,
                                   float(config['individual_stop_loss_usd']))
        except (ValueError, TypeError, AttributeError, OverflowError) as error:
            return dict(success=False, action='RISK_BUDGET_BLOCK', message=str(error))
    grid_block = _stop_grid_block(info, direction, bid, ask, sl)
    if grid_block:
        return grid_block
    risk_block = _planned_risk_block(
        mt5, direction, volume, price, sl,
        enforce_budget=(str(config.get("stop_mode", "CUMULATIVE")).upper() != "ANALYSIS"
                        or decision.get("entry_mode") == "S1_PRIMARY"),
    )
    if risk_block:
        return risk_block
    filling = _filling_mode(mt5, info)
    if filling is None:
        return {"success": False, "action": "FILLING_BLOCK", "message": "No supported order filling mode."}
    tp = 0.0  # Lane profit exits are managed cumulatively in USD.
    request = {"action": mt5.TRADE_ACTION_DEAL, "symbol": settings.SYMBOL, "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL, "price": price,
        "sl": sl, "tp": tp, "deviation": int(settings.ORDER_DEVIATION_POINTS),
        "magic": int(config["magic"]), "comment": str(config["comment"]),
        "stop_mode": str(config.get("stop_mode", "CUMULATIVE")).upper(),
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling}
    checked = mt5.order_check(request); check_data = _as_dict(checked)
    if checked is None or _retcode(check_data.get("retcode")) not in {0, int(getattr(mt5, "TRADE_RETCODE_DONE", -999))}:
        return {"success": False, "action": "ORDER_CHECK_BLOCKED", "message": str(check_data.get("comment", mt5.last_error()))}
    capacity_block = _entry_capacity_block(mt5)
    if capacity_block:
        return capacity_block
    entry_context = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "quote": {"bid": bid, "ask": ask, "age_seconds": quote_age,
                  "broker_epoch": tick_seconds},
        "analysis_reward_risk": reward_risk,
        "spread_to_analysis_target": cost_ratio,
        "decision": {key: decision.get(key) for key in (
            "entry_mode", "entry_timeframe", "fast_timeframe_selection", "s30_entry", "evidence_type", "evidence", "dominant_bias",
            "contributors", "candle_confirmation", "entry_momentum_blocks",
            "entry_coordination", "higher_timeframe_context", "setup_observation", "levels", "entry_observation",
            "m1_sequence_quality", "m1_retest_shadow", "smc_strategy", "staged_m1_observation", "s30_shadow", "candle_input_health",
            "market_schedule", "market_execution_plan", "execution_thesis", "market_entry_plan", "support_analysis_families")},
    }
    final_block, final_quote = _final_entry_quote(mt5, info, request, analysis_tp, analysis_sl)
    if final_block:
        return final_block
    entry_context['final_quote'] = final_quote
    send_started = time.perf_counter()
    try:
        result = mt5.order_send(request)
    except Exception as error:
        _journal({"record_type": "HORIZON_OPEN", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                  "horizon": horizon, "success": False, "direction": direction,
                  "error": f"{type(error).__name__}: {error}",
                  "entry_context": entry_context})
        return {"success": False, "action": "ORDER_EXCEPTION", "message": f"MT5 order send failed: {error}"}
    data = _as_dict(result)
    metrics = execution_metrics(request, data, elapsed_ms=(time.perf_counter()-send_started)*1000,
                                point=getattr(info,'point',None), contract_size=getattr(info,'trade_contract_size',None))
    successful = {int(getattr(mt5, name)) for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_DONE_PARTIAL", "TRADE_RETCODE_PLACED") if hasattr(mt5, name)}
    success = _retcode(data.get("retcode")) in successful
    _journal({"record_type": "HORIZON_OPEN", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "horizon": horizon, "success": success, "direction": direction, "volume": volume,
        "entry_price": price, "tp": tp, "analysis_tp": analysis_tp,
        "sl": sl, "analysis_sl": analysis_sl, "stop_mode": config.get("stop_mode"),
        "cumulative_take_profit_usd": settings.HORIZON_CUMULATIVE_TAKE_PROFIT_USD,
        "evidence": decision.get("evidence"),
        "entry_context": entry_context,
        "broker_reported_price": data.get("price"),
        "broker_reported_volume": data.get("volume"),
        "execution_metrics": metrics,
        "retcode": data.get("retcode"), "order": data.get("order"), "deal": data.get("deal")})
    return {"success": success, "action": "ORDER_SENT" if success else "ORDER_REJECTED", "message": str(data.get("comment", "")), "execution_metrics": metrics,
            "deal": data.get('deal'), "order": data.get('order')}


def close_horizon_positions(mt5: Any, horizon: str, *, reason: str = "policy exit", tickets=None) -> dict[str, Any]:
    horizon = str(horizon).upper(); config = settings.HORIZON_LANES[horizon]
    safe, reasons = close_safety(mt5)
    if not safe:
        return {"closed_count": 0, "failures": reasons, "reason": reason}
    closed, failures = 0, []
    for position in horizon_positions(mt5, horizon):
        if tickets is not None and int(position.ticket) not in tickets:
            continue
        result = _close_one(mt5, position, magic_number=int(config["magic"]), comment=f"{horizon}PolicyClose", reason=reason)
        if result["success"]: closed += 1
        else: failures.append(result["message"])
    return {"closed_count": closed, "failures": failures, "reason": reason}


def horizon_position_details(mt5: Any, horizon: str) -> list[dict[str, Any]]:
    details = []
    for position in horizon_positions(mt5, horizon):
        details.append({"ticket": int(position.ticket),
            "opened_epoch": broker_epoch_to_utc(float(getattr(position, 'time', 0))).timestamp(),
            "direction": "BUY" if int(position.type) == int(mt5.POSITION_TYPE_BUY) else "SELL",
            "volume": float(position.volume), "entry_price": float(position.price_open),
            "current_price": float(getattr(position, "price_current", 0.0) or 0.0),
            "profit": float(getattr(position, "profit", 0.0) or 0.0),
            "sl": float(getattr(position, "sl", 0.0) or 0.0), "tp": float(getattr(position, "tp", 0.0) or 0.0)})
    return details


def horizon_floating_profit(mt5: Any, horizon: str) -> dict[str, Any]:
    """Combined broker-reported floating P/L for exactly one horizon lane."""
    try:
        positions = horizon_positions(mt5, horizon)
        profit = sum(float(getattr(position, "profit", 0.0) or 0.0)
                     + float(getattr(position, "swap", 0.0) or 0.0) for position in positions)
        return {"available": True, "profit": round(profit, 2), "position_count": len(positions), "reason": ""}
    except Exception as error:
        return {"available": False, "profit": 0.0, "position_count": 0,
                "reason": f"Unable to calculate {horizon} floating P/L: {error}"}


def align_positions_to_consensus(mt5: Any, consensus: dict[str, Any]) -> dict[str, Any]:
    desired = str(consensus.get("direction", "WAIT")) if consensus.get("allowed") else "WAIT"
    positions_ok, all_positions, positions_error = _positions_snapshot(mt5)
    positions = [p for p in all_positions if int(getattr(p, "magic", -1)) == int(settings.MAGIC_NUMBER)]
    if not positions_ok:
        return {"closed_count": 0, "failures": [positions_error], "desired_direction": desired,
                "open_positions": 0, "exposure_slots": 0}
    safe, reasons = close_safety(mt5)
    if not safe:
        return {"closed_count": 0, "failures": reasons, "desired_direction": desired,
                "open_positions": len(positions), "exposure_slots": exposure_slots(mt5)}
    closed = 0
    failures: list[str] = []
    for position in positions:
        current = "BUY" if int(position.type) == int(mt5.POSITION_TYPE_BUY) else "SELL"
        if desired not in {"BUY", "SELL"} or current != desired:
            result = _close_one(mt5, position)
            if result["success"]:
                closed += 1
            else:
                failures.append(result["message"])
    return {"closed_count": closed, "failures": failures, "desired_direction": desired,
            "open_positions": len(consensus_positions(mt5)), "exposure_slots": exposure_slots(mt5)}


def close_all_consensus_positions(mt5: Any) -> dict[str, Any]:
    safe, reasons = close_safety(mt5)
    if not safe:
        return {"closed_count": 0, "failures": reasons}
    positions_ok, all_positions, positions_error = _positions_snapshot(mt5)
    if not positions_ok:
        return {"closed_count": 0, "failures": [positions_error]}
    owned_magics = {int(settings.MAGIC_NUMBER)} | {int(item["magic"]) for item in settings.HORIZON_LANES.values()}
    positions = [p for p in all_positions if int(getattr(p, "magic", -1)) in owned_magics]
    closed = 0
    failures: list[str] = []
    for position in positions:
        result = _close_one(mt5, position, magic_number=int(getattr(position, "magic", settings.MAGIC_NUMBER)))
        if result["success"]:
            closed += 1
        else:
            failures.append(result["message"])
    return {"closed_count": closed, "failures": failures}


def basket_floating_profit(mt5: Any) -> dict[str, Any]:
    positions_ok, all_positions, positions_error = _positions_snapshot(mt5)
    if not positions_ok:
        return {"available": False, "profit": 0.0, "position_count": 0, "reason": positions_error}
    positions = [p for p in all_positions if int(getattr(p, "magic", -1)) == int(settings.MAGIC_NUMBER)]
    profit = sum(
        float(getattr(position, "profit", 0.0) or 0.0) + float(getattr(position, "swap", 0.0) or 0.0)
        for position in positions
    )
    return {"available": True, "profit": round(profit, 2), "position_count": len(positions), "reason": ""}


def session_profit(mt5: Any, started_at: datetime) -> dict[str, float | bool | str]:
    """Broker-derived P/L for the three independent horizon lanes only.

    The legacy single-consensus magic is deliberately excluded so losses or
    gains from the retired basket strategy cannot arm or clear this bot's
    rolling loss circuit breaker.
    """
    realized = 0.0
    try:
        deals = mt5.history_deals_get(to_broker_time(started_at), to_broker_time(datetime.now(timezone.utc)))
        if deals is None:
            return {"available": False, "realized": 0.0, "floating": 0.0, "total": 0.0,
                    "reason": f"Unable to read MT5 deal history: {mt5.last_error()}"}
        owned_magics = {int(item["magic"]) for item in settings.HORIZON_LANES.values()}
        owned_ids = {int(getattr(deal,'position_id',0)) for deal in deals
                     if int(getattr(deal,'magic',-1)) in owned_magics and int(getattr(deal,'position_id',0)) > 0}
        for deal in deals:
            if int(getattr(deal, "magic", -1)) not in owned_magics and int(getattr(deal,'position_id',0)) not in owned_ids:
                continue
            realized += sum(float(getattr(deal, field, 0.0) or 0.0) for field in ("profit", "commission", "swap", "fee"))
        positions_ok, all_positions, positions_error = _positions_snapshot(mt5)
        if not positions_ok:
            return {"available": False, "realized": round(realized, 2), "floating": 0.0,
                    "total": round(realized, 2), "reason": positions_error}
        floating = sum(
            float(getattr(position, "profit", 0.0) or 0.0)
            + float(getattr(position, "swap", 0.0) or 0.0)
            for position in all_positions
            if int(getattr(position, "magic", -1)) in owned_magics
        )
        total = realized + floating
        return {"available": True, "realized": round(realized, 2), "floating": round(floating, 2),
                "total": round(total, 2), "reason": ""}
    except Exception as error:
        return {"available": False, "realized": 0.0, "floating": 0.0, "total": 0.0,
                "reason": f"MT5 session P/L error: {type(error).__name__}: {error}"}
