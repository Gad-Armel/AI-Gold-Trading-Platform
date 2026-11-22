from __future__ import annotations

"""Tick data quality and microstructure regime layer.

RAW MT5 ticks are never deleted or rewritten by this module.  The output is an
annotated research view containing quality flags, gaps, spread regimes and
session-transition information.  This keeps broker/feed artefacts available for
audit while preventing them from silently becoming model labels.
"""

from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd


DEFAULT_ROLLING_TICKS = 500
DEFAULT_STARTUP_SECONDS = 90
DEFAULT_WIDE_MULTIPLIER = 3.0
DEFAULT_EXTREME_MULTIPLIER = 8.0
DEFAULT_MIN_VALID_SPREAD = 0.0
DEFAULT_GAP_SECONDS = 5.0


def _timestamp_from_ticks(df: pd.DataFrame) -> pd.Series:
    if "time_msc" in df.columns:
        return pd.to_datetime(pd.to_numeric(df["time_msc"], errors="coerce"), unit="ms", utc=True)
    if "time" in df.columns:
        return pd.to_datetime(pd.to_numeric(df["time"], errors="coerce"), unit="s", utc=True)
    if "timestamp" in df.columns:
        return pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="mixed")
    return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")


def _robust_z(series: pd.Series, window: int) -> pd.Series:
    med = series.rolling(window, min_periods=max(20, window // 10)).median()
    mad = (series - med).abs().rolling(window, min_periods=max(20, window // 10)).median()
    return (series - med) / (1.4826 * mad.replace(0.0, np.nan))


def annotate_ticks(
    frame: pd.DataFrame,
    *,
    rolling_ticks: int = DEFAULT_ROLLING_TICKS,
    startup_seconds: int = DEFAULT_STARTUP_SECONDS,
    wide_multiplier: float = DEFAULT_WIDE_MULTIPLIER,
    extreme_multiplier: float = DEFAULT_EXTREME_MULTIPLIER,
    gap_seconds: float = DEFAULT_GAP_SECONDS,
) -> pd.DataFrame:
    df = frame.copy()
    if df.empty:
        return df

    # Preserve all source columns; only append derived columns.
    df["_original_row"] = np.arange(len(df), dtype=np.int64)
    df["timestamp"] = _timestamp_from_ticks(df)
    df["bid"] = pd.to_numeric(df.get("bid"), errors="coerce")
    df["ask"] = pd.to_numeric(df.get("ask"), errors="coerce")
    if "time_msc" in df.columns:
        df["time_msc"] = pd.to_numeric(df["time_msc"], errors="coerce")
    df = df.sort_values(["timestamp", "_original_row"], kind="stable").reset_index(drop=True)

    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    df["spread"] = df["ask"] - df["bid"]
    df["spread_bps"] = np.where(df["mid"] > 0, df["spread"] / df["mid"] * 10000.0, np.nan)
    df["gap_ms"] = df["timestamp"].diff().dt.total_seconds().mul(1000.0)
    df["gap_ms"] = df["gap_ms"].fillna(0.0).clip(lower=0.0)

    # Multiple quotes can legitimately share a millisecond timestamp.
    df["same_timestamp_count"] = df.groupby("timestamp", dropna=False)["timestamp"].transform("size").fillna(0).astype(int)
    df["same_timestamp_rank"] = df.groupby("timestamp", dropna=False).cumcount()
    df["same_timestamp_group"] = (df["same_timestamp_count"] > 1).astype(int)

    valid_quote = (
        df["timestamp"].notna()
        & df["bid"].gt(0)
        & df["ask"].gt(0)
        & df["bid"].le(df["ask"])
        & df["spread"].ge(DEFAULT_MIN_VALID_SPREAD)
    )
    df["invalid_quote"] = (~valid_quote).astype(int)

    baseline = df["spread"].where(valid_quote).rolling(rolling_ticks, min_periods=max(20, rolling_ticks // 10)).median()
    baseline = baseline.fillna(df["spread"].where(valid_quote).expanding(min_periods=1).median()).clip(lower=1e-9)
    df["spread_baseline"] = baseline
    df["spread_ratio"] = df["spread"] / baseline
    df["spread_zscore_robust"] = _robust_z(df["spread"], rolling_ticks).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # Regimes are contextual, not hard invalidation rules.
    df["spread_regime"] = np.select(
        [
            df["invalid_quote"].eq(1),
            df["spread_ratio"].ge(extreme_multiplier),
            df["spread_ratio"].ge(wide_multiplier),
        ],
        ["INVALID", "EXTREME", "WIDE"],
        default="NORMAL",
    )

    # Session transitions are inferred from UTC hour changes and unusually long gaps.
    hour = df["timestamp"].dt.hour
    previous_hour = hour.shift(1)
    hour_changed = hour.ne(previous_hour) & hour.notna() & previous_hour.notna()
    df["session_transition"] = (hour_changed | df["gap_ms"].ge(startup_seconds * 1000.0)).astype(int)

    # The first startup window of a captured dataset is explicitly marked.  This
    # matters for the user's 01:00 UTC example without assuming a broker session model.
    first_valid_time = df["timestamp"].dropna().iloc[0] if df["timestamp"].notna().any() else pd.NaT
    if pd.notna(first_valid_time):
        df["capture_start_transition"] = (
            (df["timestamp"] - first_valid_time).dt.total_seconds().between(0, startup_seconds, inclusive="both")
        ).astype(int)
    else:
        df["capture_start_transition"] = 0

    df["large_gap"] = (df["gap_ms"] >= gap_seconds * 1000.0).astype(int)
    df["extreme_gap"] = (df["gap_ms"] >= 30000.0).astype(int)
    df["training_eligible_tick"] = (
        (df["invalid_quote"] == 0)
        & (df["timestamp"].notna())
    ).astype(int)
    df["quality_penalty"] = 0.0
    df.loc[df["spread_regime"] == "WIDE", "quality_penalty"] += 0.10
    df.loc[df["spread_regime"] == "EXTREME", "quality_penalty"] += 0.30
    df.loc[df["large_gap"] == 1, "quality_penalty"] += 0.10
    df.loc[df["extreme_gap"] == 1, "quality_penalty"] += 0.20
    df.loc[df["session_transition"] == 1, "quality_penalty"] += 0.10
    df.loc[df["invalid_quote"] == 1, "quality_penalty"] = 1.0
    df["tick_quality_score"] = (1.0 - df["quality_penalty"]).clip(0.0, 1.0)

    # Do not expose an inconsistent free-text timestamp representation.
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    df = df.drop(columns=["_original_row"])
    return df


def audit_ticks(frame: pd.DataFrame, annotated: pd.DataFrame | None = None) -> dict[str, Any]:
    df = annotated if annotated is not None else annotate_ticks(frame)
    if df.empty:
        return {"rows": 0, "valid": False, "error": "empty"}
    spread = pd.to_numeric(df["spread"], errors="coerce")
    gap = pd.to_numeric(df["gap_ms"], errors="coerce")
    return {
        "rows": int(len(df)),
        "time_start": str(df["timestamp"].iloc[0]),
        "time_end": str(df["timestamp"].iloc[-1]),
        "bid_le_ask": bool((df["bid"] <= df["ask"]).all()),
        "invalid_quotes": int(df["invalid_quote"].sum()),
        "same_timestamp_rows": int(df["same_timestamp_group"].sum()),
        "same_timestamp_groups": int((df["same_timestamp_count"] > 1).sum()),
        "spread_gt_2": int((spread > 2).sum()),
        "spread_gt_5": int((spread > 5).sum()),
        "spread_gt_10": int((spread > 10).sum()),
        "spread_gt_20": int((spread > 20).sum()),
        "spread_gt_50": int((spread > 50).sum()),
        "spread_mean": float(spread.mean()),
        "spread_median": float(spread.median()),
        "max_spread": float(spread.max()),
        "gaps_gt_1s": int((gap > 1000).sum()),
        "gaps_gt_5s": int((gap > 5000).sum()),
        "gaps_gt_10s": int((gap > 10000).sum()),
        "gaps_gt_30s": int((gap > 30000).sum()),
        "max_gap_ms": float(gap.max()),
        "wide_rows": int((df["spread_regime"] == "WIDE").sum()),
        "extreme_rows": int((df["spread_regime"] == "EXTREME").sum()),
        "capture_start_transition_rows": int(df["capture_start_transition"].sum()),
        "training_eligible_rows": int(df["training_eligible_tick"].sum()),
        "quality_mean": float(df["tick_quality_score"].mean()),
    }


def annotate_file(path: str | Path, *, output: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    source = Path(path)
    raw = pd.read_csv(source)
    annotated = annotate_ticks(raw)
    target = Path(output) if output else source.with_name(source.stem + "_quality.csv")
    target.parent.mkdir(parents=True, exist_ok=True)
    annotated.to_csv(target, index=False)
    report = audit_ticks(raw, annotated)
    report_path = target.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return target, report
