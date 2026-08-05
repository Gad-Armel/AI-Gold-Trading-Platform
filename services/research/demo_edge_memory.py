from __future__ import annotations

from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.execution.scalp_demo_journal import load_cumulative_demo_history


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _direction(value: Any) -> str:
    text = str(value or "NEUTRAL").upper()
    if text in {"BUY", "BULL", "BULLISH", "LONG"}:
        return "BUY"
    if text in {"SELL", "BEAR", "BEARISH", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def build_demo_entry_profile(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    spread_policy: dict[str, Any],
    *,
    loss_recovery_mode: bool = False,
    quality_index: float = 0.0,
) -> dict[str, Any]:
    metrics = _dict(getattr(signal, "metrics", {}))
    diagnostics = _dict(metrics.get("score_diagnostics"))
    direct = _dict(diagnostics.get("direct_score_decision"))
    micro = _dict(metrics.get("microstructure"))
    meta = _dict(metrics.get("meta_controller"))
    verified = _dict(metrics.get("verified_context"))
    regime = _dict(metrics.get("regime"))
    direction = _direction(getattr(signal, "direction", "NEUTRAL"))
    micro_direction = _direction(micro.get("direction"))
    micro_state = (
        "ALIGNED"
        if micro_direction == direction
        else "OPPOSED"
        if micro_direction in {"BUY", "SELL"}
        else "NEUTRAL"
    )
    winner = _float(direct.get("winner_score", getattr(signal, "score", 0.0)))
    score_band = "STRONG" if winner >= 55.0 else "MEDIUM" if winner >= 45.0 else "BASE"
    spread_mode = str(spread_policy.get("mode", "REJECT"))
    return {
        "direction": direction,
        "entry_mode": str(meta.get("entry_mode", getattr(signal, "pattern", "UNKNOWN"))),
        "score_band": score_band,
        "spread_band": "ELEVATED" if spread_mode == "ADAPTIVE_ELEVATED_SPREAD" else "NORMAL",
        "micro_state": micro_state,
        "session": str(getattr(snapshot, "session", "UNKNOWN")),
        "regime": str(regime.get("mode", "UNKNOWN")),
        "loss_recovery_mode": bool(loss_recovery_mode),
        "winner_score": round(winner, 4),
        "score_margin": round(
            _float(direct.get("margin", diagnostics.get("direction_margin", 0.0))),
            4,
        ),
        "micro_direction": micro_direction,
        "micro_confidence": round(_float(micro.get("confidence")), 4),
        "spread_usd": round(_float(getattr(snapshot, "spread", 0.0)), 6),
        "spread_target_ratio": round(_float(spread_policy.get("spread_target_ratio")), 6),
        "reward_risk_ratio": round(_float(spread_policy.get("reward_risk_ratio")), 6),
        "quality_index": round(float(quality_index), 6),
        "relative_volume": round(_float(verified.get("relative_tick_volume")), 4),
        "vwap_distance_atr": round(_float(verified.get("vwap_distance_atr")), 4),
    }


def _bucket(profile: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(profile.get("direction", "NEUTRAL")),
        str(profile.get("score_band", "BASE")),
        str(profile.get("spread_band", "NORMAL")),
        str(profile.get("micro_state", "NEUTRAL")),
        str(profile.get("regime", "UNKNOWN")),
        str(profile.get("loss_recovery_mode", False)),
    )


def evaluate_demo_edge_memory(
    profile: dict[str, Any],
    *,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    enabled = bool(getattr(scalping_settings, "SCALPING_DEMO_EDGE_MEMORY_ENABLED", False))
    minimum = int(
        getattr(scalping_settings, "SCALPING_DEMO_EDGE_MEMORY_MIN_BUCKET_TRADES", 20)
    )
    if not enabled:
        return {
            "enabled": False,
            "allowed": True,
            "sample_size": 0,
            "reason": "Empirical edge memory is disabled.",
            "profile_bucket": _bucket(profile),
        }

    rows = history if history is not None else load_cumulative_demo_history()
    target_bucket = _bucket(profile)
    outcomes: list[float] = []
    for row in rows:
        if str(row.get("status", "")).upper() != "CLOSED":
            continue
        row_profile = _dict(row.get("entry_profile"))
        if not row_profile or _bucket(row_profile) != target_bucket:
            continue
        value = row.get("final_profit_usd")
        if value is None:
            continue
        outcomes.append(_float(value))

    wins = [value for value in outcomes if value > 0.0]
    losses = [-value for value in outcomes if value < 0.0]
    breakeven = len(outcomes) - len(wins) - len(losses)
    prior_wins = float(
        getattr(scalping_settings, "SCALPING_DEMO_EDGE_MEMORY_PRIOR_WINS", 2.0)
    )
    prior_losses = float(
        getattr(scalping_settings, "SCALPING_DEMO_EDGE_MEMORY_PRIOR_LOSSES", 2.0)
    )
    posterior_win_rate = (len(wins) + prior_wins) / max(
        len(outcomes) + prior_wins + prior_losses, 1e-9
    )
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    expectancy = posterior_win_rate * avg_win - (1.0 - posterior_win_rate) * avg_loss
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    enough = len(outcomes) >= minimum
    negative_threshold = float(
        getattr(
            scalping_settings,
            "SCALPING_DEMO_EDGE_MEMORY_MAX_NEGATIVE_EXPECTANCY_USD",
            -0.03,
        )
    )
    bad_pf_threshold = float(
        getattr(
            scalping_settings,
            "SCALPING_DEMO_EDGE_MEMORY_MAX_BAD_PROFIT_FACTOR",
            0.85,
        )
    )
    veto = bool(
        enough
        and expectancy <= negative_threshold + 1e-9
        and profit_factor <= bad_pf_threshold + 1e-9
    )
    reason = (
        f"Comparable setup bucket has {len(outcomes)} trades, posterior win rate "
        f"{posterior_win_rate:.2%}, expectancy ${expectancy:.3f}, PF {profit_factor:.2f}."
    )
    if not enough:
        reason += f" Learning only until {minimum} comparable trades."
    elif veto:
        reason += " Negative empirical edge veto is active."
    else:
        reason += " Empirical edge is not negative enough to veto."

    return {
        "enabled": enabled,
        "allowed": not veto,
        "sample_size": len(outcomes),
        "minimum_sample_size": minimum,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "posterior_win_rate": round(posterior_win_rate, 6),
        "average_win_usd": round(avg_win, 6),
        "average_loss_usd": round(avg_loss, 6),
        "expectancy_usd": round(expectancy, 6),
        "profit_factor": round(profit_factor, 6),
        "profile_bucket": target_bucket,
        "reason": reason,
    }
