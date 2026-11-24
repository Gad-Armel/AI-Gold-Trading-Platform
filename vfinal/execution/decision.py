from __future__ import annotations

from pathlib import Path
from typing import Any
import math
import joblib
import pandas as pd

from ..config import MIN_EV_USD, MIN_PROBABILITY, MODELS
from ..model.metrics import expected_value
from ..model.walk_forward import ALL_FEATURES


def load_artifact(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    if not target.exists(): return None
    try: return joblib.load(target)
    except Exception: return None


def decide(feature_row: dict[str, Any], *, reward_usd: float, risk_usd: float, cost_usd: float, artifact_path: str | None = None, hard_blocks: list[str] | None = None) -> dict[str, Any]:
    blocks = list(hard_blocks or [])
    direction = str(feature_row.get("direction", "WAIT")).upper()
    if direction not in {"BUY", "SELL"}:
        return {"action": "WAIT", "reason": "No directional candidate."}
    artifact = load_artifact(artifact_path) if artifact_path else None
    if not isinstance(artifact, dict) or not artifact.get("approved", False):
        return {"action": "WAIT", "reason": "No approved V-FINAL model; continue shadow collection."}
    if artifact.get("format_version") != 2:
        return {"action": "WAIT", "reason": "Unsupported V-FINAL artifact format."}
    if artifact.get("direction", "ALL") not in ("ALL", direction):
        return {"action": "WAIT", "reason": "V-FINAL model direction does not match the candidate."}
    if not all(math.isfinite(value) for value in (reward_usd, risk_usd, cost_usd)) or min(reward_usd, risk_usd) <= 0 or cost_usd < 0:
        return {"action": "WAIT", "reason": "Invalid V-FINAL reward, risk or cost."}
    model = artifact.get("model")
    required = list(getattr(model, "features", ALL_FEATURES))
    missing = sorted(set(required) - set(feature_row))
    if model is None or missing:
        return {"action": "WAIT", "reason": f"V-FINAL feature schema mismatch; missing {len(missing)} feature(s)."}
    frame = pd.DataFrame([feature_row])
    try:
        probability = float(model.predict_proba(frame[required])[:,1][0])
        threshold = float(artifact.get("threshold", MIN_PROBABILITY))
    except Exception:
        return {"action": "WAIT", "reason": "V-FINAL probability unavailable."}
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in (probability, threshold)):
        return {"action": "WAIT", "reason": "Invalid V-FINAL probability or threshold."}
    ev = expected_value(probability, reward_usd, risk_usd, cost_usd)
    if probability < max(MIN_PROBABILITY, threshold): blocks.append(f"probability {probability:.3f} below threshold {max(MIN_PROBABILITY, threshold):.3f}")
    if ev < MIN_EV_USD: blocks.append(f"expected value ${ev:.3f} below ${MIN_EV_USD:.3f}")
    return {
        "action": direction if not blocks else "WAIT", "direction": direction,
        "probability_win": round(probability, 6), "threshold": threshold,
        "reward_usd": reward_usd, "risk_usd": risk_usd, "cost_usd": cost_usd,
        "expected_value_usd": round(ev, 6), "blocks": blocks,
        "model_name": artifact.get("validation", {}).get("selected_model"),
    }
