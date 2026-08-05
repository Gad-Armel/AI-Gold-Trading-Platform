from __future__ import annotations

"""Append-only, broker-native forward data for medium-horizon validation."""

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import MetaTrader5 as mt5
import numpy as np
import pandas as pd


SCHEMA_VERSION = 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def merge_forward_rows(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Merge by UTC timestamp while refusing to alter previously stored rows."""
    if incoming.empty:
        return existing.copy()
    new = incoming.copy()
    new["time"] = pd.to_datetime(new["time"], utc=True)
    new = new.drop_duplicates("time", keep="last").sort_values("time")
    if existing.empty:
        return new.reset_index(drop=True)
    old = existing.copy()
    old["time"] = pd.to_datetime(old["time"], utc=True)
    old = old.drop_duplicates("time", keep="first").sort_values("time")
    overlap = old.merge(new, on="time", suffixes=("_old", "_new"))
    shared = [column for column in old.columns if column != "time" and column in new.columns]
    for column in shared:
        left, right = overlap[f"{column}_old"], overlap[f"{column}_new"]
        numeric = pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right)
        equal = np.isclose(left.astype(float), right.astype(float), equal_nan=True) if numeric else left.eq(right)
        if not bool(np.all(equal)):
            raise ValueError(f"Incoming data would revise immutable forward rows ({column}).")
    unseen = new[~new["time"].isin(old["time"])]
    return pd.concat([old, unseen], ignore_index=True).sort_values("time").reset_index(drop=True)


def aggregate_tick_costs(ticks: pd.DataFrame) -> pd.DataFrame:
    """Aggregate actual quote spreads into one-minute validation buckets."""
    if ticks.empty:
        return pd.DataFrame()
    frame = ticks.copy()
    unit = "ms" if pd.to_numeric(frame["time_msc"], errors="coerce").max() > 10**11 else "s"
    frame["tick_time"] = pd.to_datetime(frame["time_msc"], unit=unit, utc=True)
    frame = frame[(frame["ask"] > 0) & (frame["bid"] > 0)]
    frame["spread"] = frame["ask"] - frame["bid"]
    frame = frame[frame["spread"] >= 0]
    frame["time"] = frame["tick_time"].dt.floor("min")
    grouped = frame.groupby("time", sort=True)["spread"]
    result = grouped.agg(tick_count="size", spread_min="min", spread_median="median", spread_max="max")
    result["spread_p75"] = grouped.quantile(0.75)
    result["spread_p90"] = grouped.quantile(0.90)
    return result.reset_index()


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    output = frame.copy()
    if "time" in output:
        output["time"] = pd.to_datetime(output["time"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    output.to_csv(temporary, index=False)
    try:
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def collect_forward_batch(
    symbol: str,
    *,
    root: str,
    anchor_utc: datetime,
    now_utc: datetime | None = None,
    overlap_minutes: int = 2,
) -> dict[str, Any]:
    """Append closed M1 bars and quote-cost summaries after a fixed anchor."""
    if anchor_utc.tzinfo is None:
        raise ValueError("anchor_utc must be timezone-aware.")
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    anchor = anchor_utc.astimezone(timezone.utc)
    folder = Path(root) / symbol
    folder.mkdir(parents=True, exist_ok=True)
    bars_path, costs_path = folder / "forward_M1.csv", folder / "forward_M1_costs.csv"
    metadata_path = folder / "metadata.json"
    existing_bars, existing_costs = _read_csv(bars_path), _read_csv(costs_path)

    last_values = []
    for frame in (existing_bars, existing_costs):
        if not frame.empty:
            last_values.append(pd.to_datetime(frame["time"], utc=True).max().to_pydatetime())
    start = max([anchor, *last_values]) - timedelta(minutes=overlap_minutes)
    if start < anchor:
        start = anchor
    # The current minute is incomplete and must never enter a forward evaluation.
    end = now.replace(second=0, microsecond=0)
    if start >= end:
        return {"status": "NO_NEW_CLOSED_MINUTE", "from_utc": start.isoformat(), "to_utc": end.isoformat()}

    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start, end)
    bars = pd.DataFrame(rates) if rates is not None else pd.DataFrame()
    if not bars.empty:
        bars["time"] = pd.to_datetime(bars["time"], unit="s", utc=True)
        bars = bars[bars["time"] < end]
    ticks_raw = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_INFO)
    ticks = pd.DataFrame(ticks_raw) if ticks_raw is not None else pd.DataFrame()
    costs = aggregate_tick_costs(ticks)
    if not costs.empty:
        first_complete_minute = pd.Timestamp(anchor).ceil("min")
        costs = costs[(costs["time"] >= first_complete_minute) & (costs["time"] < end)]

    merged_bars = merge_forward_rows(existing_bars, bars)
    merged_costs = merge_forward_rows(existing_costs, costs)
    if not merged_bars.empty:
        _write_csv(merged_bars, bars_path)
    if not merged_costs.empty:
        _write_csv(merged_costs, costs_path)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "untouched chronological forward confirmation only",
        "symbol": symbol,
        "anchor_utc": anchor.isoformat(),
        "last_collection_utc": now.isoformat(),
        "source": {
            "bars": "MetaTrader5.copy_rates_range",
            "costs": "MetaTrader5.copy_ticks_range(COPY_TICKS_INFO)",
        },
        "immutable_overlap_check": True,
        "closed_minutes_only": True,
        "bars": {"rows": len(merged_bars), "sha256": _sha256(bars_path) if bars_path.exists() else None},
        "costs": {"rows": len(merged_costs), "sha256": _sha256(costs_path) if costs_path.exists() else None},
        "warning": "Do not tune candidates on this dataset; use it once for locked-model confirmation.",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"status": "OK", **metadata, "metadata_path": str(metadata_path)}


def forward_readiness(
    root: str,
    symbol: str,
    *,
    minimum_calendar_days: int = 90,
    minimum_matched_minutes: int = 20_000,
) -> dict[str, Any]:
    """Report only coverage, keeping forward prices and outcomes sealed."""
    folder = Path(root) / symbol
    cohort_path = folder / "cohort.json"
    if not cohort_path.exists():
        return {"status": "NOT_INITIALIZED", "ready": False}
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    anchor = pd.Timestamp(cohort["anchor_utc"])
    bars = _read_csv(folder / "forward_M1.csv")
    costs = _read_csv(folder / "forward_M1_costs.csv")
    if bars.empty or costs.empty:
        matched = pd.DataFrame()
    else:
        bars["time"] = pd.to_datetime(bars["time"], utc=True)
        costs["time"] = pd.to_datetime(costs["time"], utc=True)
        matched = bars[["time"]].merge(costs[["time"]], on="time", how="inner")
    latest = pd.to_datetime(matched["time"], utc=True).max() if not matched.empty else anchor
    calendar_days = max(0.0, (latest - anchor).total_seconds() / 86400)
    rows = int(len(matched))
    checks = {
        "minimum_calendar_days": calendar_days >= minimum_calendar_days,
        "minimum_matched_minutes": rows >= minimum_matched_minutes,
    }
    return {
        "status": "READY_FOR_ONE_TIME_LOCKED_CONFIRMATION" if all(checks.values()) else "ACCUMULATING",
        "ready": all(checks.values()),
        "anchor_utc": anchor.isoformat(),
        "latest_complete_utc": latest.isoformat(),
        "calendar_days": round(calendar_days, 3),
        "matched_minutes": rows,
        "requirements": {
            "calendar_days": minimum_calendar_days,
            "matched_minutes": minimum_matched_minutes,
            "minimum_confirmed_trades_after_unseal": 200,
            "minimum_win_rate": 0.59,
            "minimum_expectancy_usd": 0.03,
            "minimum_profit_factor": 1.15,
            "maximum_negative_folds": 1,
        },
        "checks": checks,
        "sealed": not all(checks.values()),
        "note": "Coverage only. No price, signal, or P/L inspection is performed here.",
    }
