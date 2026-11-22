from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import joblib
import pandas as pd

from ..config import LABELS, MODELS, REPORTS, MIN_ROWS_TO_TRAIN, ensure_dirs
from .walk_forward import walk_forward_evaluate


def train(frame: pd.DataFrame, *, horizon: str | None = None, direction: str | None = None, promote: bool = False) -> dict[str, Any]:
    ensure_dirs()
    data = frame.copy()
    if horizon: data = data[data.horizon.astype(str) == horizon]
    if direction: data = data[data.direction.astype(str).str.upper() == direction.upper()]
    if len(data) < MIN_ROWS_TO_TRAIN:
        return {"status": "COLLECTING", "rows": len(data), "minimum_rows": MIN_ROWS_TO_TRAIN, "approved": False}
    data["target"] = pd.to_numeric(data["outcome"], errors="coerce")
    data["pnl"] = pd.to_numeric(data["pnl_if_exit"], errors="coerce")
    result = walk_forward_evaluate(data, "target", "pnl")
    fitted = result.pop("fitted_model", None)
    validation_passed = bool(result.get("approved"))
    execution_approved = bool(promote and validation_passed)
    artifact = None
    if fitted is not None:
        artifact = {
            "format_version": 2,
            "approved": execution_approved,
            "validation_passed": validation_passed,
            "promotion_requested": bool(promote),
            "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "horizon": horizon or "ALL",
            "direction": direction or "ALL",
            "model": fitted,
            "threshold": result.get("threshold", 0.55),
            "validation": result,
        }
        name = f"vfinal_{horizon or 'ALL'}_{direction or 'ALL'}.joblib".replace("/", "_")
        path = MODELS / name
        joblib.dump(artifact, path)
        artifact["path"] = str(path)
    status = "APPROVED" if execution_approved else "VALIDATED_NOT_PROMOTED" if validation_passed else "RESEARCH_ONLY"
    # Apply deployment state after validation details so the evaluator's
    # internal `approved` flag cannot overwrite explicit promotion policy.
    report = {**result, "status": status, "approved": execution_approved,
              "validation_passed": validation_passed, "artifact": artifact}
    report_path = REPORTS / f"training_{horizon or 'ALL'}_{direction or 'ALL'}.json"
    report_path.write_text(json.dumps({k:v for k,v in report.items() if k not in {"artifact"}}, indent=2, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
