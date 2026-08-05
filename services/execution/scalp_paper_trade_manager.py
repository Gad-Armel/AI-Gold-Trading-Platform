from __future__ import annotations

from datetime import datetime
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.execution.scalp_profit_calculator import (
    calculate_scalp_profit,
    find_price_for_profit,
)
from services.risk.scalping_risk_guard import (
    evaluate_scalping_risk,
    get_scalping_trades_path,
    load_scalping_trades,
)
from services.utils.atomic_json import atomic_write_json


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value), DATETIME_FORMAT)
    except (TypeError, ValueError):
        return None


def _save_trades(trades: list[dict[str, Any]]) -> str:
    path = get_scalping_trades_path()
    return atomic_write_json(path, trades, indent=4)


def _entry_price(direction: str, snapshot: ScalpingSnapshotState) -> float:
    return snapshot.ask if direction == "BUY" else snapshot.bid


def _exit_price(direction: str, snapshot: ScalpingSnapshotState) -> float:
    return snapshot.bid if direction == "BUY" else snapshot.ask


def _profit(
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    contract_size: float,
) -> tuple[float, str]:
    return calculate_scalp_profit(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        lot_size=lot_size,
        contract_size=contract_size,
    )


def _close_trade(
    trade: dict[str, Any],
    snapshot: ScalpingSnapshotState,
    profit: float,
    reason: str,
    *,
    close_price: float | None = None,
    fill_type: str = "CURRENT_MARKET_QUOTE",
) -> None:
    direction = str(trade.get("direction", "")).upper()
    resolved_close_price = (
        float(close_price)
        if close_price is not None
        else _exit_price(direction, snapshot)
    )

    trade["status"] = "CLOSED"
    trade["closed_at"] = datetime.now().strftime(DATETIME_FORMAT)
    trade["close_price"] = round(resolved_close_price, 5)
    trade["final_profit_usd"] = round(profit, 2)
    trade["unrealized_profit_usd"] = 0.0
    trade["close_reason"] = reason
    trade["fill_type"] = fill_type
    trade["last_bid"] = snapshot.bid
    trade["last_ask"] = snapshot.ask
    trade["last_spread"] = snapshot.spread



def _signal_m1_metrics(signal: ScalpSignalState) -> dict[str, Any]:
    metrics = signal.metrics.get("M1", {}) if isinstance(signal.metrics, dict) else {}
    return metrics if isinstance(metrics, dict) else {}



def _signal_unified_metrics(signal: ScalpSignalState) -> dict[str, Any]:
    return signal.metrics if isinstance(signal.metrics, dict) else {}


def _signal_candle_key(signal: ScalpSignalState) -> str:
    m1 = _signal_m1_metrics(signal)
    value = m1.get("candle_time")
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d%H%M%S")
    return str(value or "")


def _fast_confirmation_exit_direction(signal: ScalpSignalState) -> str:
    """Return an opposite fast-exit direction even when entry is blocked.

    An exit may be needed while spread or the 20-candle entry trend prevents a
    new position.  Therefore this reads the raw score winner and the latest
    three-candle confirmation from signal metrics instead of requiring
    ``signal.allowed``.
    """

    if not bool(
        getattr(scalping_settings, "SCALPING_FAST_CONFIRMATION_EXIT_ENABLED", False)
    ):
        return "NONE"
    metrics = _signal_unified_metrics(signal)
    trend = metrics.get("trend_confirmation", {})
    diagnostics = metrics.get("score_diagnostics", {})
    direct = diagnostics.get("direct_score_decision", {})
    confirmation = str(trend.get("confirmation_direction", "NEUTRAL"))
    winner = str(direct.get("winner_direction", "NONE"))
    if confirmation in {"BUY", "SELL"} and confirmation == winner:
        return confirmation
    return "NONE"



def _tiered_protected_profit_floor(
    best_profit: float,
    target_profit: float,
) -> tuple[float | None, str]:
    """Scale profit protection to each trade's adaptive target.

    The original stages were calibrated to a $0.30 target.  V4.0 may raise the
    target when spread or ATR is larger, so the complete protection ladder is
    scaled by ``target / 0.30`` instead of activating too early.
    """

    base_target = max(
        0.01,
        float(scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD),
    )
    scale = max(1.0, float(target_profit) / base_target)
    stage_1_trigger = float(scalping_settings.SCALPING_BREAKEVEN_TRIGGER_USD) * scale
    stage_1_lock = float(scalping_settings.SCALPING_MIN_LOCKED_PROFIT_USD) * scale
    stage_2_trigger = float(scalping_settings.SCALPING_PROFIT_STAGE_2_TRIGGER_USD) * scale
    stage_2_lock = float(scalping_settings.SCALPING_PROFIT_STAGE_2_LOCK_USD) * scale
    stage_3_trigger = float(scalping_settings.SCALPING_PROFIT_STAGE_3_TRIGGER_USD) * scale
    stage_3_lock = float(scalping_settings.SCALPING_PROFIT_STAGE_3_LOCK_USD) * scale
    giveback = float(scalping_settings.SCALPING_TRAILING_GIVEBACK_USD) * scale

    if best_profit >= stage_3_trigger:
        return max(stage_3_lock, best_profit - giveback), "STAGE_3"
    if best_profit >= stage_2_trigger:
        return max(stage_2_lock, best_profit - giveback), "STAGE_2"
    if best_profit >= stage_1_trigger:
        return max(stage_1_lock, best_profit - giveback), "STAGE_1"
    return None, "INACTIVE"


def _ensure_protective_prices(
    trade: dict[str, Any],
    snapshot: ScalpingSnapshotState,
) -> None:
    """Attach target and stop close prices to old and new paper positions.

    These prices model broker-side TP/SL protection. They are persisted so a
    restart cannot convert a configured $3 stop into an arbitrary larger loss
    merely because the paper process was not running when the stop was crossed.
    """

    entry = _safe_float(trade.get("entry_price"))
    lot_size = _safe_float(
        trade.get("lot_size"), scalping_settings.SCALPING_LOT_SIZE
    )
    contract_size = _safe_float(
        trade.get("contract_size"), snapshot.contract_size
    )
    point = _safe_float(snapshot.point, 0.01)
    direction = str(trade.get("direction", "")).upper()
    target = _safe_float(
        trade.get("profit_target_usd"),
        scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD,
    )
    stop = _safe_float(
        trade.get("stop_loss_usd"),
        scalping_settings.SCALPING_MIN_STOP_LOSS_USD,
    )

    if entry <= 0 or direction not in {"BUY", "SELL"}:
        return

    if _safe_float(trade.get("target_close_price")) <= 0:
        target_price, target_method = find_price_for_profit(
            symbol=snapshot.symbol,
            direction=direction,
            entry_price=entry,
            lot_size=lot_size,
            contract_size=contract_size,
            target_profit_usd=target,
            point=point,
        )
        trade["target_close_price"] = round(target_price, 5)
        trade["target_price_method"] = target_method

    if _safe_float(trade.get("stop_close_price")) <= 0:
        stop_price, stop_method = find_price_for_profit(
            symbol=snapshot.symbol,
            direction=direction,
            entry_price=entry,
            lot_size=lot_size,
            contract_size=contract_size,
            target_profit_usd=-stop,
            point=point,
        )
        trade["stop_close_price"] = round(stop_price, 5)
        trade["stop_price_method"] = stop_method

    trade["paper_protective_orders_enabled"] = bool(
        scalping_settings.SCALPING_PAPER_PROTECTIVE_ORDERS_ENABLED
    )


def _target_hit(direction: str, current_exit: float, target_price: float) -> bool:
    if direction == "BUY":
        return current_exit >= target_price
    if direction == "SELL":
        return current_exit <= target_price
    return False


def _stop_hit(direction: str, current_exit: float, stop_price: float) -> bool:
    if direction == "BUY":
        return current_exit <= stop_price
    if direction == "SELL":
        return current_exit >= stop_price
    return False


def _protective_stop_fill(
    trade: dict[str, Any],
    snapshot: ScalpingSnapshotState,
) -> tuple[float, float, str]:
    """Return a conservative simulated stop fill and its resulting P/L."""

    direction = str(trade.get("direction", "")).upper()
    entry = _safe_float(trade.get("entry_price"))
    lot_size = _safe_float(
        trade.get("lot_size"), scalping_settings.SCALPING_LOT_SIZE
    )
    contract_size = _safe_float(
        trade.get("contract_size"), snapshot.contract_size
    )
    stop = _safe_float(
        trade.get("stop_loss_usd"),
        scalping_settings.SCALPING_MIN_STOP_LOSS_USD,
    )
    slippage = max(
        0.0,
        float(scalping_settings.SCALPING_PAPER_STOP_SLIPPAGE_USD),
    )

    fill_price, price_method = find_price_for_profit(
        symbol=snapshot.symbol,
        direction=direction,
        entry_price=entry,
        lot_size=lot_size,
        contract_size=contract_size,
        target_profit_usd=-(stop + slippage),
        point=snapshot.point,
    )
    fill_profit, profit_method = _profit(
        snapshot.symbol,
        direction,
        entry,
        fill_price,
        lot_size,
        contract_size,
    )
    return fill_price, fill_profit, f"{price_method}/{profit_method}"


def _monitor_gap_seconds(trade: dict[str, Any], now: datetime) -> float:
    previous_check = _parse_time(trade.get("last_checked_at"))
    if previous_check is None:
        previous_check = _parse_time(trade.get("opened_at"))
    if previous_check is None:
        return 0.0
    return max(0.0, (now - previous_check).total_seconds())


def close_all_open_scalp_paper_trades(
    snapshot: ScalpingSnapshotState,
    reason: str = "Paper scalper runner stopped",
) -> dict[str, Any]:
    """Flatten all open paper scalps at the latest available quote.

    This is used during an intentional CTRL+C/emergency/finite-loop shutdown so
    paper positions are never left unmanaged while the paper process is offline.
    It cannot send an MT5 order.
    """

    trades = load_scalping_trades()
    closed_count = 0
    messages: list[str] = []

    for trade in trades:
        if str(trade.get("status", "")).upper() != "OPEN":
            continue

        direction = str(trade.get("direction", "")).upper()
        entry = _safe_float(trade.get("entry_price"))
        lot_size = _safe_float(
            trade.get("lot_size"), scalping_settings.SCALPING_LOT_SIZE
        )
        contract_size = _safe_float(
            trade.get("contract_size"), snapshot.contract_size
        )
        close_price = _exit_price(direction, snapshot)
        profit, method = _profit(
            snapshot.symbol,
            direction,
            entry,
            close_price,
            lot_size,
            contract_size,
        )
        trade["profit_calculation_method"] = method
        trade["runner_shutdown_flattened"] = True
        _close_trade(
            trade,
            snapshot,
            profit,
            reason,
            close_price=close_price,
            fill_type="RUNNER_SHUTDOWN_MARKET_QUOTE",
        )
        closed_count += 1
        messages.append(f"Closed {direction} for ${profit:.2f}.")

    path = _save_trades(trades)
    return {
        "closed_count": closed_count,
        "message": " ".join(messages) if messages else "No open paper scalp required flattening.",
        "file_path": path,
    }


def manage_scalp_paper_trades(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    risk: dict[str, Any],
    news_risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Monitor and optionally open simulated scalps.

    This module contains no MT5 order call and cannot place a live trade.
    BUY positions enter at ask and close at bid. SELL positions enter at bid
    and close at ask, so spread is included in every paper result.
    """

    trades = load_scalping_trades()
    now = datetime.now()
    open_trades = [
        trade
        for trade in trades
        if str(trade.get("status", "")).upper() == "OPEN"
    ]

    closed_messages: list[str] = []
    closed_count = 0
    fast_exit_direction = _fast_confirmation_exit_direction(signal)

    for trade in open_trades:
        direction = str(trade.get("direction", "")).upper()
        entry = _safe_float(trade.get("entry_price"))
        lot_size = _safe_float(
            trade.get("lot_size"),
            scalping_settings.SCALPING_LOT_SIZE,
        )
        contract_size = _safe_float(
            trade.get("contract_size"),
            snapshot.contract_size,
        )
        current_exit_price = _exit_price(direction, snapshot)
        current_profit, profit_method = _profit(
            snapshot.symbol,
            direction,
            entry,
            current_exit_price,
            lot_size,
            contract_size,
        )
        trade["profit_calculation_method"] = profit_method

        monitor_gap = _monitor_gap_seconds(trade, now)
        trade["monitor_gap_seconds"] = round(monitor_gap, 2)

        opened_at = _parse_time(trade.get("opened_at"))
        hold_seconds = (
            max(0, int((now - opened_at).total_seconds())) if opened_at else 0
        )

        best_profit = max(
            _safe_float(trade.get("best_profit_usd")),
            current_profit,
        )
        previous_worst = _safe_float(trade.get("worst_profit_usd"), current_profit)
        worst_profit = min(previous_worst, current_profit)
        trade["best_profit_usd"] = round(best_profit, 2)
        trade["worst_profit_usd"] = round(worst_profit, 2)
        trade["max_favorable_excursion_usd"] = round(max(0.0, best_profit), 2)
        trade["max_adverse_excursion_usd"] = round(abs(min(0.0, worst_profit)), 2)
        trade["unrealized_profit_usd"] = round(current_profit, 2)
        trade["hold_seconds"] = hold_seconds
        trade["last_price"] = round(current_exit_price, 5)
        trade["last_bid"] = snapshot.bid
        trade["last_ask"] = snapshot.ask
        trade["last_spread"] = snapshot.spread

        target = _safe_float(
            trade.get("profit_target_usd"),
            scalping_settings.SCALPING_MIN_PROFIT_TARGET_USD,
        )
        stop = _safe_float(
            trade.get("stop_loss_usd"),
            scalping_settings.SCALPING_MIN_STOP_LOSS_USD,
        )

        _ensure_protective_prices(trade, snapshot)
        target_price = _safe_float(trade.get("target_close_price"))
        stop_price = _safe_float(trade.get("stop_close_price"))
        protective_enabled = bool(
            scalping_settings.SCALPING_PAPER_PROTECTIVE_ORDERS_ENABLED
        )

        close_reason = ""
        close_price = current_exit_price
        close_profit = current_profit
        fill_type = "CURRENT_MARKET_QUOTE"

        if protective_enabled and target_price > 0 and _target_hit(
            direction, current_exit_price, target_price
        ):
            close_price = target_price
            close_profit, target_profit_method = _profit(
                snapshot.symbol,
                direction,
                entry,
                close_price,
                lot_size,
                contract_size,
            )
            trade["protective_fill_method"] = target_profit_method
            close_reason = "Simulated broker-side scalp profit target reached"
            fill_type = "SIMULATED_BROKER_TARGET"
        elif protective_enabled and stop_price > 0 and _stop_hit(
            direction, current_exit_price, stop_price
        ):
            close_price, close_profit, stop_fill_method = _protective_stop_fill(
                trade, snapshot
            )
            trade["protective_fill_method"] = stop_fill_method
            trade["simulated_stop_slippage_usd"] = float(
                scalping_settings.SCALPING_PAPER_STOP_SLIPPAGE_USD
            )
            gap_threshold = float(
                scalping_settings.SCALPING_OFFLINE_GAP_THRESHOLD_SECONDS
            )
            if monitor_gap > gap_threshold:
                close_reason = (
                    "Simulated broker-side scalp stop reached during monitoring gap"
                )
                trade["offline_protective_recovery"] = True
            else:
                close_reason = "Simulated broker-side scalp stop reached"
            fill_type = "SIMULATED_BROKER_STOP"
        elif not protective_enabled and current_profit >= target:
            close_reason = "Scalp profit target reached"
        elif not protective_enabled and current_profit <= -stop:
            close_reason = "Scalp stop loss reached"
        elif hold_seconds >= int(scalping_settings.SCALPING_MAX_HOLD_SECONDS):
            close_reason = "Scalp maximum hold time reached"
        elif snapshot.spread >= float(
            scalping_settings.SCALPING_EMERGENCY_EXIT_SPREAD_USD
        ):
            close_reason = "Emergency spread exit"
        elif (
            fast_exit_direction in {"BUY", "SELL"}
            and fast_exit_direction != direction
        ):
            close_reason = "Fast 3-candle confirmation flipped against position"
        elif (
            scalping_settings.SCALPING_CLOSE_ON_OPPOSITE_SIGNAL
            and signal.allowed
            and signal.direction not in {"NONE", direction}
            and (
                bool(getattr(scalping_settings, "SCALPING_DIRECT_SCORE_PAPER_ENABLED", False))
                and bool(getattr(scalping_settings, "SCALPING_DIRECT_SCORE_CLOSE_ON_ANY_FLIP", False))
                or signal.score >= float(scalping_settings.SCALPING_OPPOSITE_SIGNAL_MIN_SCORE)
            )
        ):
            close_reason = "Opposite direct-score winner" if bool(
                getattr(scalping_settings, "SCALPING_DIRECT_SCORE_CLOSE_ON_ANY_FLIP", False)
            ) else "Strong opposite scalp signal"
        else:
            protected_floor, protection_stage = _tiered_protected_profit_floor(
                best_profit, target
            )
            trade["profit_protection_stage"] = protection_stage
            trade["trailing_active"] = protected_floor is not None
            if protected_floor is not None:
                trade["protected_profit_floor_usd"] = round(protected_floor, 2)
                if current_profit <= protected_floor:
                    close_reason = (
                        f"Scalp tiered-profit protection {protection_stage}"
                    )

        trade["last_checked_at"] = now.strftime(DATETIME_FORMAT)

        if close_reason:
            _close_trade(
                trade,
                snapshot,
                close_profit,
                close_reason,
                close_price=close_price,
                fill_type=fill_type,
            )
            closed_count += 1
            closed_messages.append(
                f"Closed {direction} for ${close_profit:.2f}: {close_reason}."
            )

    open_trades = [
        trade
        for trade in trades
        if str(trade.get("status", "")).upper() == "OPEN"
    ]

    opened_trade = False
    open_message = ""

    # Persist closures before re-evaluating risk. This lets a profitable close
    # free position capacity immediately and lets a third consecutive loss
    # activate its cooldown before any same-cycle re-entry.
    if closed_count > 0:
        _save_trades(trades)
        if news_risk is not None:
            refreshed_risk = evaluate_scalping_risk(snapshot, signal, news_risk)
            risk.clear()
            risk.update(refreshed_risk)

    if not signal.allowed:
        open_message = "No scalp opened because the signal engine returned WAIT."
    elif not bool(risk.get("entry_allowed", False)):
        open_message = "No scalp opened because the risk guard blocked entry."
    elif len(open_trades) >= int(scalping_settings.SCALPING_MAX_OPEN_POSITIONS):
        open_message = "Maximum simulated scalp positions are already open."
    else:
        direction = signal.direction
        entry = _entry_price(direction, snapshot)
        timestamp = datetime.now()
        trade = {
                "id": "SCALP-" + timestamp.strftime("%Y%m%d%H%M%S%f"),
                "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
                "status": "OPEN",
                "symbol": snapshot.symbol,
                "direction": direction,
                "entry_price": round(entry, 5),
                "entry_bid": snapshot.bid,
                "entry_ask": snapshot.ask,
                "entry_spread": snapshot.spread,
                "lot_size": float(scalping_settings.SCALPING_LOT_SIZE),
                "contract_size": snapshot.contract_size,
                "magic_number": scalping_settings.SCALPING_MAGIC_NUMBER,
                "opened_at": timestamp.strftime(DATETIME_FORMAT),
                "last_checked_at": timestamp.strftime(DATETIME_FORMAT),
                "signal_key": signal.signal_key,
                "signal_score": signal.score,
                "signal_confidence": signal.confidence,
                "entry_pattern": signal.pattern,
                "entry_candle_time": _signal_candle_key(signal),
                "entry_m1_atr": _safe_float(_signal_m1_metrics(signal).get("atr")),
                "entry_m1_rsi": _safe_float(_signal_m1_metrics(signal).get("rsi")),
                "entry_m1_momentum": _safe_float(
                    _signal_m1_metrics(signal).get("momentum")
                ),
                "entry_distance_fast_atr_ratio": _safe_float(
                    _signal_m1_metrics(signal).get("distance_fast_atr_ratio")
                ),
                "entry_market_regime": _signal_unified_metrics(signal).get("regime", {}).get("mode", ""),
                "entry_regime_direction": _signal_unified_metrics(signal).get("regime", {}).get("direction", ""),
                "entry_structure_direction": _signal_unified_metrics(signal).get("structure", {}).get("direction", ""),
                "entry_near_support": bool(_signal_unified_metrics(signal).get("zones", {}).get("near_support", False)),
                "entry_near_resistance": bool(_signal_unified_metrics(signal).get("zones", {}).get("near_resistance", False)),
                "entry_in_bullish_order_block": bool(_signal_unified_metrics(signal).get("order_blocks", {}).get("in_bullish", False)),
                "entry_in_bearish_order_block": bool(_signal_unified_metrics(signal).get("order_blocks", {}).get("in_bearish", False)),
                "entry_factor_direction": _signal_unified_metrics(signal).get("factor_model", {}).get("preferred_direction", ""),
                "entry_factor_score": _safe_float(_signal_unified_metrics(signal).get("factor_model", {}).get("preferred_score")),
                "entry_factor_count": int(_safe_float(_signal_unified_metrics(signal).get("factor_model", {}).get("preferred_factor_count"))),
                "entry_confirming_family_count": int(_safe_float(_signal_unified_metrics(signal).get("score_diagnostics", {}).get("confirming_family_count"))),
                "entry_confirming_families": list(_signal_unified_metrics(signal).get("score_diagnostics", {}).get("confirming_families", [])),
                "entry_news_bias": _signal_unified_metrics(signal).get("news_context", {}).get("directional_bias", "NEUTRAL"),
                "entry_news_data_mode": _signal_unified_metrics(signal).get("news_context", {}).get("data_mode", ""),
                "entry_verified_data_quality_score": _safe_float(_signal_unified_metrics(signal).get("verified_context", {}).get("data_quality_score")),
                "entry_relative_tick_volume": _safe_float(_signal_unified_metrics(signal).get("verified_context", {}).get("relative_tick_volume")),
                "entry_signed_tick_volume_proxy": _safe_float(_signal_unified_metrics(signal).get("verified_context", {}).get("signed_tick_volume_proxy")),
                "entry_rolling_vwap": _safe_float(_signal_unified_metrics(signal).get("verified_context", {}).get("rolling_vwap")),
                "entry_vwap_distance_atr": _safe_float(_signal_unified_metrics(signal).get("verified_context", {}).get("vwap_distance_atr")),
                "entry_adx_m5": _safe_float(_signal_unified_metrics(signal).get("verified_context", {}).get("adx_m5")),
                "entry_verified_trend_direction": _signal_unified_metrics(signal).get("verified_context", {}).get("trend_direction", ""),
                "entry_verified_liquidity_regime": _signal_unified_metrics(signal).get("verified_context", {}).get("liquidity_regime", ""),
                "entry_nearest_pivot": _signal_unified_metrics(signal).get("verified_context", {}).get("nearest_pivot", ""),
                "entry_nearest_pivot_distance_atr": _safe_float(_signal_unified_metrics(signal).get("verified_context", {}).get("nearest_pivot_distance_atr")),
                "entry_cross_market_status": _signal_unified_metrics(signal).get("cross_market_context", {}).get("status", ""),
                "entry_cross_market_usd_bias": _signal_unified_metrics(signal).get("cross_market_context", {}).get("usd_bias", ""),
                "entry_cross_market_gold_bias": _signal_unified_metrics(signal).get("cross_market_context", {}).get("gold_bias", ""),
                "entry_cross_market_pressure_score": _safe_float(_signal_unified_metrics(signal).get("cross_market_context", {}).get("pressure_score")),
                "entry_trend20_direction": _signal_unified_metrics(signal).get("trend_confirmation", {}).get("trend_direction", ""),
                "entry_trend20_strength": _safe_float(_signal_unified_metrics(signal).get("trend_confirmation", {}).get("trend_strength")),
                "entry_confirmation3_direction": _signal_unified_metrics(signal).get("trend_confirmation", {}).get("confirmation_direction", ""),
                "entry_confirmation3_strength": _safe_float(_signal_unified_metrics(signal).get("trend_confirmation", {}).get("confirmation_strength")),
                "entry_quality_support_votes": int(_safe_float(_signal_unified_metrics(signal).get("score_diagnostics", {}).get("entry_quality_decision", {}).get("support_votes"))),
                "entry_quality_opposition_votes": int(_safe_float(_signal_unified_metrics(signal).get("score_diagnostics", {}).get("entry_quality_decision", {}).get("opposition_votes"))),
                "profit_target_usd": signal.target_profit_usd,
                "stop_loss_usd": signal.stop_loss_usd,
                "max_hold_seconds": int(
                    scalping_settings.SCALPING_MAX_HOLD_SECONDS
                ),
                "best_profit_usd": round(
                    -(
                        snapshot.spread
                        * float(scalping_settings.SCALPING_LOT_SIZE)
                        * snapshot.contract_size
                    ),
                    2,
                ),
                "worst_profit_usd": round(
                    -(
                        snapshot.spread
                        * float(scalping_settings.SCALPING_LOT_SIZE)
                        * snapshot.contract_size
                    ),
                    2,
                ),
                "max_favorable_excursion_usd": 0.0,
                "max_adverse_excursion_usd": round(
                    snapshot.spread
                    * float(scalping_settings.SCALPING_LOT_SIZE)
                    * snapshot.contract_size,
                    2,
                ),
                "unrealized_profit_usd": round(
                    -(
                        snapshot.spread
                        * float(scalping_settings.SCALPING_LOT_SIZE)
                        * snapshot.contract_size
                    ),
                    2,
                ),
                "hold_seconds": 0,
                "session": snapshot.session,
                "source": "SCALPING_PAPER_ENGINE",
                "profit_calculation_method": "PENDING_FIRST_MARK",
                "same_candle_reentry_enabled": True,
            }
        _ensure_protective_prices(trade, snapshot)
        trades.append(trade)
        opened_trade = True
        open_message = (
            f"Opened simulated {direction} scalp at {entry:.5f}; "
            f"target=${signal.target_profit_usd:.2f}, "
            f"stop=${signal.stop_loss_usd:.2f}."
        )

    path = _save_trades(trades)

    final_open = [
        trade
        for trade in trades
        if str(trade.get("status", "")).upper() == "OPEN"
    ]
    closed = [
        trade
        for trade in trades
        if str(trade.get("status", "")).upper() == "CLOSED"
    ]
    realized = round(
        sum(_safe_float(trade.get("final_profit_usd")) for trade in closed),
        2,
    )
    unrealized = round(
        sum(
            _safe_float(trade.get("unrealized_profit_usd"))
            for trade in final_open
        ),
        2,
    )
    wins = sum(
        1 for trade in closed if _safe_float(trade.get("final_profit_usd")) > 0
    )
    win_rate = round((wins / len(closed) * 100.0), 2) if closed else 0.0

    if closed_count and opened_trade:
        action = "SCALP_CLOSED_AND_REOPENED"
    elif closed_count:
        action = "SCALP_CLOSED"
    elif opened_trade:
        action = "SCALP_OPENED"
    elif final_open:
        action = "SCALP_MONITORING"
    else:
        action = "NO_SCALP"

    messages = closed_messages + ([open_message] if open_message else [])
    return {
        "action": action,
        "message": " | ".join(messages),
        "opened_trade": opened_trade,
        "closed_count": closed_count,
        "open_trade_count": len(final_open),
        "total_trade_count": len(trades),
        "closed_trade_count": len(closed),
        "realized_profit_usd": realized,
        "unrealized_profit_usd": unrealized,
        "win_rate": win_rate,
        "file_path": path,
    }
