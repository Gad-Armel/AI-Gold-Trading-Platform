from __future__ import annotations

from typing import Any

from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.analysis.scalp_signal_engine_v2 import build_scalp_signal as build_v2_signal
from services.analysis.unified_scalping_intelligence import build_unified_scalp_signal


def build_scalp_signal(
    snapshot: ScalpingSnapshotState,
    news_context: dict[str, Any] | None = None,
) -> ScalpSignalState:
    """Build the single V3 unified decision.

    The proven V2 entry model remains one feature family.  It no longer acts as
    a separate AI; candle, structure, zone, order-block, regime, indicator and
    economic features are merged into one final score and one decision.
    """
    base = build_v2_signal(snapshot)
    return build_unified_scalp_signal(snapshot, base, news_context)
