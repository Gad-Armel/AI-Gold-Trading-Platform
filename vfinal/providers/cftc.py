from __future__ import annotations

"""CFTC COT adapter with a safe local-cache workflow.

The CFTC publishes changing report layouts. We therefore keep the parser
schema-tolerant and require the downloaded file to be explicitly supplied or
cached. No API key is needed.
"""

from pathlib import Path
from typing import Any
import pandas as pd


def normalize_gold_cot(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    cols = {str(c).strip().lower(): c for c in frame.columns}
    date_col = next((cols[k] for k in cols if "date" in k), None)
    if date_col is None:
        raise ValueError("CFTC file has no recognizable date column.")
    frame["report_date"] = pd.to_datetime(frame[date_col], errors="coerce", utc=True)

    aliases = {
        "open_interest": ("open interest", "open_interest", "open_interest_all"),
        "managed_money_long": ("m_money long", "managed money long", "noncommercial long", "noncommercial long all"),
        "managed_money_short": ("m_money short", "managed money short", "noncommercial short", "noncommercial short all"),
    }
    for target, candidates in aliases.items():
        source = next((cols[c] for c in candidates if c in cols), None)
        frame[target] = pd.to_numeric(frame[source], errors="coerce") if source else float("nan")
    if "managed_money_long" in frame and "managed_money_short" in frame:
        frame["managed_money_net"] = frame.managed_money_long - frame.managed_money_short
    return frame.dropna(subset=["report_date"]).sort_values("report_date").reset_index(drop=True)


def filter_gold(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    text_cols = [c for c in frame.columns if frame[c].dtype == "object"]
    if not text_cols:
        return frame
    mask = pd.Series(False, index=frame.index)
    for col in text_cols:
        mask = mask | frame[col].astype(str).str.contains(r"gold|comex", case=False, regex=True, na=False)
    filtered = frame.loc[mask].copy()
    return filtered if not filtered.empty else frame


def positioning_features(frame: pd.DataFrame, lookback: int = 52, as_of: str | None = None) -> dict[str, Any]:
    if frame.empty or "managed_money_net" not in frame:
        return {"available": False}
    data = frame.copy()
    if as_of:
        cutoff = pd.Timestamp(as_of, tz="UTC")
        data = data[data.report_date <= cutoff]
    s = pd.to_numeric(data.managed_money_net, errors="coerce").dropna()
    if s.empty:
        return {"available": False}
    latest = float(s.iloc[-1])
    window = s.tail(lookback)
    percentile = float((window <= latest).mean())
    change_4w = latest - float(s.iloc[-5]) if len(s) >= 5 else 0.0
    return {
        "available": True,
        "report_date": data.iloc[-1].report_date.isoformat(),
        "managed_money_net": latest,
        "managed_money_percentile_52w": percentile,
        "managed_money_change_4w": change_4w,
    }
