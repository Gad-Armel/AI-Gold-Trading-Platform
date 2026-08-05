
import math
import time
from typing import Any

import MetaTrader5 as mt5

from config import settings


# ======================================================================
# GENERAL HELPERS
# ======================================================================

def _last_error_text() -> str:
    try:
        return str(mt5.last_error())
    except Exception:
        return "Unknown MT5 error."


def _to_dict(value: Any) -> dict[str, Any]:
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


def _failure(
    action: str,
    message: str,
    *,
    symbol: str | None = None,
    direction: str | None = None,
    request: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result = {
        "success": False,
        "action": action,
        "message": message,
        "symbol": symbol,
        "direction": direction,
        "retcode": None,
        "request": request,
        "last_error": _last_error_text(),
    }

    result.update(extra)

    return result


def _successful_retcodes() -> set[int]:
    """
    Successful order_send return codes.
    """

    names = (
        "TRADE_RETCODE_DONE",
        "TRADE_RETCODE_DONE_PARTIAL",
        "TRADE_RETCODE_PLACED",
    )

    return {
        int(getattr(mt5, name))
        for name in names
        if hasattr(mt5, name)
    }


def _get_magic_number() -> int:
    try:
        return int(
            getattr(
                settings,
                "MAGIC_NUMBER",
                20260709,
            )
        )
    except (TypeError, ValueError):
        return 20260709


def _get_deviation_points() -> int:
    try:
        deviation = int(
            getattr(
                settings,
                "ORDER_DEVIATION_POINTS",
                20,
            )
        )
    except (TypeError, ValueError):
        deviation = 20

    return max(0, deviation)


# ======================================================================
# FINAL LOCAL LIVE-SAFETY CHECK
# ======================================================================

def _check_local_live_safety(
    symbol: str,
    direction: str,
) -> dict[str, Any]:
    """
    Final defense-in-depth protection.

    The execution gate and trade executor should already have passed
    before these functions are called. These checks prevent accidental
    direct calls to open_buy(), open_sell(), or close_position().
    """

    if (
        getattr(
            settings,
            "EMERGENCY_STOP",
            False,
        )
        is True
    ):
        return _failure(
            action="EMERGENCY_STOP_BLOCKED",
            message=(
                "Emergency stop is active. "
                "No MT5 request was sent."
            ),
            symbol=symbol,
            direction=direction,
        )

    if (
        getattr(
            settings,
            "ENABLE_LIVE_TRADING",
            False,
        )
        is not True
    ):
        return _failure(
            action="LIVE_TRADING_DISABLED",
            message=(
                "Live trading is disabled. "
                "No MT5 request was sent."
            ),
            symbol=symbol,
            direction=direction,
        )

    live_confirmation = str(
        getattr(
            settings,
            "LIVE_TRADING_CONFIRMATION",
            "",
        )
        or ""
    )

    required_confirmation = str(
        getattr(
            settings,
            "REQUIRED_LIVE_TRADING_CONFIRMATION",
            "I_ACCEPT_LIVE_TRADING_RISK",
        )
        or ""
    )

    if (
        not required_confirmation
        or live_confirmation
        != required_confirmation
    ):
        return _failure(
            action="LIVE_CONFIRMATION_BLOCKED",
            message=(
                "Live-trading confirmation is missing "
                "or invalid."
            ),
            symbol=symbol,
            direction=direction,
        )

    return {
        "success": True,
        "action": "LOCAL_SAFETY_PASSED",
        "message": (
            "Local order-manager safety checks passed."
        ),
    }


# ======================================================================
# TERMINAL AND SYMBOL VALIDATION
# ======================================================================

def _prepare_symbol(
    symbol: str,
) -> tuple[Any | None, dict[str, Any] | None]:
    clean_symbol = str(
        symbol or ""
    ).strip().upper()

    if not clean_symbol:
        return None, _failure(
            action="INVALID_SYMBOL",
            message="Trading symbol is missing.",
        )

    terminal_info = mt5.terminal_info()

    if terminal_info is None:
        return None, _failure(
            action="TERMINAL_UNAVAILABLE",
            message=(
                "MT5 terminal information is unavailable."
            ),
            symbol=clean_symbol,
        )

    if (
        getattr(
            terminal_info,
            "connected",
            True,
        )
        is not True
    ):
        return None, _failure(
            action="TERMINAL_NOT_CONNECTED",
            message="MT5 terminal is not connected.",
            symbol=clean_symbol,
        )

    account_info = mt5.account_info()

    if account_info is None:
        return None, _failure(
            action="ACCOUNT_UNAVAILABLE",
            message=(
                "MT5 account information is unavailable."
            ),
            symbol=clean_symbol,
        )

    if (
        getattr(
            account_info,
            "trade_allowed",
            True,
        )
        is not True
    ):
        return None, _failure(
            action="ACCOUNT_TRADING_DISABLED",
            message=(
                "Trading is not allowed on the "
                "connected MT5 account."
            ),
            symbol=clean_symbol,
        )

    symbol_info = mt5.symbol_info(
        clean_symbol
    )

    if symbol_info is None:
        return None, _failure(
            action="SYMBOL_NOT_FOUND",
            message=(
                f"MT5 could not find symbol "
                f"{clean_symbol}."
            ),
            symbol=clean_symbol,
        )

    if (
        getattr(
            symbol_info,
            "visible",
            False,
        )
        is not True
    ):
        selected = mt5.symbol_select(
            clean_symbol,
            True,
        )

        if not selected:
            return None, _failure(
                action="SYMBOL_SELECT_FAILED",
                message=(
                    f"Could not add {clean_symbol} "
                    "to Market Watch."
                ),
                symbol=clean_symbol,
            )

        symbol_info = mt5.symbol_info(
            clean_symbol
        )

        if symbol_info is None:
            return None, _failure(
                action="SYMBOL_INFO_FAILED",
                message=(
                    "Could not reload symbol information "
                    f"for {clean_symbol}."
                ),
                symbol=clean_symbol,
            )

    disabled_mode = getattr(
        mt5,
        "SYMBOL_TRADE_MODE_DISABLED",
        None,
    )

    if (
        disabled_mode is not None
        and getattr(
            symbol_info,
            "trade_mode",
            None,
        )
        == disabled_mode
    ):
        return None, _failure(
            action="SYMBOL_TRADING_DISABLED",
            message=(
                f"Trading is disabled for "
                f"{clean_symbol}."
            ),
            symbol=clean_symbol,
        )

    return symbol_info, None


# ======================================================================
# VOLUME VALIDATION
# ======================================================================

def _validate_volume(
    symbol_info: Any,
    requested_volume: Any,
) -> tuple[float | None, dict[str, Any] | None]:
    symbol = getattr(
        symbol_info,
        "name",
        None,
    )

    try:
        volume = float(
            requested_volume
        )
    except (TypeError, ValueError):
        return None, _failure(
            action="INVALID_VOLUME",
            message="Lot size must be numeric.",
            symbol=symbol,
        )

    if (
        not math.isfinite(volume)
        or volume <= 0
    ):
        return None, _failure(
            action="INVALID_VOLUME",
            message=(
                "Lot size must be a positive "
                "finite number."
            ),
            symbol=symbol,
        )

    volume_min = float(
        getattr(
            symbol_info,
            "volume_min",
            0.0,
        )
        or 0.0
    )

    volume_max = float(
        getattr(
            symbol_info,
            "volume_max",
            0.0,
        )
        or 0.0
    )

    volume_step = float(
        getattr(
            symbol_info,
            "volume_step",
            0.0,
        )
        or 0.0
    )

    tolerance = max(
        volume_step * 1e-6,
        1e-9,
    )

    if (
        volume_min > 0
        and volume < volume_min - tolerance
    ):
        return None, _failure(
            action="VOLUME_BELOW_MINIMUM",
            message=(
                f"Requested volume {volume} is below "
                f"the broker minimum of {volume_min}."
            ),
            symbol=symbol,
            requested_volume=volume,
            volume_min=volume_min,
        )

    if (
        volume_max > 0
        and volume > volume_max + tolerance
    ):
        return None, _failure(
            action="VOLUME_ABOVE_MAXIMUM",
            message=(
                f"Requested volume {volume} is above "
                f"the broker maximum of {volume_max}."
            ),
            symbol=symbol,
            requested_volume=volume,
            volume_max=volume_max,
        )

    if volume_step > 0:
        base_volume = (
            volume_min
            if volume_min > 0
            else 0.0
        )

        step_count = (
            volume - base_volume
        ) / volume_step

        if (
            abs(
                step_count
                - round(step_count)
            )
            > 1e-6
        ):
            return None, _failure(
                action="INVALID_VOLUME_STEP",
                message=(
                    f"Requested volume {volume} does "
                    "not match the broker volume step "
                    f"of {volume_step}."
                ),
                symbol=symbol,
                requested_volume=volume,
                volume_step=volume_step,
            )

    return round(volume, 8), None


# ======================================================================
# TICK VALIDATION
# ======================================================================

def _get_trade_tick(
    symbol: str,
    direction: str,
) -> tuple[
    Any | None,
    float | None,
    dict[str, Any] | None,
]:
    tick = mt5.symbol_info_tick(
        symbol
    )

    if tick is None:
        return None, None, _failure(
            action="TICK_UNAVAILABLE",
            message=(
                f"Could not obtain tick data "
                f"for {symbol}."
            ),
            symbol=symbol,
            direction=direction,
        )

    if direction == "BUY":
        price = getattr(
            tick,
            "ask",
            None,
        )
    else:
        price = getattr(
            tick,
            "bid",
            None,
        )

    try:
        price = float(price)
    except (TypeError, ValueError):
        price = 0.0

    if (
        not math.isfinite(price)
        or price <= 0
    ):
        return None, None, _failure(
            action="INVALID_TICK_PRICE",
            message=(
                f"MT5 returned an invalid "
                f"{direction} price for {symbol}."
            ),
            symbol=symbol,
            direction=direction,
        )

    tick_time = getattr(
        tick,
        "time",
        None,
    )

    try:
        tick_time = float(
            tick_time
        )
    except (TypeError, ValueError):
        tick_time = 0.0

    try:
        maximum_tick_age = float(
            getattr(
                settings,
                "MAX_ORDER_TICK_AGE_SECONDS",
                30.0,
            )
        )
    except (TypeError, ValueError):
        maximum_tick_age = 30.0

    if (
        tick_time > 0
        and maximum_tick_age >= 0
    ):
        tick_age = max(
            0.0,
            time.time() - tick_time,
        )

        if tick_age > maximum_tick_age:
            return None, None, _failure(
                action="STALE_TICK",
                message=(
                    f"Tick data for {symbol} is too "
                    f"old: {tick_age:.2f} seconds."
                ),
                symbol=symbol,
                direction=direction,
                tick_age_seconds=round(
                    tick_age,
                    4,
                ),
                max_tick_age_seconds=(
                    maximum_tick_age
                ),
            )

    return tick, price, None


# ======================================================================
# FILLING MODE
# ======================================================================

def _select_filling_mode(
    symbol_info: Any,
) -> int | None:
    """
    Selects a broker-supported filling policy.

    FOK is preferred so the requested volume is either
    fully filled or rejected. IOC is used when FOK is
    unavailable. RETURN is used only when allowed by the
    symbol execution mode.
    """

    filling_flags = int(
        getattr(
            symbol_info,
            "filling_mode",
            0,
        )
        or 0
    )

    symbol_fok_flag = int(
        getattr(
            mt5,
            "SYMBOL_FILLING_FOK",
            1,
        )
    )

    symbol_ioc_flag = int(
        getattr(
            mt5,
            "SYMBOL_FILLING_IOC",
            2,
        )
    )

    if (
        filling_flags
        & symbol_fok_flag
    ):
        return mt5.ORDER_FILLING_FOK

    if (
        filling_flags
        & symbol_ioc_flag
    ):
        return mt5.ORDER_FILLING_IOC

    market_execution = getattr(
        mt5,
        "SYMBOL_TRADE_EXECUTION_MARKET",
        None,
    )

    execution_mode = getattr(
        symbol_info,
        "trade_exemode",
        None,
    )

    if (
        market_execution is None
        or execution_mode
        != market_execution
    ):
        return mt5.ORDER_FILLING_RETURN

    return None


# ======================================================================
# REQUEST BUILDING
# ======================================================================

def _build_market_request(
    *,
    symbol_info: Any,
    volume: float,
    direction: str,
    price: float,
    comment: str,
    position_ticket: int | None = None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    filling_mode = _select_filling_mode(
        symbol_info
    )

    if filling_mode is None:
        return None, _failure(
            action="FILLING_MODE_UNAVAILABLE",
            message=(
                "No supported market-order filling "
                f"mode was found for {symbol_info.name}."
            ),
            symbol=symbol_info.name,
            direction=direction,
        )

    if direction == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
    else:
        order_type = mt5.ORDER_TYPE_SELL

    request: dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol_info.name,
        "volume": volume,
        "type": order_type,
        "deviation": _get_deviation_points(),
        "magic": _get_magic_number(),
        "comment": str(comment)[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    market_execution = getattr(
        mt5,
        "SYMBOL_TRADE_EXECUTION_MARKET",
        None,
    )

    execution_mode = getattr(
        symbol_info,
        "trade_exemode",
        None,
    )

    # A requested price is not required for symbols
    # using Market Execution.
    if (
        market_execution is None
        or execution_mode
        != market_execution
    ):
        request["price"] = price

    if position_ticket is not None:
        request["position"] = int(
            position_ticket
        )

    return request, None


# ======================================================================
# ORDER CHECK
# ======================================================================

def _check_request(
    request: dict[str, Any],
    *,
    symbol: str,
    direction: str,
) -> dict[str, Any] | None:
    check_result = mt5.order_check(
        request
    )

    if check_result is None:
        return _failure(
            action="ORDER_CHECK_FAILED",
            message=(
                "MT5 order_check returned no result."
            ),
            symbol=symbol,
            direction=direction,
            request=request,
        )

    check_retcode = getattr(
        check_result,
        "retcode",
        None,
    )

    try:
        check_retcode = int(
            check_retcode
        )
    except (TypeError, ValueError):
        check_retcode = None

    # A successful MT5 order_check returns retcode 0.
    if check_retcode != 0:
        return _failure(
            action="ORDER_CHECK_REJECTED",
            message=(
                "MT5 order_check rejected the request. "
                f"Comment: "
                f"{getattr(check_result, 'comment', '')}"
            ),
            symbol=symbol,
            direction=direction,
            request=request,
            retcode=check_retcode,
            check_result=_to_dict(
                check_result
            ),
        )

    return None


# ======================================================================
# ORDER SEND
# ======================================================================

def _send_request(
    request: dict[str, Any],
    *,
    symbol: str,
    direction: str,
) -> dict[str, Any]:
    result = mt5.order_send(
        request
    )

    if result is None:
        return _failure(
            action="ORDER_SEND_FAILED",
            message=(
                "MT5 order_send returned no result."
            ),
            symbol=symbol,
            direction=direction,
            request=request,
        )

    result_data = _to_dict(
        result
    )

    retcode_value = getattr(
        result,
        "retcode",
        result_data.get("retcode"),
    )

    try:
        retcode = int(
            retcode_value
        )
    except (TypeError, ValueError):
        retcode = None

    success = (
        retcode is not None
        and retcode
        in _successful_retcodes()
    )

    comment = str(
        getattr(
            result,
            "comment",
            result_data.get(
                "comment",
                "",
            ),
        )
        or ""
    )

    return {
        "success": success,
        "action": (
            "ORDER_ACCEPTED"
            if success
            else "ORDER_REJECTED"
        ),
        "message": (
            comment
            or (
                "MT5 accepted the order."
                if success
                else "MT5 rejected the order."
            )
        ),
        "symbol": symbol,
        "direction": direction,
        "retcode": retcode,
        "order": result_data.get(
            "order"
        ),
        "deal": result_data.get(
            "deal"
        ),
        "volume": result_data.get(
            "volume"
        ),
        "price": result_data.get(
            "price"
        ),
        "request": request,
        "mt5_result": result,
        "mt5_result_data": result_data,
        "last_error": _last_error_text(),
    }


# ======================================================================
# COMPLETE MARKET REQUEST
# ======================================================================

def _execute_market_request(
    *,
    symbol: str,
    volume: Any,
    direction: str,
    comment: str,
    position_ticket: int | None = None,
) -> dict[str, Any]:
    safety_result = (
        _check_local_live_safety(
            symbol,
            direction,
        )
    )

    if not safety_result.get(
        "success",
        False,
    ):
        return safety_result

    symbol_info, symbol_error = (
        _prepare_symbol(symbol)
    )

    if symbol_error is not None:
        symbol_error["direction"] = (
            direction
        )
        return symbol_error

    normalized_volume, volume_error = (
        _validate_volume(
            symbol_info,
            volume,
        )
    )

    if volume_error is not None:
        volume_error["direction"] = (
            direction
        )
        return volume_error

    _, price, tick_error = (
        _get_trade_tick(
            symbol_info.name,
            direction,
        )
    )

    if tick_error is not None:
        return tick_error

    request, request_error = (
        _build_market_request(
            symbol_info=symbol_info,
            volume=normalized_volume,
            direction=direction,
            price=price,
            comment=comment,
            position_ticket=position_ticket,
        )
    )

    if request_error is not None:
        return request_error

    check_error = _check_request(
        request,
        symbol=symbol_info.name,
        direction=direction,
    )

    if check_error is not None:
        return check_error

    # Exactly one order_send call is made.
    # Automatic retries are intentionally avoided because
    # retrying a market request could duplicate a trade.
    return _send_request(
        request,
        symbol=symbol_info.name,
        direction=direction,
    )


# ======================================================================
# PUBLIC ORDER FUNCTIONS
# ======================================================================

def open_buy(
    symbol: str,
    lot_size: Any,
) -> dict[str, Any]:
    return _execute_market_request(
        symbol=symbol,
        volume=lot_size,
        direction="BUY",
        comment="AI Gold Bot BUY",
    )


def open_sell(
    symbol: str,
    lot_size: Any,
) -> dict[str, Any]:
    return _execute_market_request(
        symbol=symbol,
        volume=lot_size,
        direction="SELL",
        comment="AI Gold Bot SELL",
    )


def close_position(
    position: Any,
) -> dict[str, Any]:
    if position is None:
        return _failure(
            action="POSITION_MISSING",
            message=(
                "No MT5 position was provided."
            ),
        )

    symbol = str(
        getattr(
            position,
            "symbol",
            "",
        )
        or ""
    ).strip().upper()

    ticket = getattr(
        position,
        "ticket",
        None,
    )

    volume = getattr(
        position,
        "volume",
        None,
    )

    position_type = getattr(
        position,
        "type",
        None,
    )

    if not symbol:
        return _failure(
            action="POSITION_SYMBOL_MISSING",
            message=(
                "The position symbol is missing."
            ),
        )

    try:
        ticket = int(ticket)
    except (TypeError, ValueError):
        return _failure(
            action="POSITION_TICKET_INVALID",
            message=(
                "The position ticket is missing "
                "or invalid."
            ),
            symbol=symbol,
        )

    buy_position_type = getattr(
        mt5,
        "POSITION_TYPE_BUY",
        mt5.ORDER_TYPE_BUY,
    )

    sell_position_type = getattr(
        mt5,
        "POSITION_TYPE_SELL",
        mt5.ORDER_TYPE_SELL,
    )

    if position_type in {
        buy_position_type,
        mt5.ORDER_TYPE_BUY,
    }:
        close_direction = "SELL"

    elif position_type in {
        sell_position_type,
        mt5.ORDER_TYPE_SELL,
    }:
        close_direction = "BUY"

    else:
        return _failure(
            action="POSITION_TYPE_INVALID",
            message=(
                "The position type is not "
                "BUY or SELL."
            ),
            symbol=symbol,
        )

    return _execute_market_request(
        symbol=symbol,
        volume=volume,
        direction=close_direction,
        comment="AI Gold Bot CLOSE",
        position_ticket=ticket,
    )

