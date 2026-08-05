from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from config import scalping_settings
from services.agents.meta_controller import apply_meta_controller_to_signal, evaluate_meta_controller
from services.agents.scalping_agents import build_scalping_agents
from services.analysis.scalp_signal_engine import build_scalp_signal
from services.analysis.v6_market_structure import build_v6_market_structure, maybe_render_v6_market_map
from services.execution.demo_session_guard import validate_demo_session_identity
from services.decision.demo_signal_persistence import apply_demo_signal_persistence, reset_demo_signal_persistence
from services.execution.scalp_demo_executor import execute_demo_scalp
from services.execution.scalp_demo_position_manager import manage_demo_scalp_positions
from services.market_data.intermarket_symbol_resolver import get_direct_intermarket_context
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.microstructure.feature_engine import build_microstructure_features
from services.microstructure.feature_store import store_microstructure_features
from services.microstructure.tick_recorder import capture_mt5_ticks
from services.news.unified_news_intelligence import build_unified_news_context
from services.risk.news_event_filter import assess_news_event_risk
from services.risk.scalping_demo_risk_guard import evaluate_scalping_demo_risk
from services.research.v6_candidate_gate import apply_v6_candidate_gate, evaluate_v6_candidate_gate
from services.research.v6_shadow_engine import build_v6_entry_profile
from services.research.v63_self_learning import score_v63_profile


def run_scalping_demo_cycle(symbol: str, *, mt5_module: Any | None = None) -> dict[str, Any]:
    if mt5_module is None:
        import MetaTrader5 as mt5_module  # type: ignore
    started = time.perf_counter()
    account = mt5_module.account_info()
    identity_ok, identity_reason = validate_demo_session_identity(account, mt5_module)
    if not identity_ok:
        return {"success": False, "fatal": True, "message": identity_reason}

    snapshot = get_scalping_snapshot(symbol)
    direct_intermarket = get_direct_intermarket_context()
    snapshot.intermarket_context = direct_intermarket
    news = assess_news_event_risk(symbol=symbol, current_time=datetime.now())
    news_context = build_unified_news_context(snapshot.session, news, datetime.now())
    news["unified_context"] = news_context
    signal = build_scalp_signal(snapshot, news_context)

    positions = mt5_module.positions_get(symbol=symbol) or ()
    magic = __import__('config.scalping_settings', fromlist=['SCALPING_MAGIC_NUMBER']).SCALPING_MAGIC_NUMBER
    open_count = sum(int(getattr(p, "magic", -1)) == int(magic) for p in positions)
    captured = capture_mt5_ticks(snapshot, signal, open_position_count=open_count, intermarket=direct_intermarket)
    recent_ticks = list(captured.pop("recent_ticks", []))
    m1 = signal.metrics.get("M1", {}) if isinstance(signal.metrics, dict) else {}
    feature_state = build_microstructure_features(symbol, recent_ticks, m1_atr=float(m1.get("atr", 0.0) or 0.0))
    feature_storage = store_microstructure_features(feature_state, cycle_timestamp=snapshot.timestamp)
    microstructure = feature_state.to_dict()
    microstructure["storage"] = feature_storage
    agents = build_scalping_agents(snapshot, signal, feature_state, news, direct_intermarket)
    meta = evaluate_meta_controller(signal, agents)
    raw_signal = apply_meta_controller_to_signal(
        signal,
        meta,
        microstructure=microstructure,
        agents=agents,
        direct_intermarket=direct_intermarket,
    )
    decision_timestamp = datetime.now(timezone.utc)

    # Position exits use the immediate, fully evaluated market signal. New
    # entries additionally require persistence and the exact V6.3 STRICT structure-consensus gate.
    managed = manage_demo_scalp_positions(snapshot, raw_signal, mt5_module=mt5_module)
    if managed.get("closed_count", 0):
        reset_demo_signal_persistence()
    signal, persistence = apply_demo_signal_persistence(raw_signal, observation_id=int(getattr(snapshot, "tick_time_msc", 0) or 0))
    current_positions = [
        position
        for position in (mt5_module.positions_get(symbol=symbol) or ())
        if int(getattr(position, "magic", -1)) == int(magic)
    ]
    open_floating = sum(
        float(getattr(position, "profit", 0.0) or 0.0)
        for position in current_positions
    )
    structure = build_v6_market_structure(snapshot)
    if not isinstance(signal.metrics, dict):
        signal.metrics = {}
    signal.metrics["v6_market_structure"] = structure
    v6_gate = evaluate_v6_candidate_gate(snapshot, signal)
    model_profile = build_v6_entry_profile(snapshot, signal, v6_gate, "STRICT")
    model_score = score_v63_profile(model_profile, source_lane="STRICT")
    if bool(getattr(scalping_settings, "SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL", True)):
        v6_gate.setdefault("checks", {})["approved_calibrated_model"] = bool(model_score.get("approved_model", False))
        v6_gate.setdefault("checks", {})["model_probability"] = bool(model_score.get("allowed", False))
        v6_gate["model_probability_win"] = float(model_score.get("probability_win", 0.0) or 0.0)
        v6_gate["model_probability_threshold"] = model_score.get("threshold")
        v6_gate["model_name"] = model_score.get("model_name")
        v6_gate["model_status"] = model_score
        v6_gate["failed_checks"] = [name for name, passed in v6_gate["checks"].items() if not passed]
        v6_gate["allowed"] = not v6_gate["failed_checks"]
        v6_gate["reason"] = (
            "V6.3 STRICT gate and calibrated model passed."
            if v6_gate["allowed"]
            else "V6.3 STRICT/model gate blocked: " + ", ".join(v6_gate["failed_checks"]) + "."
        )
    if bool(news.get("blocked", False)) or not bool(news.get("allowed", True)):
        v6_gate.setdefault("checks", {})["news_safe"] = False
        if "news_safe" not in v6_gate.setdefault("failed_checks", []):
            v6_gate["failed_checks"].append("news_safe")
        v6_gate["allowed"] = False
        v6_gate["reason"] = "V6 candidate gate blocked: " + ", ".join(v6_gate["failed_checks"]) + "."
    signal = apply_v6_candidate_gate(signal, v6_gate)
    risk = evaluate_scalping_demo_risk(
        snapshot,
        signal,
        news,
        account_info=account,
        open_floating_profit_usd=open_floating,
    )
    risk["v6_candidate_gate"] = v6_gate
    if not v6_gate.get("allowed", False):
        reason = str(v6_gate.get("reason", "V6 candidate gate blocked entry."))
        if reason and reason not in risk["block_reasons"]:
            risk["block_reasons"].append(reason)
    risk["allowed"] = bool(risk.get("allowed", False) and v6_gate.get("allowed", False))
    risk["action"] = "SCALP_DEMO_RISK_ALLOWED" if risk["allowed"] else "SCALP_DEMO_RISK_BLOCKED"
    market_map = maybe_render_v6_market_map(
        snapshot,
        structure,
        force=bool(v6_gate.get("direction") in {"BUY", "SELL"} and v6_gate.get("structure_votes", 0) >= 2),
    )

    if managed.get("closed_count", 0):
        execution = {"success": False, "action": "SCALP_DEMO_REENTRY_DELAYED", "message": "No demo re-entry during a position-closing cycle."}
    elif risk["allowed"]:
        request_timestamp = datetime.now(timezone.utc)
        execution = execute_demo_scalp(
            snapshot,
            signal,
            readiness_report={},
            mt5_module=mt5_module,
            decision_timestamp=decision_timestamp,
            request_timestamp=request_timestamp,
        )
    else:
        execution = {"success": False, "action": "SCALP_DEMO_ENTRY_BLOCKED", "message": " | ".join(risk["block_reasons"])}

    return {
        "success": True,
        "fatal": False,
        "symbol": symbol,
        "runtime_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "snapshot": snapshot,
        "signal": signal,
        "news": news,
        "risk": risk,
        "position_management": managed,
        "execution": execution,
        "tick_recorder": captured,
        "microstructure": microstructure,
        "agents": agents,
        "meta_controller": meta,
        "signal_persistence": persistence,
        "v6_candidate_gate": v6_gate,
        "v6_market_structure": structure,
        "v63_model_score": model_score,
        "market_map": market_map,
        "raw_signal": raw_signal,
    }
