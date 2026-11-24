from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import LABELS, MIN_ROWS_TO_TRAIN, PREFERRED_ROWS, ensure_dirs


def flatten_snapshot_rows(snapshots: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in snapshots:
        base = {k: v for k, v in item.items() if k != "feature_payload"}
        payload = item.get("feature_payload") if isinstance(item.get("feature_payload"), dict) else {}
        base.update(payload)
        rows.append(base)
    return pd.DataFrame(rows)


def merge_features_labels(snapshots: list[dict[str, Any]], labels: pd.DataFrame) -> pd.DataFrame:
    features = flatten_snapshot_rows(snapshots)
    if features.empty or labels.empty:
        return pd.DataFrame()
    features["snapshot_timestamp"] = pd.to_datetime(features["timestamp"], utc=True, errors="coerce")
    labels["snapshot_timestamp"] = pd.to_datetime(labels["snapshot_timestamp"], utc=True, errors="coerce")
    # Ambiguous same-timestamp barrier touches are retained in raw labels but
    # excluded from supervised training because their winner is unknowable at
    # tick resolution.
    if "label_quality" in labels.columns:
        labels = labels[labels["label_quality"].astype(str).isin(("VALID", "TIME_BARRIER"))].copy()
    merged = labels.merge(features, on=["snapshot_timestamp", "symbol", "direction"], how="left", suffixes=("", "_feature"))
    merged = merged.sort_values("snapshot_timestamp").reset_index(drop=True)
    return merged


def save_dataset(frame: pd.DataFrame, name: str = "vfinal_dataset.csv") -> Path:
    ensure_dirs()
    path = LABELS / name
    frame.to_csv(path, index=False)
    return path


def load_dataset(path: str | Path | None = None) -> pd.DataFrame:
    target = Path(path) if path else LABELS / "vfinal_dataset.csv"
    
    if not target.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(target)
    except pd.errors.EmptyDataError:
        # A collecting build can legitimately produce an empty CSV before
        # the first closed trade/snapshot exists. Treat it as an empty
        # dataset instead of crashing the status command.
        return pd.DataFrame()


def dataset_status(frame: pd.DataFrame) -> dict[str, Any]:
    rows = int(len(frame))
    status = "READY_FOR_RESEARCH" if rows >= MIN_ROWS_TO_TRAIN else "COLLECTING"
    return {
        "rows": rows,
        "status": status,
        "minimum_rows": MIN_ROWS_TO_TRAIN,
        "preferred_rows": PREFERRED_ROWS,
        "directions": frame.get("direction", pd.Series(dtype=str)).value_counts().to_dict(),
        "horizons": frame.get("horizon", pd.Series(dtype=str)).value_counts().to_dict(),
        "time_start": str(frame["snapshot_timestamp"].min()) if "snapshot_timestamp" in frame and not frame.empty else None,
        "time_end": str(frame["snapshot_timestamp"].max()) if "snapshot_timestamp" in frame and not frame.empty else None,
    }
