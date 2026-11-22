from __future__ import annotations

from typing import Any
import math
import pandas as pd

from .core import candle_features, tick_features, time_features, clean_candles, atr


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def build_market_features(
    *,
    snapshot: Any,
    candles: dict[str, Any] | None = None,
    ticks: Any = None,
    verified_context: dict[str, Any] | None = None,
    structure: dict[str, Any] | None = None,
    news: dict[str, Any] | None = None,
    macro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candles = candles or getattr(snapshot, "candles", {}) or {}
    verified_context = verified_context or {}
    structure = structure or {}
    news = news or {}
    macro = macro or {}
    timestamp = getattr(snapshot, "system_timestamp", None) or pd.Timestamp.now(tz="UTC")
    timestamp = pd.Timestamp(timestamp)
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")

    features: dict[str, Any] = {}
    features.update(candle_features(candles))
    features.update(tick_features(ticks, timestamp))
    features.update(time_features(timestamp))

    mid = _num(getattr(snapshot, "mid", 0.0))
    spread = _num(getattr(snapshot, "spread", 0.0))
    m1_atr = max(_num(features.get("m1_atr")), 1e-9)
    features["spread_atr"] = spread / m1_atr
    features["mid"] = mid
    features["spread"] = spread

    features["vwap_distance_atr"] = _num(verified_context.get("vwap_distance_atr"))
    features["verified_data_quality"] = _num(verified_context.get("data_quality_score", verified_context.get("data_quality", 0.0)))
    features["verified_trend_direction"] = str(verified_context.get("trend_direction", "NEUTRAL")).upper()
    features["verified_liquidity_regime"] = str(verified_context.get("liquidity_regime", "UNKNOWN")).upper()
    features["structure_direction"] = str(structure.get("consensus_direction", structure.get("direction", "NEUTRAL"))).upper()
    features["structure_confidence"] = _num(structure.get("confidence"))
    features["structure_votes"] = _num(structure.get("consensus_votes", structure.get("votes", 0)))
    features["structure_room_usd"] = _num(structure.get("room_to_target_usd"))
    features["structure_location_safe"] = float(bool(structure.get("location_safe", False)))

    families = structure.get("families", {}) if isinstance(structure.get("families", {}), dict) else {}
    for name, key in (("htf_trend", "htf_direction"), ("support_resistance", "level_direction"), ("order_block", "order_block_direction")):
        item = families.get(name, {}) if isinstance(families.get(name, {}), dict) else {}
        features[key] = str(item.get("direction", "NEUTRAL")).upper()
        features[f"{key}_confidence"] = _num(item.get("confidence"))

    features["news_directional_bias"] = str(news.get("directional_bias", "NEUTRAL")).upper()
    features["news_bias_value"] = _num(news.get("directional_bias_value"))
    features["news_provider_quality"] = _num(news.get("provider_quality"))
    features["news_provider_conflict"] = float(bool(news.get("provider_conflict", False)))
    features["news_relevant_count"] = _num(news.get("relevant_event_count"))
    features["news_data_mode"] = str(news.get("data_mode", "UNKNOWN")).upper()

    observations = macro.get("observations", {}) if isinstance(macro.get("observations", {}), dict) else {}
    for key in ("us10y", "us10y_real", "us2y", "usd_broad", "fed_funds", "vix"):
        item = observations.get(key, {}) if isinstance(observations.get(key, {}), dict) else {}
        features[f"macro_{key}"] = _num(item.get("value"))
        features[f"macro_{key}_change_5"] = _num(item.get("change_5"))
    features["macro_gold_bias"] = str(macro.get("gold_bias", "NEUTRAL")).upper()
    features["macro_gold_pressure_raw"] = _num(macro.get("gold_pressure_raw"))
    features["macro_available"] = float(bool(macro.get("available", False)))
    features["macro_training_safe"] = float(bool(macro.get("historical_training_safe", False)))

    return features
