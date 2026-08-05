from __future__ import annotations

from typing import Any


def _fallback_profit(
    direction: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    contract_size: float,
) -> float:
    notional_per_price_unit = float(lot_size) * float(contract_size)
    if str(direction).upper() == "BUY":
        return (float(exit_price) - float(entry_price)) * notional_per_price_unit
    if str(direction).upper() == "SELL":
        return (float(entry_price) - float(exit_price)) * notional_per_price_unit
    return 0.0


def calculate_scalp_profit(
    *,
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    contract_size: float,
) -> tuple[float, str]:
    """Estimate P/L in account currency, preferring MT5's official calculator.

    MetaTrader5.order_calc_profit reflects the connected account and symbol's
    calculation mode. The deterministic contract-size formula remains a safe
    fallback for synthetic tests or temporary MT5 calculator failures.
    """

    try:
        import MetaTrader5 as mt5  # type: ignore

        order_type = (
            getattr(mt5, "ORDER_TYPE_BUY")
            if str(direction).upper() == "BUY"
            else getattr(mt5, "ORDER_TYPE_SELL")
        )
        result = mt5.order_calc_profit(
            order_type,
            str(symbol),
            float(lot_size),
            float(entry_price),
            float(exit_price),
        )
        if result is not None:
            return float(result), "MT5_ORDER_CALC_PROFIT"
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError):
        pass

    return (
        _fallback_profit(
            direction,
            entry_price,
            exit_price,
            lot_size,
            contract_size,
        ),
        "CONTRACT_SIZE_FALLBACK",
    )


def find_price_for_profit(
    *,
    symbol: str,
    direction: str,
    entry_price: float,
    lot_size: float,
    contract_size: float,
    target_profit_usd: float,
    point: float = 0.01,
) -> tuple[float, str]:
    """Find an approximate close price that corresponds to a target P/L.

    Used only to prepare broker-side protective prices for the disabled demo
    execution path. The result is rounded to the symbol point.
    """

    target = float(target_profit_usd)
    if target == 0:
        return float(entry_price), "ZERO_TARGET"

    direction_upper = str(direction).upper()
    sign = 1.0 if direction_upper == "BUY" else -1.0
    if target < 0:
        sign *= -1.0

    absolute_target = abs(target)
    lower_distance = max(float(point), 1e-8)
    upper_distance = max(
        lower_distance * 2.0,
        absolute_target / max(float(lot_size) * float(contract_size), 1e-8) * 4.0,
    )

    method = "CONTRACT_SIZE_FALLBACK"
    for _ in range(12):
        candidate = float(entry_price) + sign * upper_distance
        profit, method = calculate_scalp_profit(
            symbol=symbol,
            direction=direction_upper,
            entry_price=entry_price,
            exit_price=candidate,
            lot_size=lot_size,
            contract_size=contract_size,
        )
        if abs(profit) >= absolute_target:
            break
        upper_distance *= 2.0

    for _ in range(50):
        midpoint = (lower_distance + upper_distance) / 2.0
        candidate = float(entry_price) + sign * midpoint
        profit, method = calculate_scalp_profit(
            symbol=symbol,
            direction=direction_upper,
            entry_price=entry_price,
            exit_price=candidate,
            lot_size=lot_size,
            contract_size=contract_size,
        )
        if abs(profit) < absolute_target:
            lower_distance = midpoint
        else:
            upper_distance = midpoint

    raw_price = float(entry_price) + sign * upper_distance
    safe_point = max(float(point), 1e-8)
    rounded = round(raw_price / safe_point) * safe_point
    return float(rounded), method
