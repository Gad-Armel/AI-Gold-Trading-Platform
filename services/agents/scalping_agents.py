from __future__ import annotations

from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.microstructure.feature_engine import MicrostructureFeatureState
from services.risk.adaptive_spread_policy import evaluate_adaptive_spread_policy


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized_confidence(value: Any) -> float:
    number = _safe_float(value)
    if number > 1.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def _candidate_diagnostics(signal: ScalpSignalState) -> dict[str, Any]:
    metrics = signal.metrics if isinstance(signal.metrics, dict) else {}
    diagnostics = metrics.get("score_diagnostics", {})
    return diagnostics if isinstance(diagnostics, dict) else {}


def build_technical_agent(signal: ScalpSignalState) -> dict[str, Any]:
    diagnostics = _candidate_diagnostics(signal)
    direct = diagnostics.get("direct_score_decision", {})
    candidate = signal.direction if signal.direction in {"BUY", "SELL"} else str(
        direct.get("winner_direction", "NEUTRAL")
    )
    if candidate not in {"BUY", "SELL"}:
        candidate = "NEUTRAL"
    quality = diagnostics.get("entry_quality_decision", {})
    if not isinstance(quality, dict):
        quality = {}
    return {
        "name": "technical_regime",
        "direction": candidate,
        "confidence": _normalized_confidence(signal.confidence),
        "data_quality": 1.0 if isinstance(signal.metrics, dict) and signal.metrics else 0.5,
        "safe": bool(signal.allowed),
        "native_playbook_allowed": bool(signal.allowed),
        "score": _safe_float(signal.score),
        "margin": _safe_float(direct.get("margin", diagnostics.get("direction_margin", 0.0))),
        "support_votes": int(_safe_float(quality.get("support_votes", 0))),
        "opposition_votes": int(_safe_float(quality.get("opposition_votes", 0))),
        "reason": (
            f"Technical candidate={candidate}, pattern={signal.pattern}, "
            f"score={signal.score:.2f}, native_allowed={signal.allowed}."
        ),
    }

def build_microstructure_agent(features: MicrostructureFeatureState) -> dict[str, Any]:
    return {
        "name": "tick_microstructure",
        "direction": features.direction,
        "confidence": features.confidence,
        "data_quality": features.data_quality,
        "safe": features.data_quality >= float(
            scalping_settings.SCALPING_MICROSTRUCTURE_MIN_DATA_QUALITY
        ),
        "status": features.status,
        "reason": features.reason,
    }


def build_intermarket_agent(
    signal: ScalpSignalState,
    direct_context: dict[str, Any] | None,
) -> dict[str, Any]:
    direct_context = direct_context or {}
    direct_bias = str(direct_context.get("gold_bias", "NEUTRAL"))
    direct_pressure = _safe_float(direct_context.get("pressure_score"))

    existing = signal.metrics.get("cross_market_context", {}) if isinstance(signal.metrics, dict) else {}
    existing_bias = str(existing.get("gold_bias", "NEUTRAL")) if isinstance(existing, dict) else "NEUTRAL"
    existing_pressure = _safe_float(existing.get("pressure_score")) if isinstance(existing, dict) else 0.0

    components: list[float] = []
    if direct_bias in {"BUY", "SELL"}:
        components.append(direct_pressure)
    if existing_bias in {"BUY", "SELL"}:
        components.append(abs(existing_pressure) if existing_bias == "BUY" else -abs(existing_pressure))
    pressure = sum(components) / len(components) if components else 0.0
    direction = "BUY" if pressure >= 0.25 else "SELL" if pressure <= -0.25 else "NEUTRAL"
    quality = 1.0 if direct_context.get("status") == "ACTIVE" else 0.5 if existing else 0.0
    return {
        "name": "intermarket_context",
        "direction": direction,
        "confidence": min(1.0, abs(pressure)),
        "data_quality": quality,
        "safe": True,
        "pressure_score": round(pressure, 6),
        "direct_status": direct_context.get("status", "UNAVAILABLE"),
        "reason": (
            f"Direct bias={direct_bias} ({direct_pressure:+.2f}); "
            f"existing basket bias={existing_bias} ({existing_pressure:+.2f})."
        ),
    }


def build_news_agent(news_risk: dict[str, Any]) -> dict[str, Any]:
    allowed = bool(news_risk.get("allowed", False))
    return {
        "name": "economic_event_risk",
        "direction": "SAFE" if allowed else "BLOCK",
        "confidence": 1.0,
        "data_quality": 1.0,
        "safe": allowed,
        "reason": (
            "Economic-event filter is safe."
            if allowed
            else f"Economic-event block: {news_risk.get('block_reasons', [])}"
        ),
    }


def build_execution_economics_agent(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
) -> dict[str, Any]:
    policy = evaluate_adaptive_spread_policy(snapshot, signal)
    accepted = bool(policy["accepted"])
    target = float(policy["target_usd"])
    spread_cost = float(policy["spread_cost_usd"])
    movement_edge = max(0.0, target - spread_cost)
    confidence = min(1.0, movement_edge / max(target, 1e-9)) if target > 0 else 0.0
    return {
        "name": "execution_economics",
        "direction": "ACCEPTABLE" if accepted else "REJECT",
        "confidence": confidence,
        "data_quality": 1.0,
        "safe": accepted,
        "spread_policy_mode": policy["mode"],
        "adaptive_spread_accepted": bool(policy["adaptive_ok"]),
        "absolute_spread_ok": bool(
            policy["normal_spread_ok"] or policy["adaptive_ok"]
        ),
        "spread_limit_usd": float(policy["effective_limit_usd"]),
        "normal_spread_limit_usd": float(policy["normal_limit_usd"]),
        "hard_spread_limit_usd": float(policy["hard_limit_usd"]),
        "spread_cost_usd": float(policy["spread_cost_usd"]),
        "target_usd": float(policy["target_usd"]),
        "stop_usd": float(policy["stop_usd"]),
        "spread_target_ratio": float(policy["spread_target_ratio"]),
        "spread_atr_ratio": float(policy["spread_atr_ratio"]),
        "reward_risk_ratio": float(policy["reward_risk_ratio"]),
        "winner_score": float(policy["winner_score"]),
        "score_margin": float(policy["score_margin"]),
        "failed_adaptive_checks": list(policy["failed_adaptive_checks"]),
        "reason": str(policy["reason"]),
    }


def build_scalping_agents(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    features: MicrostructureFeatureState,
    news_risk: dict[str, Any],
    direct_intermarket: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    return {
        "technical": build_technical_agent(signal),
        "microstructure": build_microstructure_agent(features),
        "intermarket": build_intermarket_agent(signal, direct_intermarket),
        "news": build_news_agent(news_risk),
        "execution": build_execution_economics_agent(snapshot, signal),
    }
