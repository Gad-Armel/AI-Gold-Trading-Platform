from __future__ import annotations

import copy
import threading
import time
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState


_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "direction": "NEUTRAL",
    "count": 0,
    "first_seen": 0.0,
    "last_seen": 0.0,
    "last_observation_id": None,
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_direction(value: Any) -> str:
    text = str(value or "NEUTRAL").strip().upper()
    if text in {"BUY", "BULL", "BULLISH", "LONG"}:
        return "BUY"
    if text in {"SELL", "BEAR", "BEARISH", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def reset_demo_signal_persistence() -> None:
    with _LOCK:
        _STATE.update(
            {
                "direction": "NEUTRAL",
                "count": 0,
                "first_seen": 0.0,
                "last_seen": 0.0,
                "last_observation_id": None,
            }
        )


def _candidate_context(signal: ScalpSignalState) -> dict[str, Any]:
    """Resolve a trackable candidate independently from final meta permission.

    V5.2.0 required ``signal.allowed`` before persistence could start. When the
    meta-controller rejected only a soft timing/location rule, persistence
    therefore remained permanently at 0/3 and could never provide the evidence
    needed by the final entry policy. V5.2.1 separates a hard-safe directional
    candidate from final order authorization.
    """

    metrics = _dict(getattr(signal, "metrics", {}))
    diagnostics = _dict(metrics.get("score_diagnostics"))
    direct = _dict(diagnostics.get("direct_score_decision"))
    micro = _dict(metrics.get("microstructure"))
    meta = _dict(metrics.get("meta_controller"))
    meta_checks = _dict(meta.get("checks"))

    direction = _normalize_direction(
        direct.get("winner_direction")
        or _dict(metrics.get("technical_candidate")).get("direction")
        or getattr(signal, "direction", "NEUTRAL")
    )
    winner = _float(direct.get("winner_score", getattr(signal, "score", 0.0)))
    margin = _float(direct.get("margin", diagnostics.get("direction_margin", 0.0)))
    micro_direction = _normalize_direction(micro.get("direction"))
    micro_confidence = _float(micro.get("confidence"))

    required_operational_checks = (
        "news_safe",
        "execution_economics_acceptable",
        "microstructure_data_ready",
        "no_strong_microstructure_opposition",
        "no_strong_intermarket_opposition",
    )
    operational_checks = {
        name: bool(meta_checks.get(name, True)) for name in required_operational_checks
    }
    hard_blocks = list(meta.get("hard_signal_blocks", []) or [])
    direct_passed = bool(direct.get("passed", False))
    base_score_ok = winner + 1e-9 >= float(
        getattr(scalping_settings, "SCALPING_DEMO_ENTRY_MIN_WINNER_SCORE", 0.0)
    )
    base_margin_ok = margin + 1e-9 >= float(
        getattr(scalping_settings, "SCALPING_DEMO_ENTRY_MIN_SCORE_MARGIN", 0.0)
    )
    candidate_trackable = bool(
        direction in {"BUY", "SELL"}
        and direct_passed
        and base_score_ok
        and base_margin_ok
        and not hard_blocks
        and all(operational_checks.values())
    )
    return {
        "direction": direction,
        "winner_score": winner,
        "score_margin": margin,
        "micro_direction": micro_direction,
        "micro_confidence": micro_confidence,
        "direct_score_passed": direct_passed,
        "base_score_ok": base_score_ok,
        "base_margin_ok": base_margin_ok,
        "hard_signal_blocks": hard_blocks,
        "operational_checks": operational_checks,
        "operational_safe": all(operational_checks.values()),
        "candidate_trackable": candidate_trackable,
        "native_signal_allowed": bool(getattr(signal, "allowed", False)),
    }


def apply_demo_signal_persistence(
    signal: ScalpSignalState,
    *,
    now_monotonic: float | None = None,
    observation_id: Any | None = None,
) -> tuple[ScalpSignalState, dict[str, Any]]:
    """Require a hard-safe candidate to persist across several demo scans.

    Persistence tracks the direct-score candidate even when the meta-controller
    is waiting on a soft location/playbook rule. It never bypasses hard news,
    execution, stale-data or strong-opposition protections. Final entry remains
    the responsibility of the evidence policy and demo risk guard.
    """

    now = float(time.monotonic() if now_monotonic is None else now_monotonic)
    enabled = bool(
        getattr(scalping_settings, "SCALPING_DEMO_SIGNAL_PERSISTENCE_ENABLED", False)
    )
    context = _candidate_context(signal)
    direction = str(context["direction"])
    candidate_trackable = bool(context["candidate_trackable"])
    winner = float(context["winner_score"])
    margin = float(context["score_margin"])
    micro_direction = str(context["micro_direction"])
    micro_confidence = float(context["micro_confidence"])

    minimum_cycles = int(
        getattr(scalping_settings, "SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_CYCLES", 1)
    )
    minimum_seconds = float(
        getattr(scalping_settings, "SCALPING_DEMO_SIGNAL_PERSISTENCE_MIN_SECONDS", 0.0)
    )
    maximum_gap = float(
        getattr(scalping_settings, "SCALPING_DEMO_SIGNAL_PERSISTENCE_MAX_GAP_SECONDS", 2.0)
    )
    instant = bool(
        candidate_trackable
        and winner + 1e-9
        >= float(getattr(scalping_settings, "SCALPING_DEMO_INSTANT_ENTRY_MIN_SCORE", 101.0))
        and margin + 1e-9
        >= float(getattr(scalping_settings, "SCALPING_DEMO_INSTANT_ENTRY_MIN_MARGIN", 101.0))
        and micro_direction == direction
        and micro_confidence + 1e-9
        >= float(
            getattr(
                scalping_settings,
                "SCALPING_DEMO_INSTANT_ENTRY_MIN_MICRO_CONFIDENCE",
                1.0,
            )
        )
    )

    count_advanced = False
    with _LOCK:
        if not enabled:
            count = minimum_cycles
            elapsed = minimum_seconds
            count_advanced = True
        elif not candidate_trackable:
            _STATE.update(
                {
                    "direction": "NEUTRAL",
                    "count": 0,
                    "first_seen": 0.0,
                    "last_seen": now,
                    "last_observation_id": observation_id,
                }
            )
            count = 0
            elapsed = 0.0
        else:
            same_direction = _STATE.get("direction") == direction
            gap = now - _float(_STATE.get("last_seen"), now)
            same_observation = observation_id is not None and _STATE.get("last_observation_id") == observation_id
            if not same_direction or gap > maximum_gap:
                _STATE.update(
                    {
                        "direction": direction,
                        "count": 1,
                        "first_seen": now,
                        "last_seen": now,
                        "last_observation_id": observation_id,
                    }
                )
                count_advanced = True
            elif not same_observation:
                _STATE["count"] = int(_STATE.get("count", 0)) + 1
                count_advanced = True
                _STATE["last_seen"] = now
                _STATE["last_observation_id"] = observation_id
            count = int(_STATE.get("count", 0))
            elapsed = max(0.0, now - _float(_STATE.get("first_seen"), now))

    passed = bool(
        candidate_trackable
        and (
            not enabled
            or instant
            or (count >= minimum_cycles and elapsed + 1e-9 >= minimum_seconds)
        )
    )
    report = {
        "enabled": enabled,
        "passed": passed,
        "candidate_trackable": candidate_trackable,
        "native_signal_allowed": bool(context["native_signal_allowed"]),
        "instant_override": instant,
        "direction": direction,
        "consecutive_cycles": count,
        "elapsed_seconds": round(elapsed, 4),
        "minimum_cycles": minimum_cycles,
        "minimum_seconds": minimum_seconds,
        "winner_score": round(winner, 4),
        "score_margin": round(margin, 4),
        "micro_direction": micro_direction,
        "micro_confidence": round(micro_confidence, 4),
        "direct_score_passed": bool(context["direct_score_passed"]),
        "base_score_ok": bool(context["base_score_ok"]),
        "base_margin_ok": bool(context["base_margin_ok"]),
        "operational_safe": bool(context["operational_safe"]),
        "operational_checks": dict(context["operational_checks"]),
        "hard_signal_blocks": list(context["hard_signal_blocks"]),
        "observation_id": observation_id,
        "count_advanced": count_advanced,
    }

    updated = copy.deepcopy(signal)
    if not isinstance(updated.metrics, dict):
        updated.metrics = {}
    updated.metrics["signal_persistence"] = report
    if candidate_trackable:
        updated.direction = direction
    if candidate_trackable and not passed:
        updated.allowed = False
        updated.action = "WAIT"
        reason = (
            "Demo signal persistence is still confirming: "
            f"{count}/{minimum_cycles} cycles and {elapsed:.2f}/{minimum_seconds:.2f}s."
        )
        if reason not in updated.block_reasons:
            updated.block_reasons.append(reason)
    return updated, report
