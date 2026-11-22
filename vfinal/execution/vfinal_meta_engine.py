from __future__ import annotations

"""Drop-in V-FINAL gate for the existing XAUUSD bot.

This module never creates a trade by itself. It only converts an existing safe
candidate into TRADE/WAIT after the approved calibrated V-FINAL artifact passes.
Keep the existing MT5/news/account/risk guards in front of it.
"""

from pathlib import Path
from typing import Any
import math

import joblib
import pandas as pd

try:
    from vfinal.model.walk_forward import ALL_FEATURES
except Exception:
    ALL_FEATURES = []


DEFAULT_MODEL = "data/models/vfinal/vfinal_SCALP_60S_ALL.joblib"


def score_candidate(profile: dict[str, Any], model_path: str = DEFAULT_MODEL) -> dict[str, Any]:
    path = Path(model_path)
    if not path.exists():
        return {"available": False, "approved": False, "allowed": False, "reason": "V-FINAL model artifact not found."}
    try:
        artifact = joblib.load(path)
        if not artifact.get("approved", False):
            return {"available": True, "approved": False, "allowed": False, "reason": "V-FINAL artifact is research-only."}
        if artifact.get("format_version") != 2:
            return {"available": True, "approved": False, "allowed": False, "reason": "Unsupported V-FINAL artifact format."}
        if artifact.get("direction", "ALL") not in ("ALL", profile.get("direction")):
            return {"available": True, "approved": False, "allowed": False, "reason": "V-FINAL model direction mismatch."}
        model = artifact.get("model")
        required = list(getattr(model, "features", ALL_FEATURES))
        missing = sorted(set(required) - set(profile))
        if model is None or missing:
            return {"available": True, "approved": True, "allowed": False,
                    "reason": f"V-FINAL feature schema mismatch; missing {len(missing)} feature(s)."}
        frame = pd.DataFrame([profile])
        probability = float(model.predict_proba(frame[required])[:, 1][0])
        threshold = float(artifact.get("threshold", 0.55))
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in (probability, threshold)):
            return {"available": True, "approved": False, "allowed": False, "reason": "Invalid V-FINAL probability or threshold."}
        return {
            "available": True,
            "approved": True,
            "allowed": probability >= threshold,
            "probability_win": round(probability, 6),
            "threshold": threshold,
            "model_name": artifact.get("validation", {}).get("selected_model"),
        }
    except Exception as exc:
        return {"available": False, "approved": False, "allowed": False, "reason": f"V-FINAL scoring error: {type(exc).__name__}."}


def apply_gate(decision: dict[str, Any], profile: dict[str, Any], *, reward_usd: float, risk_usd: float, cost_usd: float, model_path: str = DEFAULT_MODEL) -> dict[str, Any]:
    result = dict(decision)
    if not bool(result.get("allowed", False)):
        return result
    if not all(math.isfinite(value) for value in (reward_usd, risk_usd, cost_usd)) or min(reward_usd, risk_usd) <= 0 or cost_usd < 0:
        result["allowed"] = False
        result.setdefault("blocks", []).append("Invalid V-FINAL reward, risk or cost.")
        return result
    score = score_candidate(profile, model_path=model_path)
    result["vfinal"] = score
    if not score.get("allowed", False):
        result["allowed"] = False
        result.setdefault("blocks", []).append(score.get("reason", "V-FINAL probability gate failed."))
        return result
    probability = float(score["probability_win"])
    ev = probability * reward_usd - (1 - probability) * risk_usd - cost_usd
    result["vfinal"]["expected_value_usd"] = round(ev, 6)
    if ev <= 0:
        result["allowed"] = False
        result.setdefault("blocks", []).append(f"V-FINAL expected value <= 0 (${ev:.3f}).")
    return result
