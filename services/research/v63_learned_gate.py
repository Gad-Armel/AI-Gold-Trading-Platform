from __future__ import annotations

from copy import deepcopy
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.research.v6_shadow_engine import build_v6_entry_profile
from services.research.v63_self_learning import score_v63_profile


def evaluate_v63_learned_gate(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    base_gate: dict[str, Any],
) -> dict[str, Any]:
    """Filter an EXPLORATORY candidate with an approved calibrated model.

    LEARNED is always simulation-only. It cannot repair a failed base gate and
    never becomes demo eligible.
    """

    gate = deepcopy(base_gate)
    gate["lane"] = str(scalping_settings.SCALPING_V63_LEARNED_LANE_NAME)
    gate["demo_eligible"] = False
    profile = build_v6_entry_profile(snapshot, signal, gate, gate["lane"])
    model = score_v63_profile(profile, source_lane=str(scalping_settings.SCALPING_V63_LEARNED_BASE_LANE))
    checks = dict(gate.get("checks", {}))
    checks["learned_base_lane"] = bool(base_gate.get("allowed", False))
    checks["approved_calibrated_model"] = bool(model.get("approved_model", False))
    checks["model_probability"] = bool(model.get("allowed", False))
    failed = [name for name, passed in checks.items() if not passed]
    gate.update(
        {
            "checks": checks,
            "failed_checks": failed,
            "allowed": not failed,
            "model_probability_win": float(model.get("probability_win", 0.0) or 0.0),
            "model_probability_threshold": model.get("threshold"),
            "model_name": model.get("model_name"),
            "model_training_rows": model.get("training_rows"),
            "model_regime_samples": model.get("regime_samples"),
            "model_status": model,
            "reason": (
                "V6.3 LEARNED lane passed calibrated probability selection."
                if not failed
                else "V6.3 LEARNED lane blocked: " + ", ".join(failed) + "."
            ),
        }
    )
    return gate
