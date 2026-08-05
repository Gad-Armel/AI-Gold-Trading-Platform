from __future__ import annotations

from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def build_v63_barrier_plan(
    snapshot: ScalpingSnapshotState,
    gate: dict[str, Any],
) -> dict[str, float | str | bool]:
    """Return a cost-aware triple-barrier plan for one shadow candidate.

    The plan is deterministic and uses only information available at entry.
    It never changes lot size and never bypasses the candidate gate.
    """

    if not bool(getattr(scalping_settings, "SCALPING_V63_DYNAMIC_BARRIERS_ENABLED", True)):
        target = float(scalping_settings.SCALPING_V6_TARGET_USD)
        stop = float(scalping_settings.SCALPING_V6_HARD_STOP_USD)
        return {
            "enabled": False,
            "target_profit_usd": round(target, 4),
            "hard_stop_usd": round(stop, 4),
            "target_stop_ratio": round(target / max(stop, 1e-9), 6),
            "reason": "Static V6 barriers.",
        }

    spread = max(_float(getattr(snapshot, "spread", 0.0)), 0.0)
    spread_atr = max(_float(gate.get("spread_atr")), 0.0)
    atr = spread / spread_atr if spread > 0 and spread_atr > 1e-9 else 0.0

    target = max(
        float(scalping_settings.SCALPING_V63_TARGET_MIN_USD),
        spread * float(scalping_settings.SCALPING_V63_TARGET_SPREAD_MULTIPLE),
        atr * float(scalping_settings.SCALPING_V63_TARGET_ATR_MULTIPLE),
    )
    stop = max(
        float(scalping_settings.SCALPING_V63_STOP_MIN_USD),
        spread * float(scalping_settings.SCALPING_V63_STOP_SPREAD_MULTIPLE),
        atr * float(scalping_settings.SCALPING_V63_STOP_ATR_MULTIPLE),
    )

    target = _clamp(
        target,
        float(scalping_settings.SCALPING_V63_TARGET_MIN_USD),
        float(scalping_settings.SCALPING_V63_TARGET_MAX_USD),
    )
    stop = _clamp(
        stop,
        float(scalping_settings.SCALPING_V63_STOP_MIN_USD),
        float(scalping_settings.SCALPING_V63_STOP_MAX_USD),
    )

    minimum_ratio = float(scalping_settings.SCALPING_V63_MIN_TARGET_STOP_RATIO)
    if target / max(stop, 1e-9) < minimum_ratio:
        required_target = stop * minimum_ratio
        target = min(float(scalping_settings.SCALPING_V63_TARGET_MAX_USD), required_target)
    if target / max(stop, 1e-9) < minimum_ratio:
        stop = min(stop, target / max(minimum_ratio, 1e-9))

    ratio = target / max(stop, 1e-9)
    breakeven_win_rate = stop / max(target + stop, 1e-9)
    return {
        "enabled": True,
        "target_profit_usd": round(target, 4),
        "hard_stop_usd": round(stop, 4),
        "target_stop_ratio": round(ratio, 6),
        "breakeven_win_rate": round(breakeven_win_rate, 6),
        "spread_usd": round(spread, 5),
        "estimated_m1_atr_usd": round(atr, 5),
        "reason": "Cost-aware V6.3 adaptive barriers.",
    }
