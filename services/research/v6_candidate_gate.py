from __future__ import annotations

from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _direction(value: Any) -> str:
    text = str(value or "NEUTRAL").upper()
    if text in {"BUY", "BULL", "BULLISH", "LONG"}:
        return "BUY"
    if text in {"SELL", "BEAR", "BEARISH", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def _policy(name: str) -> dict[str, Any]:
    lane = str(name or "STRICT").upper()
    if lane == "FAST":
        return {
            "name": lane,
            "winner_score": float(scalping_settings.SCALPING_V6_FAST_MIN_WINNER_SCORE),
            "score_margin": float(scalping_settings.SCALPING_V6_FAST_MIN_SCORE_MARGIN),
            "spread": float(scalping_settings.SCALPING_V6_FAST_MAX_SPREAD_USD),
            "spread_atr": float(scalping_settings.SCALPING_V6_FAST_MAX_SPREAD_ATR_RATIO),
            "vwap": 1.25, "rel_volume_min": 0.65, "rel_volume_max": 1.75,
            "micro": float(scalping_settings.SCALPING_V6_FAST_MIN_MICRO_CONFIDENCE),
            "windows": 2,
            "micro_data_quality": float(scalping_settings.SCALPING_V6_FAST_MIN_MICRO_DATA_QUALITY),
            "quote_flow": float(scalping_settings.SCALPING_V6_FAST_MIN_QUOTE_FLOW_IMBALANCE),
            "spread_expansion_atr": 0.04,
            "blocked_micro_regimes": ("STALLED", "DISLOCATED"),
            "blocked_context_regimes": ("NO_TRADE",),
            "context_direction_alignment": True,
            "fast_horizon_alignment": True,
            "max_hold_seconds": float(scalping_settings.SCALPING_V6_FAST_MAX_HOLD_SECONDS),
            "cycles": 2, "seconds": 0.40, "structure_votes": 1,
            "strict_structure_consensus": False, "location_room": False,
            "demo_eligible": False,
        }
    if lane == "BALANCED":
        return {
            "name": lane,
            "winner_score": float(scalping_settings.SCALPING_V6_BALANCED_MIN_WINNER_SCORE),
            "score_margin": float(scalping_settings.SCALPING_V6_BALANCED_MIN_SCORE_MARGIN),
            "spread": float(scalping_settings.SCALPING_V6_BALANCED_MAX_SPREAD_USD),
            "spread_atr": float(scalping_settings.SCALPING_V6_BALANCED_MAX_SPREAD_ATR_RATIO),
            "vwap": float(scalping_settings.SCALPING_V6_BALANCED_MAX_ABS_VWAP_ATR),
            "rel_volume_min": float(scalping_settings.SCALPING_V6_BALANCED_MIN_RELATIVE_VOLUME),
            "rel_volume_max": float(scalping_settings.SCALPING_V6_BALANCED_MAX_RELATIVE_VOLUME),
            "micro": float(scalping_settings.SCALPING_V6_BALANCED_MIN_MICRO_CONFIDENCE),
            "windows": int(scalping_settings.SCALPING_V6_BALANCED_MIN_DIRECTIONAL_WINDOWS),
            "micro_data_quality": 0.60,
            "quote_flow": 0.05,
            "spread_expansion_atr": 0.06,
            "blocked_micro_regimes": ("STALLED", "DISLOCATED"),
            "blocked_context_regimes": ("NO_TRADE",),
            "context_direction_alignment": True,
            "fast_horizon_alignment": False,
            "max_hold_seconds": float(scalping_settings.SCALPING_V6_MAX_HOLD_SECONDS),
            "cycles": int(scalping_settings.SCALPING_V6_BALANCED_MIN_PERSISTENCE_CYCLES),
            "seconds": float(scalping_settings.SCALPING_V6_BALANCED_MIN_PERSISTENCE_SECONDS),
            "structure_votes": int(scalping_settings.SCALPING_V6_STRUCTURE_MIN_VOTES),
            "strict_structure_consensus": True,
            "location_room": bool(scalping_settings.SCALPING_V6_BALANCED_REQUIRE_LOCATION_ROOM),
            "demo_eligible": False,
        }
    if lane == "EXPLORATORY":
        return {
            "name": lane,
            "winner_score": float(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_WINNER_SCORE),
            "score_margin": float(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_SCORE_MARGIN),
            "spread": float(scalping_settings.SCALPING_V6_EXPLORATORY_MAX_SPREAD_USD),
            "spread_atr": float(scalping_settings.SCALPING_V6_EXPLORATORY_MAX_SPREAD_ATR_RATIO),
            "vwap": float(scalping_settings.SCALPING_V6_EXPLORATORY_MAX_ABS_VWAP_ATR),
            "rel_volume_min": float(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_RELATIVE_VOLUME),
            "rel_volume_max": float(scalping_settings.SCALPING_V6_EXPLORATORY_MAX_RELATIVE_VOLUME),
            "micro": float(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_MICRO_CONFIDENCE),
            "windows": int(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_DIRECTIONAL_WINDOWS),
            "micro_data_quality": 0.50,
            "quote_flow": 0.0,
            "spread_expansion_atr": 0.10,
            "blocked_micro_regimes": ("DISLOCATED",),
            "blocked_context_regimes": (),
            "context_direction_alignment": False,
            "fast_horizon_alignment": False,
            "max_hold_seconds": float(scalping_settings.SCALPING_V6_MAX_HOLD_SECONDS),
            "cycles": int(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_PERSISTENCE_CYCLES),
            "seconds": float(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_PERSISTENCE_SECONDS),
            "structure_votes": int(scalping_settings.SCALPING_V6_EXPLORATORY_MIN_STRUCTURE_VOTES),
            "strict_structure_consensus": False,
            "location_room": bool(scalping_settings.SCALPING_V6_EXPLORATORY_REQUIRE_LOCATION_ROOM),
            "demo_eligible": False,
        }
    return {
        "name": "STRICT",
        "winner_score": float(scalping_settings.SCALPING_V6_MIN_WINNER_SCORE),
        "score_margin": float(scalping_settings.SCALPING_V6_MIN_SCORE_MARGIN),
        "spread": float(scalping_settings.SCALPING_V6_MAX_SPREAD_USD),
        "spread_atr": float(scalping_settings.SCALPING_V6_MAX_SPREAD_ATR_RATIO),
        "vwap": float(scalping_settings.SCALPING_V6_MAX_ABS_VWAP_ATR),
        "rel_volume_min": float(scalping_settings.SCALPING_V6_MIN_RELATIVE_VOLUME),
        "rel_volume_max": float(scalping_settings.SCALPING_V6_MAX_RELATIVE_VOLUME),
        "micro": float(scalping_settings.SCALPING_V6_MIN_ALIGNED_MICRO_CONFIDENCE),
        "windows": int(scalping_settings.SCALPING_V6_MIN_DIRECTIONAL_WINDOWS),
        "micro_data_quality": float(scalping_settings.SCALPING_V6_MIN_MICRO_DATA_QUALITY),
        "quote_flow": float(scalping_settings.SCALPING_V6_MIN_ALIGNED_QUOTE_FLOW_IMBALANCE),
        "spread_expansion_atr": float(scalping_settings.SCALPING_V6_MAX_SPREAD_EXPANSION_ATR),
        "blocked_micro_regimes": tuple(scalping_settings.SCALPING_V6_BLOCKED_MICRO_REGIMES),
        "blocked_context_regimes": tuple(scalping_settings.SCALPING_V6_STRICT_BLOCKED_CONTEXT_REGIMES),
        "context_direction_alignment": bool(scalping_settings.SCALPING_V6_STRICT_REQUIRE_CONTEXT_DIRECTION_ALIGNMENT),
        "fast_horizon_alignment": False,
        "max_hold_seconds": float(scalping_settings.SCALPING_V6_MAX_HOLD_SECONDS),
        "cycles": int(scalping_settings.SCALPING_V6_MIN_PERSISTENCE_CYCLES),
        "seconds": float(scalping_settings.SCALPING_V6_MIN_PERSISTENCE_SECONDS),
        "structure_votes": int(scalping_settings.SCALPING_V6_STRUCTURE_MIN_VOTES),
        "strict_structure_consensus": True,
        "location_room": bool(scalping_settings.SCALPING_V6_REQUIRE_STRUCTURE_LOCATION_ROOM),
        "demo_eligible": True,
    }


def _features(snapshot: ScalpingSnapshotState, signal: ScalpSignalState) -> dict[str, Any]:
    metrics = _dict(getattr(signal, "metrics", {}))
    diagnostics = _dict(metrics.get("score_diagnostics"))
    direct = _dict(diagnostics.get("direct_score_decision"))
    persistence = _dict(metrics.get("signal_persistence"))
    micro = _dict(metrics.get("microstructure"))
    verified = _dict(metrics.get("verified_market_context"))
    quality = _dict(_dict(metrics.get("meta_controller")).get("score_margin_quality_details"))
    entry_quality = _dict(diagnostics.get("entry_quality_decision"))
    economics = _dict(entry_quality.get("economics"))
    structure = _dict(metrics.get("v6_market_structure"))
    context_regime = _dict(_dict(metrics.get("unified_context")).get("regime") or metrics.get("regime"))

    direction = _direction(
        persistence.get("direction")
        or direct.get("winner_direction")
        or getattr(signal, "direction", "NEUTRAL")
    )
    winner = _float(direct.get("winner_score", getattr(signal, "score", 0.0)))
    margin = _float(direct.get("margin", diagnostics.get("direction_margin", 0.0)))
    micro_direction = _direction(micro.get("direction"))
    micro_confidence = _float(micro.get("confidence"))
    m1 = _dict(metrics.get("M1"))
    atr = max(_float(m1.get("atr")), 1e-9)
    spread_atr = float(snapshot.spread) / atr
    vwap_atr = _float(
        verified.get("vwap_distance_atr", quality.get("vwap_distance_atr", metrics.get("vwap_distance_atr", 999.0))),
        999.0,
    )
    rel_volume = _float(
        verified.get("relative_volume", quality.get("relative_volume", metrics.get("relative_volume", 0.0))),
        0.0,
    )
    windows = _dict(micro.get("windows"))
    directional_windows = 0
    horizon_aligned: dict[str, bool] = {}
    for seconds in ("1", "3", "5"):
        window = _dict(windows.get(seconds) or windows.get(f"{seconds}s"))
        ratio = _float(window.get("directional_tick_ratio", window.get("tick_imbalance_ratio", window.get("ratio", 0.0))))
        velocity = _float(window.get("velocity_atr_per_second", window.get("velocity", 0.0)))
        if direction == "BUY" and ratio > 0 and velocity >= 0:
            directional_windows += 1
            horizon_aligned[seconds] = True
        elif direction == "SELL" and ratio < 0 and velocity <= 0:
            directional_windows += 1
            horizon_aligned[seconds] = True
        else:
            horizon_aligned[seconds] = False
    if not windows and micro_direction == direction:
        directional_windows = int(scalping_settings.SCALPING_V6_MIN_DIRECTIONAL_WINDOWS)
    primary_window = _dict(windows.get("3") or windows.get("3s"))
    quote_flow = _float(primary_window.get("quote_flow_imbalance_proxy"))
    spread_expansion_atr = _float(primary_window.get("spread_expansion")) / atr
    micro_data_quality = _float(micro.get("data_quality"))
    micro_regime = str(micro.get("micro_regime", "UNKNOWN") or "UNKNOWN").upper()

    structure_direction = _direction(structure.get("consensus_direction"))
    buy_votes = int(structure.get("buy_votes", 0) or 0)
    sell_votes = int(structure.get("sell_votes", 0) or 0)
    direction_votes = buy_votes if direction == "BUY" else sell_votes if direction == "SELL" else 0
    opposite_votes = sell_votes if direction == "BUY" else buy_votes if direction == "SELL" else 0
    hard_meta_blocks = list(_dict(metrics.get("meta_controller")).get("hard_signal_blocks", []) or [])
    return {
        "direction": direction,
        "winner": winner,
        "margin": margin,
        "micro_direction": micro_direction,
        "micro_confidence": micro_confidence,
        "spread_atr": spread_atr,
        "vwap_atr": vwap_atr,
        "rel_volume": rel_volume,
        "directional_windows": directional_windows,
        "fast_horizons_aligned": bool(horizon_aligned.get("1")) and bool(horizon_aligned.get("5")),
        "micro_data_quality": micro_data_quality,
        "quote_flow": quote_flow,
        "spread_expansion_atr": spread_expansion_atr,
        "micro_regime": micro_regime,
        "context_regime_mode": str(context_regime.get("mode", "UNKNOWN") or "UNKNOWN").upper(),
        "context_regime_direction": _direction(context_regime.get("direction")),
        "persistence_cycles": int(persistence.get("consecutive_cycles", 0) or 0),
        "persistence_seconds": _float(persistence.get("elapsed_seconds")),
        "direct_passed": bool(direct.get("passed", False)),
        "hard_meta_blocks": hard_meta_blocks,
        "economics_barrier": bool(economics.get("barrier_asymmetry_ok", True)),
        "structure": structure,
        "structure_direction": structure_direction,
        "structure_votes": int(structure.get("consensus_votes", 0) or 0),
        "buy_votes": buy_votes,
        "sell_votes": sell_votes,
        "direction_votes": direction_votes,
        "opposite_votes": opposite_votes,
    }


def _evaluate_policy(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    policy: dict[str, Any],
    *,
    extracted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    f = extracted or _features(snapshot, signal)
    direction = str(f["direction"])
    if bool(policy["strict_structure_consensus"]):
        structure_ok = (
            f["structure_direction"] == direction
            and int(f["structure_votes"]) >= int(policy["structure_votes"])
        )
    else:
        # Research-only lane: at least one family must support the candidate and
        # there may not be a 2/3 consensus in the opposite direction.
        structure_ok = (
            int(f["direction_votes"]) >= int(policy["structure_votes"])
            and int(f["opposite_votes"]) < int(scalping_settings.SCALPING_V6_STRUCTURE_MIN_VOTES)
        )
    checks = {
        "direction": direction in {"BUY", "SELL"},
        "direct_score": bool(f["direct_passed"]),
        "winner_score": float(f["winner"]) + 1e-9 >= float(policy["winner_score"]),
        "score_margin": float(f["margin"]) + 1e-9 >= float(policy["score_margin"]),
        "spread": float(snapshot.spread) <= float(policy["spread"]) + 1e-9,
        "quote_fresh": _float(getattr(snapshot, "quote_age_seconds", 0.0)) <= float(scalping_settings.SCALPING_V6_MAX_QUOTE_AGE_SECONDS),
        "spread_atr": float(f["spread_atr"]) <= float(policy["spread_atr"]) + 1e-9,
        "vwap_location": abs(float(f["vwap_atr"])) <= float(policy["vwap"]) + 1e-9,
        "relative_volume": float(policy["rel_volume_min"]) <= float(f["rel_volume"]) <= float(policy["rel_volume_max"]),
        "micro_alignment": f["micro_direction"] == direction and float(f["micro_confidence"]) + 1e-9 >= float(policy["micro"]),
        "micro_window_consistency": int(f["directional_windows"]) >= int(policy["windows"]),
        "micro_data_quality": float(f["micro_data_quality"]) + 1e-9 >= float(policy["micro_data_quality"]),
        "quote_flow_alignment": (
            (direction == "BUY" and float(f["quote_flow"]) + 1e-9 >= float(policy["quote_flow"]))
            or (direction == "SELL" and float(f["quote_flow"]) - 1e-9 <= -float(policy["quote_flow"]))
        ),
        "spread_stability": float(f["spread_expansion_atr"]) <= float(policy["spread_expansion_atr"]) + 1e-9,
        "micro_regime_safe": str(f["micro_regime"]) not in set(policy["blocked_micro_regimes"]),
        "context_regime_safe": str(f["context_regime_mode"]) not in set(policy["blocked_context_regimes"]),
        "context_regime_alignment": (
            not bool(policy["context_direction_alignment"])
            or str(f["context_regime_direction"]) in {"NEUTRAL", direction}
        ),
        "fast_horizon_alignment": (not bool(policy["fast_horizon_alignment"])) or bool(f["fast_horizons_aligned"]),
        "persistence_cycles": int(f["persistence_cycles"]) >= int(policy["cycles"]),
        "persistence_seconds": float(f["persistence_seconds"]) + 1e-9 >= float(policy["seconds"]),
        "hard_meta_safe": not f["hard_meta_blocks"],
        "economics_barrier": bool(f["economics_barrier"]),
        "structure_consensus": bool(structure_ok),
        "structure_location_safe": (not bool(policy["location_room"])) or bool(f["structure"].get("location_safe", False)),
    }
    if not bool(scalping_settings.SCALPING_V6_REQUIRE_TICK_DIRECTION_CONSISTENCY):
        checks["micro_window_consistency"] = True
    if float(f["rel_volume"]) <= 0:
        checks["relative_volume"] = False
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "lane": str(policy["name"]),
        "demo_eligible": bool(policy["demo_eligible"]),
        "allowed": not failed,
        "direction": direction,
        "checks": checks,
        "failed_checks": failed,
        "winner_score": round(float(f["winner"]), 4),
        "score_margin": round(float(f["margin"]), 4),
        "spread_usd": round(float(snapshot.spread), 5),
        "spread_atr": round(float(f["spread_atr"]), 6),
        "vwap_distance_atr": round(float(f["vwap_atr"]), 6),
        "relative_volume": round(float(f["rel_volume"]), 6),
        "micro_direction": str(f["micro_direction"]),
        "micro_confidence": round(float(f["micro_confidence"]), 6),
        "directional_micro_windows": int(f["directional_windows"]),
        "micro_data_quality": round(float(f["micro_data_quality"]), 6),
        "micro_quote_flow_imbalance": round(float(f["quote_flow"]), 6),
        "micro_spread_expansion_atr": round(float(f["spread_expansion_atr"]), 6),
        "micro_regime": str(f["micro_regime"]),
        "context_regime_mode": str(f["context_regime_mode"]),
        "context_regime_direction": str(f["context_regime_direction"]),
        "fast_horizons_aligned": bool(f["fast_horizons_aligned"]),
        "max_hold_seconds": float(policy["max_hold_seconds"]),
        "persistence_cycles": int(f["persistence_cycles"]),
        "persistence_seconds": round(float(f["persistence_seconds"]), 6),
        "required_persistence_cycles": int(policy["cycles"]),
        "required_persistence_seconds": float(policy["seconds"]),
        "hard_meta_blocks": list(f["hard_meta_blocks"]),
        "structure_direction": str(f["structure_direction"]),
        "structure_votes": int(f["structure_votes"]),
        "structure_buy_votes": int(f["buy_votes"]),
        "structure_sell_votes": int(f["sell_votes"]),
        "structure_confidence": round(_float(f["structure"].get("confidence")), 6),
        "structure_location_safe": bool(f["structure"].get("location_safe", False)),
        "structure_room_usd": round(_float(f["structure"].get("room_to_target_usd")), 5),
        "structure_reason": str(f["structure"].get("reason", "")),
        "policy": dict(policy),
        "reason": (
            f"V6 {policy['name']} lane passed."
            if not failed
            else f"V6 {policy['name']} lane blocked: " + ", ".join(failed) + "."
        ),
    }


def evaluate_v6_candidate_gate(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
) -> dict[str, Any]:
    """Evaluate the only lane eligible for controlled-demo execution."""
    return _evaluate_policy(snapshot, signal, _policy("STRICT"))


def evaluate_v6_shadow_lane_gates(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
) -> dict[str, dict[str, Any]]:
    """Evaluate strict, balanced and exploratory shadow hypotheses.

    FAST, BALANCED and EXPLORATORY are simulation-only and are never consumed by the
    MT5 demo execution path. This creates enough counterfactual observations to
    compare policies without weakening broker safety.
    """
    extracted = _features(snapshot, signal)
    return {
        lane: _evaluate_policy(snapshot, signal, _policy(lane), extracted=extracted)
        for lane in ("STRICT", "FAST", "BALANCED", "EXPLORATORY")
    }


def apply_v6_candidate_gate(
    signal: ScalpSignalState,
    gate: dict[str, Any],
) -> ScalpSignalState:
    """Apply the exact STRICT V6 research gate to controlled-demo execution."""
    if str(gate.get("lane", "STRICT")).upper() != "STRICT" or not bool(gate.get("demo_eligible", True)):
        raise ValueError("Only the STRICT V6 lane may be applied to demo execution.")
    if not isinstance(signal.metrics, dict):
        signal.metrics = {}
    signal.metrics["v6_candidate_gate"] = gate
    signal.target_profit_usd = float(scalping_settings.SCALPING_V6_TARGET_USD)
    signal.stop_loss_usd = float(scalping_settings.SCALPING_V6_HARD_STOP_USD)
    direction = _direction(gate.get("direction"))
    if bool(gate.get("allowed", False)) and direction in {"BUY", "SELL"}:
        signal.allowed = True
        signal.action = direction
        signal.direction = direction
        signal.pattern = "V6_STRUCTURE_CONFIRMED_DEMO"
        signal.signal_key = (
            f"V6:{direction}:{gate.get('winner_score')}:{gate.get('score_margin')}:"
            f"{gate.get('structure_direction')}:{gate.get('structure_votes')}"
        )
        signal.block_reasons = []
        return signal
    signal.allowed = False
    signal.action = "WAIT"
    reason = str(gate.get("reason", "V6 candidate gate blocked entry."))
    if reason and reason not in signal.block_reasons:
        signal.block_reasons.append(reason)
    return signal
