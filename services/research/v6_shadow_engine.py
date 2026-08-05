from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.execution.scalp_profit_calculator import calculate_scalp_profit, find_price_for_profit
from services.research.v63_barrier_policy import build_v63_barrier_plan
from services.utils.atomic_json import atomic_write_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json_state(path_value: str, default: dict[str, Any]) -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except (OSError, json.JSONDecodeError):
        recovered = dict(default)
        recovered["state_recovered"] = True
        return recovered


def _save_json_state(path_value: str, state: dict[str, Any]) -> str:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(str(path), state, indent=2)


def _append_jsonl(path_value: str, payload: dict[str, Any]) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, default=str) + "\n"
    for attempt in range(10):
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    # Research logging must never crash the market-data loop.


def _pnl(snapshot: ScalpingSnapshotState, trade: dict[str, Any]) -> float:
    direction = str(trade["direction"])
    exit_price = float(snapshot.bid if direction == "BUY" else snapshot.ask)
    value, _ = calculate_scalp_profit(
        symbol=snapshot.symbol,
        direction=direction,
        entry_price=float(trade["entry_price"]),
        exit_price=exit_price,
        lot_size=float(trade.get("lot_size", scalping_settings.SCALPING_LOT_SIZE)),
        contract_size=float(trade.get("contract_size", snapshot.contract_size)),
    )
    return float(value)


def _candidate_key(snapshot: ScalpingSnapshotState, gate: dict[str, Any], lane: str) -> str:
    bucket = max(float(scalping_settings.SCALPING_V6_CANDIDATE_PRICE_BUCKET_USD), 0.01)
    price_bucket = round(float(snapshot.mid) / bucket)
    return f"{lane}:{gate.get('direction')}:{snapshot.session}:{price_bucket}"


def build_v6_entry_profile(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    gate: dict[str, Any],
    lane: str,
) -> dict[str, Any]:
    metrics = _dict(signal.metrics)
    m1 = _dict(metrics.get("M1"))
    verified = _dict(metrics.get("verified_market_context"))
    structure = _dict(metrics.get("v6_market_structure"))
    families = _dict(structure.get("families"))
    cross_market = _dict(metrics.get("cross_market_context"))
    direct_intermarket = _dict(metrics.get("direct_intermarket_context"))
    micro = _dict(metrics.get("microstructure"))
    micro_windows = _dict(micro.get("windows"))
    primary_micro = _dict(micro_windows.get("3"))
    if not primary_micro and micro_windows:
        primary_micro = _dict(next(iter(micro_windows.values())))
    micro_atr = max(_float(m1.get("atr")), 1e-9)
    return {
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "shadow_lane": lane,
        "demo_eligible": bool(gate.get("demo_eligible", False)),
        "symbol": snapshot.symbol,
        "session": snapshot.session,
        "direction": gate.get("direction"),
        "winner_score": gate.get("winner_score"),
        "score_margin": gate.get("score_margin"),
        "spread_usd": gate.get("spread_usd"),
        "spread_atr": gate.get("spread_atr"),
        "vwap_distance_atr": gate.get("vwap_distance_atr"),
        "relative_volume": gate.get("relative_volume"),
        "micro_direction": gate.get("micro_direction"),
        "micro_confidence": gate.get("micro_confidence"),
        "directional_micro_windows": gate.get("directional_micro_windows"),
        "micro_data_quality": _float(micro.get("data_quality")),
        "micro_regime": micro.get("micro_regime", "UNKNOWN"),
        "micro_regime_confidence": _float(micro.get("micro_regime_confidence")),
        "micro_quote_flow_imbalance": _float(primary_micro.get("quote_flow_imbalance_proxy")),
        "micro_efficiency_ratio": _float(primary_micro.get("efficiency_ratio")),
        "micro_stall_ratio": _float(primary_micro.get("stall_ratio"), 1.0),
        "micro_spread_expansion_atr": _float(primary_micro.get("spread_expansion")) / micro_atr,
        "micro_arrival_acceleration": _float(primary_micro.get("arrival_acceleration")),
        "micro_velocity_atr_s": _float(primary_micro.get("velocity_atr_per_second")),
        "micro_reversal_ratio": _float(primary_micro.get("reversal_ratio")),
        "persistence_cycles": gate.get("persistence_cycles"),
        "persistence_seconds": gate.get("persistence_seconds"),
        "m1_atr": _float(m1.get("atr")),
        "m1_rsi": _float(m1.get("rsi")),
        "m1_momentum": _float(m1.get("momentum")),
        "adx": _float(verified.get("adx_m5", verified.get("adx"))),
        "regime": _dict(metrics.get("unified_context")).get("regime") or metrics.get("regime"),
        "pattern": signal.pattern,
        "structure_direction": structure.get("consensus_direction"),
        "structure_votes": structure.get("consensus_votes"),
        "structure_buy_votes": structure.get("buy_votes"),
        "structure_sell_votes": structure.get("sell_votes"),
        "structure_confidence": structure.get("confidence"),
        "structure_location_safe": structure.get("location_safe"),
        "structure_room_usd": structure.get("room_to_target_usd"),
        "htf_direction": _dict(families.get("htf_trend")).get("direction"),
        "level_direction": _dict(families.get("support_resistance")).get("direction"),
        "level_event": _dict(families.get("support_resistance")).get("event"),
        "order_block_direction": _dict(families.get("order_block")).get("direction"),
        "entry_hour_utc": datetime.now(timezone.utc).hour + datetime.now(timezone.utc).minute / 60.0,
        "model_probability_win": gate.get("model_probability_win"),
        "model_probability_threshold": gate.get("model_probability_threshold"),
        "model_name": gate.get("model_name"),
        "cross_market_status": cross_market.get("status"),
        "cross_market_gold_bias": cross_market.get("gold_bias"),
        "cross_market_pressure_score": cross_market.get("pressure_score"),
        "cross_market_available_symbols": cross_market.get("available_symbols"),
        "direct_intermarket_status": direct_intermarket.get("status"),
        "direct_intermarket_gold_bias": direct_intermarket.get("gold_bias"),
        "direct_intermarket_pressure_score": direct_intermarket.get("pressure_score"),
        "direct_intermarket_resolved_symbols": len(_dict(direct_intermarket.get("resolved_symbols"))),
    }


def _new_rearm_state() -> dict[str, Any]:
    return {
        "required": False,
        "reason": "",
        "direction": "NEUTRAL",
        "structure_direction": "NEUTRAL",
        "closed_at": "",
        "rearmed_at": "",
        "blocked_cycles": 0,
    }


def _arm_after_exit(
    lane_state: dict[str, Any],
    *,
    close_reason: str,
    direction: str,
    structure_direction: str,
    closed_at: str,
) -> None:
    if not bool(getattr(scalping_settings, "SCALPING_V6_EPISODE_REARM_ENABLED", True)):
        lane_state["rearm"] = _new_rearm_state()
        return
    lane_state["rearm"] = {
        "required": True,
        "reason": str(close_reason),
        "direction": str(direction).upper(),
        "structure_direction": str(structure_direction or "NEUTRAL").upper(),
        "closed_at": str(closed_at),
        "rearmed_at": "",
        "blocked_cycles": 0,
    }


def _evaluate_rearm(
    lane_state: dict[str, Any],
    gate: dict[str, Any],
    *,
    now_iso: str,
) -> tuple[bool, bool, str]:
    """Return (blocked, rearmed_this_cycle, message).

    Normal exits require one fully invalid candidate observation before a new
    episode can start. A hard stop requires the prior structural direction to
    reset, so the same invalidated thesis cannot be traded repeatedly.
    """

    rearm = lane_state.get("rearm") if isinstance(lane_state.get("rearm"), dict) else _new_rearm_state()
    if not bool(rearm.get("required", False)):
        lane_state["rearm"] = rearm
        return False, False, ""

    locked_direction = str(rearm.get("direction", "NEUTRAL")).upper()
    current_direction = str(gate.get("direction", "NEUTRAL")).upper()
    structure_direction = str(gate.get("structure_direction", "NEUTRAL")).upper()
    exit_reason = str(rearm.get("reason", ""))
    hard_stop_lock = bool(
        exit_reason == "TRIPLE_BARRIER_HARD_STOP"
        and getattr(scalping_settings, "SCALPING_V6_HARD_STOP_STRUCTURE_RESET_REQUIRED", True)
    )
    failed_thesis_lock = bool(
        exit_reason in {"NO_PROGRESS_THESIS_EXIT", "STRONG_OPPOSITE_TAPE_EXIT"}
        and getattr(
            scalping_settings,
            "SCALPING_V6_FAILED_THESIS_DIRECTION_RESET_REQUIRED",
            True,
        )
    )
    if failed_thesis_lock:
        # A transient micro/gate miss is not evidence of a new market episode.
        # Require the directional candidate itself to reset before risking the
        # spread again. This prevents clusters of near-identical failed entries.
        reset_observed = current_direction != locked_direction
        waiting_for = "candidate direction to reset"
    elif hard_stop_lock:
        reset_observed = bool(
            current_direction != locked_direction
            or structure_direction != locked_direction
        )
        waiting_for = "higher-timeframe structure to reset"
    else:
        reset_observed = not bool(gate.get("allowed", False))
        waiting_for = "one invalid candidate observation"

    if reset_observed:
        rearm["required"] = False
        rearm["rearmed_at"] = now_iso
        lane_state["rearm"] = rearm
        return False, True, f"Episode rearmed after {rearm.get('reason', 'exit')}."

    rearm["blocked_cycles"] = int(rearm.get("blocked_cycles", 0) or 0) + 1
    lane_state["rearm"] = rearm
    return True, False, f"Re-entry blocked after {rearm.get('reason', 'exit')}; waiting for {waiting_for}."


def _lane_paths(lane: str) -> tuple[str, str]:
    normalized = str(lane).upper()
    if normalized == "STRICT":
        return (
            str(scalping_settings.SCALPING_V6_SHADOW_HISTORY_PATH),
            str(scalping_settings.SCALPING_V6_SHADOW_CANDIDATES_PATH),
        )
    history = Path(scalping_settings.SCALPING_V6_SHADOW_LANE_HISTORY_FOLDER) / f"{normalized.lower()}_history.jsonl"
    candidates = Path(scalping_settings.SCALPING_V6_SHADOW_LANE_CANDIDATES_FOLDER) / f"{normalized.lower()}_candidates.jsonl"
    return str(history), str(candidates)


def _update_lane(
    lane_state: dict[str, Any],
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    gate: dict[str, Any],
    lane: str,
    *,
    history_path: str,
    candidates_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    trade = lane_state.get("open_trade") if isinstance(lane_state.get("open_trade"), dict) else None
    now = datetime.now(timezone.utc)
    action = "NO_ACTION"
    message = "No shadow position action required."
    closed_record: dict[str, Any] | None = None
    closed_this_cycle = False
    rearmed_this_cycle = False

    if "rearm" not in lane_state or not isinstance(lane_state.get("rearm"), dict):
        lane_state["rearm"] = _new_rearm_state()

    if trade:
        # Measure active fresh-feed holding time, not raw wall-clock time. Long
        # gaps caused by a frozen/closed MT5 feed are excluded from the triple
        # barrier clock so a position cannot expire artificially on reopen.
        now_epoch = time.time()
        previous_epoch = _float(trade.get("last_fresh_update_epoch"), now_epoch)
        gap = max(0.0, now_epoch - previous_epoch)
        unmonitored_session_gap = bool(
            previous_epoch > 0.0
            and gap > float(scalping_settings.SCALPING_V6_MAX_RESEARCH_MONITORING_GAP_SECONDS)
        )
        active_age = _float(trade.get("active_hold_seconds"), 0.0)
        maximum_fresh_gap = float(scalping_settings.SCALPING_V6_FEED_PAUSE_QUOTE_AGE_SECONDS) + 0.5
        if gap <= maximum_fresh_gap:
            active_age += gap
        else:
            trade["feed_pause_seconds_ignored"] = round(
                _float(trade.get("feed_pause_seconds_ignored"), 0.0) + gap, 3
            )
        trade["last_fresh_update_epoch"] = now_epoch
        trade["active_hold_seconds"] = round(active_age, 3)
        age = active_age
        pnl = _pnl(snapshot, trade)
        trade["current_profit_usd"] = round(pnl, 4)
        trade["peak_profit_usd"] = round(max(_float(trade.get("peak_profit_usd"), pnl), pnl), 4)
        trade["max_adverse_profit_usd"] = round(min(_float(trade.get("max_adverse_profit_usd"), pnl), pnl), 4)
        trade["hold_seconds"] = round(age, 3)
        reason = ""
        if unmonitored_session_gap:
            reason = "UNMONITORED_SESSION_GAP"
        elif pnl >= float(trade["target_profit_usd"]):
            reason = "TRIPLE_BARRIER_TARGET"
        elif pnl <= -float(trade["hard_stop_usd"]):
            reason = "TRIPLE_BARRIER_HARD_STOP"
        elif (
            trade["peak_profit_usd"] >= float(scalping_settings.SCALPING_V6_BREAKEVEN_TRIGGER_USD)
            and pnl <= float(scalping_settings.SCALPING_V6_BREAKEVEN_FLOOR_USD)
        ):
            reason = "BREAKEVEN_PROTECTION"
        elif (
            trade["peak_profit_usd"] >= float(trade["target_profit_usd"]) * float(scalping_settings.SCALPING_V63_PROFIT_LOCK_STAGE2_PEAK_RATIO)
            and pnl <= float(trade["target_profit_usd"]) * float(scalping_settings.SCALPING_V63_PROFIT_LOCK_STAGE2_FLOOR_RATIO)
        ):
            reason = "PROFIT_LOCK_STAGE2_EXIT"
        elif (
            trade["peak_profit_usd"] >= float(trade["target_profit_usd"]) * float(scalping_settings.SCALPING_V63_PROFIT_LOCK_STAGE1_PEAK_RATIO)
            and pnl <= float(trade["target_profit_usd"]) * float(scalping_settings.SCALPING_V63_PROFIT_LOCK_STAGE1_FLOOR_RATIO)
        ):
            reason = "PROFIT_LOCK_STAGE1_EXIT"
        elif (
            age >= float(scalping_settings.SCALPING_V6_NO_PROGRESS_CHECK_SECONDS)
            and trade["peak_profit_usd"] < float(scalping_settings.SCALPING_V6_NO_PROGRESS_MAX_MFE_USD)
            and pnl <= float(scalping_settings.SCALPING_V6_NO_PROGRESS_EXIT_PNL_USD)
        ):
            reason = "NO_PROGRESS_THESIS_EXIT"
        else:
            metrics = _dict(signal.metrics)
            micro = _dict(metrics.get("microstructure"))
            micro_direction = str(micro.get("direction", "NEUTRAL")).upper()
            micro_confidence = _float(micro.get("confidence"))
            opposite = "SELL" if trade["direction"] == "BUY" else "BUY"
            if (
                age >= float(scalping_settings.SCALPING_V6_MIN_HOLD_BEFORE_THESIS_EXIT_SECONDS)
                and micro_direction == opposite
                and micro_confidence >= float(scalping_settings.SCALPING_V6_STRONG_OPPOSITE_EXIT_CONFIDENCE)
                and pnl < 0.0
            ):
                reason = "STRONG_OPPOSITE_TAPE_EXIT"
        if not reason and age >= float(trade["max_hold_seconds"]):
            reason = "TRIPLE_BARRIER_TIME"
        if reason:
            observed_exit_price = float(snapshot.bid if trade["direction"] == "BUY" else snapshot.ask)
            observed_market_pnl = float(pnl)
            simulated_exit_price = observed_exit_price
            simulated_fill_pnl = observed_market_pnl
            fill_model = "OBSERVED_EXECUTABLE_QUOTE"
            fill_price_method = "OBSERVED_EXECUTABLE_QUOTE"
            planned_barrier_profit = None
            barrier_overshoot = 0.0

            # A polled shadow loop can first observe price well beyond a
            # profitable target. Crediting the entire later quote would make
            # research results more optimistic than a broker-side TP. V6.3.2
            # therefore books target crossings at the planned barrier while
            # adverse stop crossings remain charged at the observed quote.
            target_fill_mode = str(
                getattr(
                    scalping_settings,
                    "SCALPING_V632_SHADOW_TARGET_FILL_MODE",
                    "PLANNED_BARRIER",
                )
            ).upper()
            if reason == "TRIPLE_BARRIER_TARGET" and target_fill_mode == "PLANNED_BARRIER":
                planned_barrier_profit = float(trade["target_profit_usd"])
                simulated_fill_pnl = min(observed_market_pnl, planned_barrier_profit)
                simulated_exit_price, fill_price_method = find_price_for_profit(
                    symbol=snapshot.symbol,
                    direction=str(trade["direction"]),
                    entry_price=float(trade["entry_price"]),
                    lot_size=float(trade.get("lot_size", scalping_settings.SCALPING_LOT_SIZE)),
                    contract_size=float(trade.get("contract_size", snapshot.contract_size)),
                    target_profit_usd=simulated_fill_pnl,
                    point=float(getattr(snapshot, "point", 0.01)),
                )
                fill_model = "PLANNED_TARGET_BARRIER"
                barrier_overshoot = max(0.0, observed_market_pnl - simulated_fill_pnl)

            closed_record = {
                **trade,
                "status": "CLOSED",
                "closed_at": now.isoformat(),
                "exit_price": float(simulated_exit_price),
                "observed_exit_price": observed_exit_price,
                "observed_market_profit_usd": round(observed_market_pnl, 4),
                "final_profit_usd": round(simulated_fill_pnl, 4),
                "planned_barrier_profit_usd": (
                    round(planned_barrier_profit, 4)
                    if planned_barrier_profit is not None
                    else None
                ),
                "barrier_overshoot_usd": round(barrier_overshoot, 4),
                "shadow_fill_model": fill_model,
                "shadow_fill_price_method": fill_price_method,
                "close_reason": reason,
                "research_eligible": not unmonitored_session_gap,
                "research_exclusion_reason": (
                    "Position was first re-observed after an unmonitored process gap "
                    f"of {gap:.3f} seconds. Observed P/L is audit-only."
                    if unmonitored_session_gap
                    else ""
                ),
            }
            _append_jsonl(history_path, closed_record)
            lane_state["open_trade"] = None
            _arm_after_exit(
                lane_state,
                close_reason=reason,
                direction=str(trade["direction"]),
                structure_direction=str(gate.get("structure_direction", "NEUTRAL")),
                closed_at=now.isoformat(),
            )
            closed_this_cycle = True
            action = "CLOSE_SHADOW"
            if barrier_overshoot > 0:
                message = (
                    f"Closed {lane} shadow {trade['direction']} at ${simulated_fill_pnl:.2f}: "
                    f"{reason} (observed ${observed_market_pnl:.2f}; "
                    f"${barrier_overshoot:.2f} target overshoot not credited)."
                )
            else:
                message = (
                    f"Closed {lane} shadow {trade['direction']} at "
                    f"${simulated_fill_pnl:.2f}: {reason}."
                )
        else:
            lane_state["open_trade"] = trade
            action = "MONITOR_SHADOW"
            message = f"{lane} shadow {trade['direction']} open: ${pnl:.2f}, age={age:.1f}s."

    rearm_blocked = False
    if lane_state.get("open_trade") is None and not closed_this_cycle:
        rearm_blocked, rearmed_this_cycle, rearm_message = _evaluate_rearm(
            lane_state, gate, now_iso=now.isoformat()
        )
        if rearm_blocked:
            action = "REARM_BLOCKED"
            message = rearm_message
        elif rearmed_this_cycle:
            action = "EPISODE_REARMED"
            message = rearm_message

    if (
        lane_state.get("open_trade") is None
        and not closed_this_cycle
        and not rearm_blocked
        and not rearmed_this_cycle
        and bool(gate.get("allowed", False))
    ):
        key = _candidate_key(snapshot, gate, lane)
        last = lane_state.get("last_candidate") if isinstance(lane_state.get("last_candidate"), dict) else {}
        last_time = _float(last.get("timestamp_epoch"), 0.0)
        duplicate = last.get("key") == key and time.time() - last_time < float(scalping_settings.SCALPING_V6_CANDIDATE_DEDUP_SECONDS)
        candidate_record = {
            "recorded_at": now.isoformat(),
            "shadow_lane": lane,
            "candidate_key": key,
            "accepted": not duplicate,
            "duplicate": duplicate,
            "gate": gate,
            "profile": build_v6_entry_profile(snapshot, signal, gate, lane),
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "mid": snapshot.mid,
        }
        _append_jsonl(candidates_path, candidate_record)
        if not duplicate:
            direction = str(gate["direction"])
            entry = float(snapshot.ask if direction == "BUY" else snapshot.bid)
            barrier_plan = build_v63_barrier_plan(snapshot, gate)
            lane_state["open_trade"] = {
                "status": "OPEN",
                "shadow_lane": lane,
                "demo_eligible": bool(gate.get("demo_eligible", False)),
                "opened_at": now.isoformat(),
                "decision_timestamp_utc": now.isoformat(),
                "candidate_key": key,
                "direction": direction,
                "entry_price": entry,
                "lot_size": float(scalping_settings.SCALPING_LOT_SIZE),
                "contract_size": float(snapshot.contract_size),
                "target_profit_usd": float(barrier_plan["target_profit_usd"]),
                "hard_stop_usd": float(barrier_plan["hard_stop_usd"]),
                "barrier_plan": barrier_plan,
                "max_hold_seconds": float(gate.get("max_hold_seconds", scalping_settings.SCALPING_V6_MAX_HOLD_SECONDS)),
                "peak_profit_usd": -float(snapshot.spread),
                "max_adverse_profit_usd": -float(snapshot.spread),
                "active_hold_seconds": 0.0,
                "last_fresh_update_epoch": time.time(),
                "feed_pause_seconds_ignored": 0.0,
                "entry_profile": candidate_record["profile"],
                "gate": gate,
            }
            lane_state["last_candidate"] = {"key": key, "timestamp_epoch": time.time()}
            action = "OPEN_SHADOW"
            message = f"Opened {lane} shadow {direction} at {entry:.5f}."

    lane_state["updated_at"] = now.isoformat()
    return lane_state, {
        "lane": lane,
        "action": action,
        "message": message,
        "open_trade": lane_state.get("open_trade"),
        "closed_record": closed_record,
        "closed_this_cycle": closed_this_cycle,
        "rearmed_this_cycle": rearmed_this_cycle,
        "rearm": lane_state.get("rearm"),
        "history_path": history_path,
        "candidates_path": candidates_path,
    }


def update_v6_shadow(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    gate: dict[str, Any],
) -> dict[str, Any]:
    """Backward-compatible single STRICT-lane shadow engine."""
    state = _load_json_state(
        str(scalping_settings.SCALPING_V6_SHADOW_STATE_PATH),
        {"open_trade": None, "last_candidate": None, "rearm": _new_rearm_state(), "started_at": _now_iso()},
    )
    state, result = _update_lane(
        state,
        snapshot,
        signal,
        gate,
        "STRICT",
        history_path=str(scalping_settings.SCALPING_V6_SHADOW_HISTORY_PATH),
        candidates_path=str(scalping_settings.SCALPING_V6_SHADOW_CANDIDATES_PATH),
    )
    state["updated_at"] = _now_iso()
    _save_json_state(str(scalping_settings.SCALPING_V6_SHADOW_STATE_PATH), state)
    result["state_path"] = str(scalping_settings.SCALPING_V6_SHADOW_STATE_PATH)
    return result


def update_v6_shadow_lanes(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    lane_gates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Update independent STRICT/FAST/BALANCED/EXPLORATORY/LEARNED books."""
    state_path = str(scalping_settings.SCALPING_V6_SHADOW_LANE_STATE_PATH)
    state = _load_json_state(state_path, {"lanes": {}, "started_at": _now_iso()})
    lanes_state = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    results: dict[str, dict[str, Any]] = {}
    lane_names = ["STRICT", "FAST", "BALANCED", "EXPLORATORY"]
    if bool(getattr(scalping_settings, "SCALPING_V63_LEARNED_LANE_ENABLED", True)):
        lane_names.append(str(scalping_settings.SCALPING_V63_LEARNED_LANE_NAME).upper())
    for lane in lane_names:
        gate = lane_gates.get(lane, {"allowed": False, "direction": "NEUTRAL"})
        lane_state = lanes_state.get(lane) if isinstance(lanes_state.get(lane), dict) else {
            "open_trade": None,
            "last_candidate": None,
            "rearm": _new_rearm_state(),
            "started_at": _now_iso(),
        }
        history_path, candidates_path = _lane_paths(lane)
        lane_state, lane_result = _update_lane(
            lane_state,
            snapshot,
            signal,
            gate,
            lane,
            history_path=history_path,
            candidates_path=candidates_path,
        )
        lanes_state[lane] = lane_state
        results[lane] = lane_result
    state["lanes"] = lanes_state
    state["updated_at"] = _now_iso()
    _save_json_state(state_path, state)
    opened = [name for name, item in results.items() if item["action"] == "OPEN_SHADOW"]
    closed = [name for name, item in results.items() if item["action"] == "CLOSE_SHADOW"]
    return {
        "lanes": results,
        "opened_lanes": opened,
        "closed_lanes": closed,
        "state_path": state_path,
        "any_open_trade": any(bool(item.get("open_trade")) for item in results.values()),
    }
