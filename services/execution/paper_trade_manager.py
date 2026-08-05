
import json
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from config import settings
from services.utils.atomic_json import atomic_write_json


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# ======================================================================
# SAFE VALUE HELPERS
# ======================================================================

def _get_value(
    source: Any,
    *keys: str,
    default: Any = None,
) -> Any:
    if source is None:
        return default

    for key in keys:
        if isinstance(source, Mapping):
            value = source.get(key)
        else:
            value = getattr(source, key, None)

        if value is not None:
            return value

    return default


def _normalize_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    normalized = str(value).strip().upper()
    return normalized or default


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "yes", "1", "enabled"}:
            return True

        if normalized in {"false", "no", "0", "disabled"}:
            return False

    if value is None:
        return default

    return bool(value)


# ======================================================================
# FILE MANAGEMENT
# ======================================================================

def _get_log_folder() -> str:
    base_log_path = getattr(
        settings,
        "LOG_FILE_PATH",
        "logs/bot_cycle_log.csv",
    )

    base_log_folder = (
        os.path.dirname(base_log_path)
        or "logs"
    )

    if getattr(
        settings,
        "USE_DAILY_LOG_FOLDERS",
        False,
    ):
        date_format = getattr(
            settings,
            "LOG_DATE_FORMAT",
            "%Y-%m-%d",
        )

        today_folder = datetime.now().strftime(
            date_format
        )

        base_log_folder = os.path.join(
            base_log_folder,
            today_folder,
        )

    os.makedirs(
        base_log_folder,
        exist_ok=True,
    )

    return base_log_folder


def get_paper_trade_file_path() -> str:
    return os.path.join(
        _get_log_folder(),
        "paper_trades.json",
    )


def _load_paper_trades() -> list[dict[str, Any]]:
    path = get_paper_trade_file_path()

    if not os.path.exists(path):
        return []

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(
                "Paper-trade JSON root must be a list."
            )

        return [
            trade
            for trade in data
            if isinstance(trade, dict)
        ]

    except Exception:
        # Preserve the damaged file instead of silently overwriting it.
        backup_path = (
            f"{path}.corrupt-"
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

        try:
            os.replace(
                path,
                backup_path,
            )
        except OSError:
            pass

        return []


def _save_paper_trades(
    trades: list[dict[str, Any]],
) -> str:
    """
    Saves atomically so an interrupted write does not destroy the journal.
    """

    path = get_paper_trade_file_path()
    return atomic_write_json(path, trades, indent=4)


# ======================================================================
# TRADE EXTRACTION
# ======================================================================

def _get_open_paper_trades(
    trades: list[dict[str, Any]],
    symbol: str,
) -> list[dict[str, Any]]:
    magic_number = getattr(
        settings,
        "MAGIC_NUMBER",
        None,
    )

    return [
        trade
        for trade in trades
        if _normalize_text(
            trade.get("symbol")
        )
        == symbol
        and _normalize_text(
            trade.get("status")
        )
        == "OPEN"
        and trade.get("magic_number")
        == magic_number
    ]


def _extract_snapshot(
    cycle: Any,
) -> Any:
    return _get_value(
        cycle,
        "snapshot",
        "market_snapshot",
        default={},
    )


def _extract_symbol(
    cycle: Any,
) -> str:
    snapshot = _extract_snapshot(cycle)

    symbol = _get_value(
        cycle,
        "symbol",
        default=None,
    )

    if not symbol:
        symbol = _get_value(
            snapshot,
            "symbol",
            default=getattr(
                settings,
                "SYMBOL",
                "XAUUSD",
            ),
        )

    return _normalize_text(
        symbol,
        default="XAUUSD",
    )


def _extract_price_data(
    cycle: Any,
) -> dict[str, float | None]:
    snapshot = _extract_snapshot(cycle)

    price = _get_value(
        cycle,
        "price",
        "current_price",
        default=None,
    )

    if price is None:
        price = _get_value(
            snapshot,
            "price",
            "current_price",
            default=None,
        )

    bid = _get_value(
        price,
        "bid",
        default=None,
    )

    ask = _get_value(
        price,
        "ask",
        default=None,
    )

    bid_value = _safe_float(
        bid,
        default=0.0,
    )

    ask_value = _safe_float(
        ask,
        default=0.0,
    )

    if (
        bid_value > 0
        and ask_value > 0
    ):
        return {
            "bid": bid_value,
            "ask": ask_value,
            "mid": (
                bid_value + ask_value
            ) / 2,
            "spread": ask_value - bid_value,
        }

    scalar_price = _safe_float(
        price,
        default=0.0,
    )

    if scalar_price > 0:
        return {
            "bid": scalar_price,
            "ask": scalar_price,
            "mid": scalar_price,
            "spread": 0.0,
        }

    return {
        "bid": None,
        "ask": None,
        "mid": None,
        "spread": None,
    }


def _extract_dry_run_plan(
    cycle: Any,
) -> Any:
    return _get_value(
        cycle,
        "dry_run_plan",
        "dry_run_trade_plan",
        "dry_run_result",
        default={},
    )


# ======================================================================
# PAPER PROFIT CALCULATION
# ======================================================================

def _get_contract_size(
    cycle: Any,
) -> float:
    snapshot = _extract_snapshot(cycle)

    contract_size = _get_value(
        snapshot,
        "contract_size",
        default=None,
    )

    if contract_size is None:
        contract_size = getattr(
            settings,
            "PAPER_CONTRACT_SIZE",
            100.0,
        )

    value = _safe_float(
        contract_size,
        default=100.0,
    )

    return value if value > 0 else 100.0


def _entry_price(
    direction: str,
    prices: dict[str, float | None],
) -> float | None:
    # A BUY enters at ask; a SELL enters at bid.
    if direction == "BUY":
        return prices["ask"]

    if direction == "SELL":
        return prices["bid"]

    return None


def _exit_price(
    direction: str,
    prices: dict[str, float | None],
) -> float | None:
    # A BUY closes at bid; a SELL closes at ask.
    if direction == "BUY":
        return prices["bid"]

    if direction == "SELL":
        return prices["ask"]

    return None


def _calculate_profit(
    direction: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    contract_size: float,
) -> float:
    volume_value = (
        lot_size * contract_size
    )

    if direction == "BUY":
        return (
            exit_price - entry_price
        ) * volume_value

    if direction == "SELL":
        return (
            entry_price - exit_price
        ) * volume_value

    return 0.0


# ======================================================================
# TRADE CLOSING HELPERS
# ======================================================================

def _parse_datetime(
    value: Any,
) -> datetime | None:
    try:
        return datetime.strptime(
            str(value),
            DATETIME_FORMAT,
        )
    except (TypeError, ValueError):
        return None


def _close_trade(
    trade: dict[str, Any],
    close_price: float,
    profit: float,
    reason: str,
) -> None:
    trade["status"] = "CLOSED"
    trade["closed_at"] = datetime.now().strftime(
        DATETIME_FORMAT
    )
    trade["close_price"] = round(
        close_price,
        5,
    )
    trade["final_profit_usd"] = round(
        profit,
        2,
    )
    trade["unrealized_profit_usd"] = 0.0
    trade["close_reason"] = reason


def _is_opposite_signal(
    open_direction: str,
    dry_run_action: str,
) -> bool:
    return (
        open_direction == "BUY"
        and dry_run_action == "WOULD_SELL"
    ) or (
        open_direction == "SELL"
        and dry_run_action == "WOULD_BUY"
    )


# ======================================================================
# PAPER TRADE MANAGER
# ======================================================================

def manage_paper_trade(
    cycle: Any,
) -> dict[str, Any]:
    """
    Manages safe simulated XAUUSD trades.

    Simulated prices include spread:
    - BUY opens at ask and closes at bid;
    - SELL opens at bid and closes at ask.

    This function never sends an MT5 order.
    """

    symbol = _extract_symbol(cycle)
    prices = _extract_price_data(cycle)
    dry_run_plan = _extract_dry_run_plan(cycle)

    if getattr(
        settings,
        "ENABLE_LIVE_TRADING",
        False,
    ):
        return {
            "action": "SKIPPED",
            "message": (
                "Paper trading skipped because "
                "live trading is enabled."
            ),
            "symbol": symbol,
            "open_paper_trades": 0,
            "closed_trade": False,
            "opened_trade": False,
            "paper_profit": 0.0,
        }

    if (
        prices["bid"] is None
        or prices["ask"] is None
    ):
        return {
            "action": "NO_PRICE",
            "message": (
                "Cannot manage paper trades because "
                "valid bid/ask prices are missing."
            ),
            "symbol": symbol,
            "open_paper_trades": 0,
            "closed_trade": False,
            "opened_trade": False,
            "paper_profit": 0.0,
        }

    trades = _load_paper_trades()

    dry_run_action = _normalize_text(
        _get_value(
            dry_run_plan,
            "action",
            "dry_run_action",
            default="NO_TRADE",
        ),
        default="NO_TRADE",
    )

    dry_run_direction = _normalize_text(
        _get_value(
            dry_run_plan,
            "direction",
            "dry_run_direction",
            default="NONE",
        ),
        default="NONE",
    )

    profit_target = max(
        0.0,
        _safe_float(
            getattr(
                settings,
                "PROFIT_TARGET_USD",
                2.00,
            ),
            default=2.00,
        ),
    )

    stop_loss = max(
        0.0,
        _safe_float(
            getattr(
                settings,
                "PAPER_STOP_LOSS_USD",
                2.00,
            ),
            default=2.00,
        ),
    )

    max_hold_seconds = max(
        0,
        _safe_int(
            getattr(
                settings,
                "PAPER_MAX_HOLD_SECONDS",
                300,
            ),
            default=300,
        ),
    )

    close_on_opposite = _safe_bool(
        getattr(
            settings,
            "PAPER_CLOSE_ON_OPPOSITE_SIGNAL",
            True,
        ),
        default=True,
    )

    lot_size = _safe_float(
        getattr(
            settings,
            "LOT_SIZE",
            0.01,
        ),
        default=0.01,
    )

    contract_size = _get_contract_size(
        cycle
    )

    max_positions = max(
        1,
        _safe_int(
            getattr(
                settings,
                "MAX_OPEN_POSITIONS",
                1,
            ),
            default=1,
        ),
    )

    now = datetime.now()
    closed_trade = False
    opened_trade = False
    closed_count = 0
    close_messages: list[str] = []

    # ==================================================================
    # MONITOR EXISTING TRADES
    # ==================================================================

    open_trades = _get_open_paper_trades(
        trades,
        symbol,
    )

    for trade in open_trades:
        direction = _normalize_text(
            trade.get("direction"),
            default="NONE",
        )

        entry_price = _safe_float(
            trade.get("entry_price"),
            default=0.0,
        )

        trade_lot_size = _safe_float(
            trade.get("lot_size"),
            default=lot_size,
        )

        trade_contract_size = _safe_float(
            trade.get("contract_size"),
            default=contract_size,
        )

        close_price = _exit_price(
            direction,
            prices,
        )

        if (
            entry_price <= 0
            or close_price is None
            or trade_lot_size <= 0
        ):
            trade["last_checked_at"] = now.strftime(
                DATETIME_FORMAT
            )
            trade["monitoring_error"] = (
                "Invalid entry, exit, or volume data."
            )
            continue

        profit = _calculate_profit(
            direction=direction,
            entry_price=entry_price,
            exit_price=close_price,
            lot_size=trade_lot_size,
            contract_size=trade_contract_size,
        )

        trade["last_checked_at"] = now.strftime(
            DATETIME_FORMAT
        )
        trade["last_price"] = round(
            close_price,
            5,
        )
        trade["last_bid"] = prices["bid"]
        trade["last_ask"] = prices["ask"]
        trade["unrealized_profit_usd"] = round(
            profit,
            2,
        )

        opened_at = _parse_datetime(
            trade.get("opened_at")
        )

        hold_seconds = (
            max(
                0,
                int(
                    (
                        now - opened_at
                    ).total_seconds()
                ),
            )
            if opened_at
            else 0
        )

        trade["hold_seconds"] = hold_seconds

        close_reason = None

        if profit >= profit_target:
            close_reason = (
                "Paper profit target reached"
            )

        elif profit <= -stop_loss:
            close_reason = (
                "Paper stop loss reached"
            )

        elif (
            max_hold_seconds > 0
            and hold_seconds
            >= max_hold_seconds
        ):
            close_reason = (
                "Paper max hold time reached"
            )

        elif (
            close_on_opposite
            and _is_opposite_signal(
                direction,
                dry_run_action,
            )
        ):
            close_reason = (
                "Opposite dry-run signal appeared"
            )

        if close_reason:
            _close_trade(
                trade=trade,
                close_price=close_price,
                profit=profit,
                reason=close_reason,
            )

            closed_trade = True
            closed_count += 1

            close_messages.append(
                f"Closed {direction}: {close_reason}. "
                f"Profit: ${profit:.2f}."
            )

    # ==================================================================
    # OPEN NEW TRADE
    # ==================================================================

    open_trades = _get_open_paper_trades(
        trades,
        symbol,
    )

    valid_open_action = dry_run_action in {
        "WOULD_BUY",
        "WOULD_SELL",
    }

    # Prevent immediate churn after closing a trade.
    # A fresh trade may open on the next bot cycle.
    can_open_this_cycle = not closed_trade

    message = ""

    if (
        valid_open_action
        and can_open_this_cycle
        and len(open_trades) < max_positions
    ):
        direction = (
            "BUY"
            if dry_run_action == "WOULD_BUY"
            else "SELL"
        )

        entry_price = _entry_price(
            direction,
            prices,
        )

        if entry_price is not None:
            timestamp = datetime.now()

            new_trade = {
                "id": (
                    "PAPER-"
                    + timestamp.strftime(
                        "%Y%m%d%H%M%S%f"
                    )
                ),
                "status": "OPEN",
                "symbol": symbol,
                "direction": direction,
                "entry_price": round(
                    entry_price,
                    5,
                ),
                "entry_bid": prices["bid"],
                "entry_ask": prices["ask"],
                "entry_spread": prices["spread"],
                "lot_size": lot_size,
                "contract_size": contract_size,
                "magic_number": getattr(
                    settings,
                    "MAGIC_NUMBER",
                    None,
                ),
                "opened_at": timestamp.strftime(
                    DATETIME_FORMAT
                ),
                "source": "DRY_RUN",
                "dry_run_action": dry_run_action,
                "dry_run_direction": dry_run_direction,
                "profit_target_usd": profit_target,
                "stop_loss_usd": stop_loss,
                "max_hold_seconds": max_hold_seconds,
                "last_price": entry_price,
                "last_bid": prices["bid"],
                "last_ask": prices["ask"],
                "unrealized_profit_usd": round(
                    -(
                        prices["spread"]
                        * lot_size
                        * contract_size
                    ),
                    2,
                ),
                "hold_seconds": 0,
            }

            trades.append(new_trade)
            opened_trade = True

            message = (
                f"Opened simulated {direction} paper trade "
                f"at {entry_price:.5f}."
            )

    elif closed_trade:
        message = (
            "No new paper trade opened during the same "
            "cycle in which a trade was closed."
        )

    elif len(open_trades) >= max_positions:
        message = (
            "Maximum open paper-trade limit reached."
        )

    else:
        message = (
            "No paper trade opened. Dry-run action did "
            "not request BUY or SELL."
        )

    if close_messages:
        message = (
            " | ".join(close_messages)
            + " | "
            + message
        )

    # ==================================================================
    # SAVE AND FINAL SUMMARY
    # ==================================================================

    try:
        file_path = _save_paper_trades(
            trades
        )
    except Exception as error:
        return {
            "action": "PAPER_TRADE_SAVE_FAILED",
            "message": (
                f"Paper trades were processed but could "
                f"not be saved: {error}"
            ),
            "symbol": symbol,
            "open_paper_trades": len(
                _get_open_paper_trades(
                    trades,
                    symbol,
                )
            ),
            "closed_trade": closed_trade,
            "opened_trade": opened_trade,
            "closed_count": closed_count,
            "paper_profit": 0.0,
            "file_path": get_paper_trade_file_path(),
        }

    final_open_trades = _get_open_paper_trades(
        trades,
        symbol,
    )

    total_unrealized_profit = sum(
        _safe_float(
            trade.get(
                "unrealized_profit_usd",
                0.0,
            )
        )
        for trade in final_open_trades
    )

    if closed_trade and opened_trade:
        action = (
            "PAPER_TRADE_CLOSED_AND_OPENED"
        )
    elif closed_trade:
        action = "PAPER_TRADE_CLOSED"
    elif opened_trade:
        action = "PAPER_TRADE_OPENED"
    elif final_open_trades:
        action = "PAPER_TRADE_MONITORING"
    else:
        action = "NO_PAPER_TRADE"

    return {
        "action": action,
        "message": message,
        "symbol": symbol,
        "open_paper_trades": len(
            final_open_trades
        ),
        "closed_trade": closed_trade,
        "opened_trade": opened_trade,
        "closed_count": closed_count,
        "paper_profit": round(
            total_unrealized_profit,
            2,
        ),
        "current_bid": prices["bid"],
        "current_ask": prices["ask"],
        "current_spread": prices["spread"],
        "file_path": file_path,
    }

