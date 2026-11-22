from __future__ import annotations

from config import scalping_settings


def spread_tolerance_usd() -> float:
    """Return the configured absolute tolerance for spread comparisons."""
    return max(
        0.0,
        float(
            getattr(
                scalping_settings,
                "SCALPING_SPREAD_COMPARISON_TOLERANCE_USD",
                1e-6,
            )
        ),
    )


def spread_exceeds(spread: float, limit: float) -> bool:
    """True only when spread is materially above the configured limit.

    Broker prices are floating-point values, so an apparent 0.320 spread can be
    stored internally as 0.3200000000001.  This helper prevents an exact
    boundary from being rejected because of representation noise.
    """
    return float(spread) - float(limit) > spread_tolerance_usd()


def hard_entry_spread_limit_usd() -> float:
    """Absolute ceiling used before score-aware adaptive spread evaluation."""
    normal = float(scalping_settings.SCALPING_MAX_ENTRY_SPREAD_USD)
    if not bool(getattr(scalping_settings, "SCALPING_ADAPTIVE_SPREAD_ENABLED", False)):
        return normal
    return max(
        normal,
        float(
            getattr(
                scalping_settings,
                "SCALPING_ADAPTIVE_HARD_MAX_ENTRY_SPREAD_USD",
                normal,
            )
        ),
    )
