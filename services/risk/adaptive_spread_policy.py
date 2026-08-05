from __future__ import annotations

from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.market_data.spread_utils import spread_exceeds


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _candidate_metrics(signal: ScalpSignalState) -> tuple[float, float, bool]:
    metrics = _dict(getattr(signal, "metrics", {}))
    diagnostics = _dict(metrics.get("score_diagnostics"))
    direct = _dict(diagnostics.get("direct_score_decision"))
    winner_score = _float(direct.get("winner_score", getattr(signal, "score", 0.0)))
    margin = _float(direct.get("margin", diagnostics.get("direction_margin", 0.0)))
    candidate_valid = bool(direct.get("passed", False)) and str(
        direct.get("winner_direction", getattr(signal, "direction", "NEUTRAL"))
    ).upper() in {"BUY", "SELL"}
    return winner_score, margin, candidate_valid


def _m1_atr(signal: ScalpSignalState) -> float:
    metrics = _dict(getattr(signal, "metrics", {}))
    m1 = _dict(metrics.get("M1"))
    for key in ("atr", "atr_usd", "m1_atr"):
        value = _float(m1.get(key))
        if value > 0:
            return value
    diagnostics = _dict(metrics.get("score_diagnostics"))
    quality = _dict(diagnostics.get("entry_quality_decision"))
    value = _float(quality.get("m1_atr"))
    return value if value > 0 else 0.0


def evaluate_adaptive_spread_policy(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    *,
    require_normal_economics: bool = True,
) -> dict[str, Any]:
    """Evaluate the normal and elevated-spread execution bands.

    The normal spread ceiling remains strict. A narrow elevated band is allowed
    only for strong, fresh score-margin candidates whose reward/risk and spread
    economics remain acceptable. The hard ceiling can never be bypassed.
    """
    spread = max(0.0, _float(getattr(snapshot, "spread", 0.0)))
    normal_limit = float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD)
    hard_limit = float(
        getattr(
            scalping_settings,
            "SCALPING_ADAPTIVE_HARD_MAX_ENTRY_SPREAD_USD",
            normal_limit,
        )
    )
    enabled = bool(
        getattr(scalping_settings, "SCALPING_ADAPTIVE_SPREAD_ENABLED", False)
    )

    target = max(0.0, _float(getattr(signal, "target_profit_usd", 0.0)))
    stop = max(0.0, _float(getattr(signal, "stop_loss_usd", 0.0)))
    lot = max(0.0, float(scalping_settings.SCALPING_LOT_SIZE))
    contract_size = max(0.0, _float(getattr(snapshot, "contract_size", 100.0), 100.0))
    spread_cost = spread * lot * contract_size
    spread_target_ratio = spread_cost / target if target > 0 else float("inf")
    reward_risk = target / stop if stop > 0 else 0.0
    atr = _m1_atr(signal)
    spread_atr_ratio = spread / atr if atr > 0 else float("inf")
    winner_score, margin, candidate_valid = _candidate_metrics(signal)
    quote_age = max(0.0, _float(getattr(snapshot, "quote_age_seconds", 0.0)))

    normal_spread_ok = not spread_exceeds(spread, normal_limit)
    hard_spread_ok = not spread_exceeds(spread, hard_limit)
    economics_available = target > 0 and stop > 0
    normal_economics_ok = bool(
        not economics_available
        or (
            target > spread_cost
            and spread_target_ratio
            <= float(scalping_settings.SCALPING_MAX_SPREAD_TARGET_RATIO)
            and reward_risk >= float(scalping_settings.SCALPING_MIN_REWARD_RISK_RATIO)
        )
    )

    adaptive_checks = {
        "adaptive_enabled": enabled,
        "candidate_valid": candidate_valid,
        "winner_score": winner_score + 1e-9
        >= float(scalping_settings.SCALPING_ADAPTIVE_SPREAD_MIN_WINNER_SCORE),
        "score_margin": margin + 1e-9
        >= float(scalping_settings.SCALPING_ADAPTIVE_SPREAD_MIN_SCORE_MARGIN),
        "hard_spread_ceiling": hard_spread_ok,
        "spread_target": spread_target_ratio
        <= float(scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_TARGET_RATIO),
        "spread_atr": spread_atr_ratio
        <= float(scalping_settings.SCALPING_ADAPTIVE_MAX_SPREAD_ATR_RATIO),
        "reward_risk": reward_risk
        >= float(scalping_settings.SCALPING_ADAPTIVE_MIN_REWARD_RISK_RATIO),
        "fresh_quote": quote_age
        <= float(scalping_settings.SCALPING_MAX_QUOTE_STALE_SECONDS),
        "positive_edge": target > spread_cost,
    }
    adaptive_ok = bool(
        not normal_spread_ok and all(adaptive_checks.values())
    )

    if normal_spread_ok and (normal_economics_ok or not require_normal_economics):
        accepted = True
        mode = "NORMAL_SPREAD"
        effective_limit = normal_limit
    elif adaptive_ok:
        accepted = True
        mode = "ADAPTIVE_ELEVATED_SPREAD"
        effective_limit = hard_limit
    else:
        accepted = False
        mode = "REJECT"
        effective_limit = normal_limit if normal_spread_ok else hard_limit

    failed_adaptive = [name for name, passed in adaptive_checks.items() if not passed]
    return {
        "accepted": accepted,
        "mode": mode,
        "normal_spread_ok": normal_spread_ok,
        "normal_economics_ok": normal_economics_ok,
        "normal_economics_required": bool(require_normal_economics),
        "adaptive_ok": adaptive_ok,
        "adaptive_checks": adaptive_checks,
        "failed_adaptive_checks": failed_adaptive,
        "normal_limit_usd": normal_limit,
        "hard_limit_usd": hard_limit,
        "effective_limit_usd": effective_limit,
        "spread_usd": round(spread, 6),
        "spread_cost_usd": round(spread_cost, 6),
        "target_usd": round(target, 6),
        "stop_usd": round(stop, 6),
        "spread_target_ratio": round(spread_target_ratio, 6)
        if spread_target_ratio != float("inf")
        else 999.0,
        "spread_atr_ratio": round(spread_atr_ratio, 6)
        if spread_atr_ratio != float("inf")
        else 999.0,
        "reward_risk_ratio": round(reward_risk, 6),
        "winner_score": round(winner_score, 4),
        "score_margin": round(margin, 4),
        "quote_age_seconds": round(quote_age, 4),
        "reason": (
            f"mode={mode}, spread=${spread:.2f}, normal<=${normal_limit:.2f}, "
            f"hard<=${hard_limit:.2f}, winner={winner_score:.1f}, margin={margin:.1f}, "
            f"spread/target={spread_target_ratio:.2f}, spread/ATR={spread_atr_ratio:.2f}, "
            f"R/R={reward_risk:.2f}."
        ),
    }
