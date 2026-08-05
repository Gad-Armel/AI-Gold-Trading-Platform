from __future__ import annotations

import time
from datetime import datetime, timezone

from config import scalping_settings
from models.scalping_state import ScalpingCycleState
from services.agents.meta_controller import (
    apply_meta_controller_to_signal,
    evaluate_meta_controller,
)
from services.agents.scalping_agents import build_scalping_agents
from services.analysis.scalp_signal_engine import build_scalp_signal
from services.bot.scalping_logger import export_scalping_trade_history, log_scalping_cycle
from services.execution.execution_audit import audit_paper_trade_transition
from services.execution.scalp_paper_trade_manager import manage_scalp_paper_trades
from services.market_data.intermarket_symbol_resolver import (
    get_direct_intermarket_context,
)
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.microstructure.feature_engine import build_microstructure_features
from services.microstructure.feature_store import store_microstructure_features
from services.microstructure.tick_recorder import capture_mt5_ticks
from services.news.unified_news_intelligence import build_unified_news_context
from services.risk.news_event_filter import assess_news_event_risk
from services.risk.scalping_risk_guard import (
    evaluate_scalping_risk,
    load_scalping_trades,
)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def _open_trade_count(trades: list[dict]) -> int:
    return sum(
        1 for trade in trades if str(trade.get("status", "")).upper() == "OPEN"
    )


def run_scalping_cycle(symbol: str) -> ScalpingCycleState:
    started_at = datetime.now()
    started_counter = time.perf_counter()
    snapshot = None
    signal = None
    news_risk: dict = {}
    risk: dict = {}
    paper: dict = {}
    tick_recorder: dict = {}
    microstructure: dict = {}
    agents: dict = {}
    meta_controller: dict = {}
    execution_audit: dict = {}
    error_message = None
    success = False
    timing_ms: dict[str, float] = {}

    try:
        phase = time.perf_counter()
        snapshot = get_scalping_snapshot(symbol)
        timing_ms["snapshot"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        direct_intermarket = get_direct_intermarket_context()
        snapshot.intermarket_context = direct_intermarket
        timing_ms["direct_intermarket"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        if scalping_settings.SCALPING_USE_CORE_NEWS_FILTER:
            news_risk = assess_news_event_risk(symbol=symbol, current_time=datetime.now())
        else:
            news_risk = {
                "allowed": True,
                "action": "SCALPING_NEWS_FILTER_DISABLED",
                "block_reasons": [],
                "active_events": [],
            }
        timing_ms["news_filter"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        news_context = build_unified_news_context(snapshot.session, news_risk, datetime.now())
        news_risk["unified_context"] = news_context
        timing_ms["news_context"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        signal = build_scalp_signal(snapshot, news_context)
        timing_ms["signal_engine"] = _elapsed_ms(phase)

        # Snapshot the paper book before the decision manager mutates it. This
        # same immutable before-state is used by the tick context and audit.
        before_trades = load_scalping_trades()

        phase = time.perf_counter()
        captured = capture_mt5_ticks(
            snapshot,
            signal,
            open_position_count=_open_trade_count(before_trades),
            intermarket=direct_intermarket,
        )
        recent_ticks = list(captured.pop("recent_ticks", []))
        tick_recorder = captured
        timing_ms["tick_recorder"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        m1_metrics = signal.metrics.get("M1", {}) if isinstance(signal.metrics, dict) else {}
        m1_atr = float(m1_metrics.get("atr", 0.0) or 0.0) if isinstance(m1_metrics, dict) else 0.0
        feature_state = build_microstructure_features(
            snapshot.symbol,
            recent_ticks,
            m1_atr=m1_atr,
        )
        feature_storage = store_microstructure_features(
            feature_state,
            cycle_timestamp=snapshot.timestamp,
        )
        microstructure = feature_state.to_dict()
        microstructure["storage"] = feature_storage
        timing_ms["microstructure"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        agents = build_scalping_agents(
            snapshot,
            signal,
            feature_state,
            news_risk,
            direct_intermarket,
        )
        meta_controller = evaluate_meta_controller(signal, agents)
        signal = apply_meta_controller_to_signal(
            signal,
            meta_controller,
            microstructure=microstructure,
            agents=agents,
            direct_intermarket=direct_intermarket,
        )
        decision_timestamp = datetime.now(timezone.utc)
        timing_ms["agent_consensus"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        risk = evaluate_scalping_risk(snapshot, signal, news_risk)
        timing_ms["risk_guard"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        request_timestamp = datetime.now(timezone.utc)
        paper = manage_scalp_paper_trades(snapshot, signal, risk, news_risk)
        response_timestamp = datetime.now(timezone.utc)
        timing_ms["paper_manager"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        after_trades = load_scalping_trades()
        execution_audit = audit_paper_trade_transition(
            before_trades,
            after_trades,
            snapshot=snapshot,
            signal=signal,
            decision_timestamp=decision_timestamp,
            request_timestamp=request_timestamp,
            response_timestamp=response_timestamp,
        )
        timing_ms["execution_audit"] = _elapsed_ms(phase)
        success = True
    except Exception as error:
        error_message = f"{type(error).__name__}: {error}"

    finished_at = datetime.now()
    core_runtime_ms = (time.perf_counter() - started_counter) * 1000.0
    timing_ms["core_total"] = round(core_runtime_ms, 3)
    cycle = ScalpingCycleState(
        success=success,
        symbol=symbol,
        started_at=started_at,
        finished_at=finished_at,
        runtime_ms=core_runtime_ms,
        snapshot=snapshot,
        signal=signal,
        news_risk=news_risk,
        risk=risk,
        paper=paper,
        error_message=error_message,
        timing_ms=timing_ms,
        tick_recorder=tick_recorder,
        microstructure=microstructure,
        agents=agents,
        meta_controller=meta_controller,
        execution_audit=execution_audit,
    )

    # Keep reporting I/O outside the decision runtime. It cannot delay the
    # decision already made, but is measured separately for diagnostics.
    try:
        phase = time.perf_counter()
        export_scalping_trade_history()
        cycle.timing_ms["trade_export"] = _elapsed_ms(phase)

        phase = time.perf_counter()
        log_scalping_cycle(cycle)
        cycle.timing_ms["cycle_log"] = _elapsed_ms(phase)
    except Exception as logging_error:
        cycle.error_message = (
            f"{cycle.error_message} | LoggingError: {logging_error}"
            if cycle.error_message
            else f"LoggingError: {logging_error}"
        )
    return cycle
