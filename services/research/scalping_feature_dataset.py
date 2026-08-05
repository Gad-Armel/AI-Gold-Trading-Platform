from __future__ import annotations

"""Export real paper-trade features for later walk-forward ML research.

No model is trained here. Synthetic data is never generated. The export is a
clean trade-level dataset containing only information that existed at entry and
outcomes observed after the trade closed.
"""

import csv
import os
from typing import Any

from config import scalping_settings
from services.bot.scalping_trade_repository import (
    filter_strategy_trades,
    load_all_scalping_trades,
    split_trade_statuses,
)
from services.risk.scalping_risk_guard import get_scalping_log_folder


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


FEATURE_FIELDS = [
    "id", "strategy_id", "opened_at", "closed_at", "session", "direction",
    "entry_pattern", "signal_score", "signal_confidence", "entry_spread",
    "entry_m1_atr", "entry_m1_rsi", "entry_m1_momentum",
    "entry_distance_fast_atr_ratio", "entry_market_regime",
    "entry_regime_direction", "entry_structure_direction",
    "entry_near_support", "entry_near_resistance",
    "entry_in_bullish_order_block", "entry_in_bearish_order_block",
    "entry_factor_direction", "entry_factor_score", "entry_factor_count",
    "entry_confirming_family_count", "entry_news_bias", "entry_news_data_mode",
    "entry_verified_data_quality_score", "entry_relative_tick_volume",
    "entry_signed_tick_volume_proxy", "entry_rolling_vwap",
    "entry_vwap_distance_atr", "entry_adx_m5",
    "entry_verified_trend_direction", "entry_verified_liquidity_regime",
    "entry_nearest_pivot", "entry_nearest_pivot_distance_atr",
    "entry_cross_market_status", "entry_cross_market_usd_bias",
    "entry_cross_market_gold_bias", "entry_cross_market_pressure_score",
    "profit_target_usd", "stop_loss_usd", "hold_seconds", "close_reason",
    "best_profit_usd", "worst_profit_usd", "max_favorable_excursion_usd",
    "max_adverse_excursion_usd", "final_profit_usd", "outcome_class",
]


def build_feature_dataset() -> dict[str, Any]:
    trades = filter_strategy_trades(load_all_scalping_trades())
    closed, opened = split_trade_statuses(trades)
    folder = get_scalping_log_folder()
    path = os.path.join(folder, scalping_settings.SCALPING_FEATURE_DATASET_FILENAME)
    os.makedirs(folder, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for trade in closed:
        profit = _float(trade.get("final_profit_usd"))
        row = {field: trade.get(field, "") for field in FEATURE_FIELDS}
        row["outcome_class"] = "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"
        row["final_profit_usd"] = profit
        rows.append(row)

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FEATURE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    minimum = int(scalping_settings.SCALPING_MIN_REAL_TRADES_BEFORE_ML_RESEARCH)
    return {
        "path": path,
        "closed_trade_rows": len(rows),
        "open_trades_excluded": len(opened),
        "minimum_real_trades_for_ml_research": minimum,
        "ml_research_ready": len(rows) >= minimum,
        "synthetic_data_used": False,
        "model_enabled": False,
    }
