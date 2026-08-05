from collections.abc import Mapping
from typing import Any

from config import settings

from services.execution.position_limit_checker import (
    get_bot_open_positions,
)
from services.execution.order_manager import close_position


# ======================================================================
# SAFE VALUE HELPERS
# ======================================================================

def _get(
    source: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Reads a value from either a dictionary or an object.
    """

    if source is None:
        return default

    if isinstance(source, Mapping):
        return source.get(key, default)

    return getattr(source, key, default)


def _normalize_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "yes",
            "1",
            "success",
            "accepted",
            "closed",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "failed",
            "rejected",
            "blocked",
        }:
            return False

    if value is None:
        return default

    return bool(value)


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _position_ticket(
    position: Any,
) -> Any:
    return _get(
        position,
        "ticket",
        "UNKNOWN",
    )


def _position_profit(
    position: Any,
) -> float:
    return _safe_float(
        _get(
            position,
            "profit",
            0.0,
        ),
        default=0.0,
    )


def _get_profit_target() -> float:
    target = _safe_float(
        getattr(
            settings,
            "PROFIT_TARGET_USD",
            2.00,
        ),
        default=2.00,
    )

    return max(0.0, target)


# ======================================================================
# RESULT BUILDERS
# ======================================================================

def _make_result(
    *,
    action: str,
    message: str,
    symbol: str,
    positions_checked: int = 0,
    positions_at_target: int = 0,
    closed_count: int = 0,
    failed_count: int = 0,
    target_usd: float | None = None,
    close_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "message": message,
        "symbol": symbol,
        "positions_checked": positions_checked,
        "positions_at_target": positions_at_target,
        "closed_count": closed_count,
        "failed_count": failed_count,
        "target_usd": target_usd,
        "close_results": close_results or [],
    }


# ======================================================================
# LEGACY MT5 RESULT SUPPORT
# ======================================================================

def _successful_mt5_retcodes() -> set[int]:
    """
    Supports older close_position implementations that returned
    a raw MT5 result instead of the new structured dictionary.
    """

    try:
        import MetaTrader5 as mt5

        names = (
            "TRADE_RETCODE_PLACED",
            "TRADE_RETCODE_DONE",
            "TRADE_RETCODE_DONE_PARTIAL",
        )

        return {
            int(getattr(mt5, name))
            for name in names
            if hasattr(mt5, name)
        }

    except Exception:
        # Compatibility fallback for common MT5 success codes.
        return {10008, 10009, 10010}


def _interpret_close_result(
    close_result: Any,
) -> dict[str, Any]:
    """
    Interprets both:
    - the new structured order-manager response;
    - an older raw MT5 order result.
    """

    if close_result is None:
        return {
            "success": False,
            "action": "NO_CLOSE_RESULT",
            "message": (
                "Close request returned no result."
            ),
            "retcode": None,
        }

    explicit_success = _get(
        close_result,
        "success",
        None,
    )

    action = str(
        _get(
            close_result,
            "action",
            "UNKNOWN",
        )
        or "UNKNOWN"
    )

    message = str(
        _get(
            close_result,
            "message",
            _get(
                close_result,
                "comment",
                "",
            ),
        )
        or ""
    )

    retcode = _get(
        close_result,
        "retcode",
        None,
    )

    if explicit_success is not None:
        success = _normalize_bool(
            explicit_success,
            default=False,
        )

        return {
            "success": success,
            "action": action,
            "message": (
                message
                or (
                    "Position closed successfully."
                    if success
                    else "Position close failed."
                )
            ),
            "retcode": retcode,
        }

    if retcode is not None:
        try:
            numeric_retcode = int(retcode)
        except (TypeError, ValueError):
            numeric_retcode = None

        success = (
            numeric_retcode
            in _successful_mt5_retcodes()
        )

        return {
            "success": success,
            "action": (
                "POSITION_CLOSED"
                if success
                else "POSITION_CLOSE_REJECTED"
            ),
            "message": (
                message
                or (
                    "Position closed successfully."
                    if success
                    else (
                        "MT5 rejected the position close "
                        f"with retcode {numeric_retcode}."
                    )
                )
            ),
            "retcode": numeric_retcode,
        }

    return {
        "success": False,
        "action": "UNVERIFIED_CLOSE_RESULT",
        "message": (
            "Position-close result could not be verified."
        ),
        "retcode": None,
    }


# ======================================================================
# PROFIT MANAGER
# ======================================================================

def manage_profit_targets(
    symbol: str,
) -> dict[str, Any]:
    """
    Checks this bot's open MT5 positions for the configured symbol.

    A position is eligible to close when:

        position.profit >= PROFIT_TARGET_USD

    Live positions are closed only when the complete live-trading
    safety configuration permits it.

    This function does not manage simulated paper positions.
    """

    clean_symbol = str(
        symbol or ""
    ).strip().upper()

    if not clean_symbol:
        return _make_result(
            action="INVALID_SYMBOL",
            message="Profit manager received an invalid symbol.",
            symbol="UNKNOWN",
        )

    target_usd = _get_profit_target()

    try:
        positions = get_bot_open_positions(
            clean_symbol
        )
    except Exception as error:
        return _make_result(
            action="POSITION_LOOKUP_FAILED",
            message=(
                "Could not retrieve bot positions: "
                f"{error}"
            ),
            symbol=clean_symbol,
            target_usd=target_usd,
        )

    if positions is None:
        positions = []

    try:
        positions = list(positions)
    except TypeError:
        return _make_result(
            action="INVALID_POSITION_RESULT",
            message=(
                "Position checker returned an invalid result."
            ),
            symbol=clean_symbol,
            target_usd=target_usd,
        )

    positions_checked = len(positions)

    if not positions:
        return _make_result(
            action="NO_POSITIONS",
            message=(
                f"No bot positions found for {clean_symbol}."
            ),
            symbol=clean_symbol,
            positions_checked=0,
            target_usd=target_usd,
        )

    positions_at_target: list[Any] = []

    for position in positions:
        profit = _position_profit(
            position
        )

        if profit >= target_usd:
            positions_at_target.append(
                position
            )

    target_count = len(
        positions_at_target
    )

    if not positions_at_target:
        return _make_result(
            action="CHECKED",
            message=(
                f"{positions_checked} bot position(s) checked. "
                "No position reached the profit target of "
                f"${target_usd:.2f}."
            ),
            symbol=clean_symbol,
            positions_checked=positions_checked,
            positions_at_target=0,
            target_usd=target_usd,
        )

    # ==================================================================
    # SAFETY BLOCKS
    # ==================================================================

    if (
        getattr(
            settings,
            "EMERGENCY_STOP",
            False,
        )
        is True
    ):
        return _make_result(
            action="EMERGENCY_STOP_BLOCKED",
            message=(
                f"{target_count} position(s) reached the profit "
                "target, but closing is blocked because the "
                "emergency stop is active."
            ),
            symbol=clean_symbol,
            positions_checked=positions_checked,
            positions_at_target=target_count,
            target_usd=target_usd,
        )

    if (
        getattr(
            settings,
            "ENABLE_LIVE_TRADING",
            False,
        )
        is not True
    ):
        return _make_result(
            action="SAFE_MODE_BLOCKED",
            message=(
                f"{target_count} position(s) reached the profit "
                "target, but live position closing is blocked "
                "because ENABLE_LIVE_TRADING=False."
            ),
            symbol=clean_symbol,
            positions_checked=positions_checked,
            positions_at_target=target_count,
            target_usd=target_usd,
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
        return _make_result(
            action="LIVE_CONFIRMATION_BLOCKED",
            message=(
                f"{target_count} position(s) reached the profit "
                "target, but live-trading confirmation is "
                "missing or invalid."
            ),
            symbol=clean_symbol,
            positions_checked=positions_checked,
            positions_at_target=target_count,
            target_usd=target_usd,
        )

    # ==================================================================
    # CLOSE POSITIONS
    # ==================================================================

    closed_count = 0
    failed_count = 0
    close_results: list[dict[str, Any]] = []
    summary_messages: list[str] = []

    for position in positions_at_target:
        ticket = _position_ticket(
            position
        )

        profit = _position_profit(
            position
        )

        try:
            raw_result = close_position(
                position
            )

            interpreted = _interpret_close_result(
                raw_result
            )

            result_entry = {
                "ticket": ticket,
                "profit_usd": round(
                    profit,
                    2,
                ),
                "success": interpreted[
                    "success"
                ],
                "action": interpreted[
                    "action"
                ],
                "message": interpreted[
                    "message"
                ],
                "retcode": interpreted[
                    "retcode"
                ],
                "raw_result": raw_result,
            }

            close_results.append(
                result_entry
            )

            if interpreted["success"]:
                closed_count += 1

                summary_messages.append(
                    f"Ticket {ticket}: closed successfully "
                    f"at profit ${profit:.2f}."
                )
            else:
                failed_count += 1

                summary_messages.append(
                    f"Ticket {ticket}: close failed. "
                    f"{interpreted['message']}"
                )

        except Exception as error:
            failed_count += 1

            close_results.append(
                {
                    "ticket": ticket,
                    "profit_usd": round(
                        profit,
                        2,
                    ),
                    "success": False,
                    "action": "CLOSE_EXCEPTION",
                    "message": str(error),
                    "retcode": None,
                    "exception_type": (
                        type(error).__name__
                    ),
                }
            )

            summary_messages.append(
                f"Ticket {ticket}: close error: {error}"
            )

    # ==================================================================
    # FINAL RESULT
    # ==================================================================

    if closed_count == target_count:
        final_action = "ALL_TARGETS_CLOSED"

    elif closed_count > 0:
        final_action = "PARTIAL_CLOSE_SUCCESS"

    else:
        final_action = "CLOSE_FAILED"

    return _make_result(
        action=final_action,
        message=(
            f"Positions checked: {positions_checked}. "
            f"At target: {target_count}. "
            f"Closed: {closed_count}. "
            f"Failed: {failed_count}. "
            + " | ".join(summary_messages)
        ),
        symbol=clean_symbol,
        positions_checked=positions_checked,
        positions_at_target=target_count,
        closed_count=closed_count,
        failed_count=failed_count,
        target_usd=target_usd,
        close_results=close_results,
    )