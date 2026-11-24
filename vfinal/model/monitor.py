from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd


def psi(reference: np.ndarray, recent: np.ndarray, bins: int = 10) -> float:
    ref = np.asarray(reference, dtype=float); cur = np.asarray(recent, dtype=float)
    ref = ref[np.isfinite(ref)]; cur = cur[np.isfinite(cur)]
    if len(ref) < 30 or len(cur) < 10: return 0.0
    edges = np.unique(np.quantile(ref, np.linspace(0,1,bins+1)))
    if len(edges) < 3: return 0.0
    r = np.histogram(ref, bins=edges)[0].astype(float); c = np.histogram(cur, bins=edges)[0].astype(float)
    r /= max(r.sum(), 1.0); c /= max(c.sum(), 1.0)
    eps = 1e-6; r=np.clip(r,eps,1); c=np.clip(c,eps,1)
    return float(np.sum((c-r)*np.log(c/r)))


def monitor_dataset(frame: pd.DataFrame, probability_col: str = "probability_win") -> dict[str, Any]:
    if frame.empty or probability_col not in frame:
        return {"available": False}
    frame = frame.sort_values("snapshot_timestamp")
    split = max(1, int(len(frame)*0.70))
    ref = pd.to_numeric(frame.iloc[:split][probability_col], errors="coerce").to_numpy()
    recent = pd.to_numeric(frame.iloc[split:][probability_col], errors="coerce").to_numpy()
    value = psi(ref, recent)
    return {"available": True, "psi": value, "status": "BLOCK" if value >= 0.30 else "WARNING" if value >= 0.20 else "OK", "reference_rows": len(ref), "recent_rows": len(recent)}
