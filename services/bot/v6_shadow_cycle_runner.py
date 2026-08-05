from __future__ import annotations

from datetime import datetime
from typing import Any

from config import scalping_settings
from services.agents.meta_controller import apply_meta_controller_to_signal, evaluate_meta_controller
from services.agents.scalping_agents import build_scalping_agents
from services.analysis.scalp_signal_engine import build_scalp_signal
from services.analysis.v6_market_structure import build_v6_market_structure, maybe_render_v6_market_map
from services.decision.demo_signal_persistence import apply_demo_signal_persistence, reset_demo_signal_persistence
from services.market_data.intermarket_symbol_resolver import get_direct_intermarket_context
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.microstructure.feature_engine import build_microstructure_features
from services.microstructure.feature_store import store_microstructure_features
from services.microstructure.tick_recorder import capture_mt5_ticks
from services.news.free_macro_context import load_free_macro_cache
from services.news.unified_news_intelligence import build_unified_news_context
from services.research.v6_candidate_gate import evaluate_v6_shadow_lane_gates
from services.research.v6_feed_guard import evaluate_v6_feed_guard
from services.research.v6_gate_telemetry import record_v6_gate_telemetry
from services.research.v6_shadow_engine import update_v6_shadow_lanes
from services.research.v63_learned_gate import evaluate_v63_learned_gate
from services.research.v63_self_learning import maybe_retrain_v63_model
from services.risk.news_event_filter import assess_news_event_risk


def run_v6_shadow_cycle(symbol: str, *, mt5_module: Any | None = None) -> dict[str, Any]:
    if mt5_module is None:
        import MetaTrader5 as mt5_module  # type: ignore
    snapshot = get_scalping_snapshot(symbol)
    feed_guard = evaluate_v6_feed_guard(snapshot)
    if bool(feed_guard["paused"]):
        # Do not repeatedly run candle/agent/chart analysis against one frozen
        # terminal quote. The loop backs off until a fresh MT5 tick arrives.
        return {
            "success": True,
            "feed_paused": True,
            "snapshot": snapshot,
            "quote_age_seconds": feed_guard["quote_age_seconds"],
            "reason": feed_guard["reason"],
            "feed_guard": feed_guard,
        }

    direct_intermarket = get_direct_intermarket_context()
    snapshot.intermarket_context = direct_intermarket
    news = assess_news_event_risk(symbol=symbol, current_time=datetime.now())
    news_context = build_unified_news_context(snapshot.session, news, datetime.now())
    if isinstance(news_context, dict):
        news_context["free_macro_context"] = load_free_macro_cache()
    news["unified_context"] = news_context
    initial_signal = build_scalp_signal(snapshot, news_context)
    captured = capture_mt5_ticks(snapshot, initial_signal, open_position_count=0, intermarket=direct_intermarket)
    recent_ticks = list(captured.pop("recent_ticks", []))
    m1 = initial_signal.metrics.get("M1", {}) if isinstance(initial_signal.metrics, dict) else {}
    feature_state = build_microstructure_features(symbol, recent_ticks, m1_atr=float(m1.get("atr", 0.0) or 0.0))
    feature_storage = store_microstructure_features(feature_state, cycle_timestamp=snapshot.timestamp)
    microstructure = feature_state.to_dict()
    microstructure["storage"] = feature_storage
    agents = build_scalping_agents(snapshot, initial_signal, feature_state, news, direct_intermarket)
    meta = evaluate_meta_controller(initial_signal, agents)
    raw_signal = apply_meta_controller_to_signal(
        initial_signal,
        meta,
        microstructure=microstructure,
        agents=agents,
        direct_intermarket=direct_intermarket,
    )
    signal, persistence = apply_demo_signal_persistence(
        raw_signal,
        observation_id=int(getattr(snapshot, "tick_time_msc", 0) or 0),
    )
    structure = build_v6_market_structure(snapshot)
    if not isinstance(signal.metrics, dict):
        signal.metrics = {}
    signal.metrics["v6_market_structure"] = structure
    lane_gates = evaluate_v6_shadow_lane_gates(snapshot, signal)
    if bool(getattr(scalping_settings, "SCALPING_V63_LEARNED_LANE_ENABLED", True)):
        learned_name = str(scalping_settings.SCALPING_V63_LEARNED_LANE_NAME).upper()
        base_name = str(scalping_settings.SCALPING_V63_LEARNED_BASE_LANE).upper()
        lane_gates[learned_name] = evaluate_v63_learned_gate(
            snapshot, signal, lane_gates[base_name]
        )
    if bool(news.get("blocked", False)) or not bool(news.get("allowed", True)):
        for gate in lane_gates.values():
            gate["checks"]["news_safe"] = False
            if "news_safe" not in gate["failed_checks"]:
                gate["failed_checks"].append("news_safe")
            gate["allowed"] = False
            gate["reason"] = f"V6 {gate['lane']} lane blocked: " + ", ".join(gate["failed_checks"]) + "."

    shadow_lanes = update_v6_shadow_lanes(snapshot, signal, lane_gates)
    persistence_reset_after_close = False
    self_learning_update = {"attempted": False}
    if shadow_lanes.get("closed_lanes"):
        reset_demo_signal_persistence()
        persistence_reset_after_close = True
        if bool(getattr(scalping_settings, "SCALPING_V63_AUTO_RETRAIN_AFTER_CLOSE", True)):
            self_learning_update = maybe_retrain_v63_model(force=False)
    gate_telemetry = record_v6_gate_telemetry(
        snapshot, lane_gates, force=bool(shadow_lanes.get("opened_lanes") or shadow_lanes.get("closed_lanes"))
    )
    chart = maybe_render_v6_market_map(
        snapshot,
        structure,
        force=bool(shadow_lanes.get("opened_lanes")),
    )
    return {
        "success": True,
        "feed_paused": False,
        "snapshot": snapshot,
        "signal": signal,
        "raw_signal": raw_signal,
        "news": news,
        "tick_recorder": captured,
        "microstructure": microstructure,
        "agents": agents,
        "meta_controller": meta,
        "signal_persistence": persistence,
        "v6_gate": lane_gates["STRICT"],
        "v6_lane_gates": lane_gates,
        "v6_market_structure": structure,
        "market_map": chart,
        "shadow": shadow_lanes["lanes"]["STRICT"],
        "shadow_lanes": shadow_lanes,
        "gate_telemetry": gate_telemetry,
        "persistence_reset_after_close": persistence_reset_after_close,
        "v63_self_learning_update": self_learning_update,
    }
