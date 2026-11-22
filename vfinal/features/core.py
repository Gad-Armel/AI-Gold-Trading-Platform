from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def clean_candles(frame: Any, *, closed_only: bool = True) -> pd.DataFrame:
    df = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
    required = {"time", "open", "high", "low", "close"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()
    df["time"] = (pd.to_datetime(df["time"], unit="s", utc=True, errors="coerce")
                  if pd.api.types.is_numeric_dtype(df["time"])
                  else pd.to_datetime(df["time"], utc=True, errors="coerce"))
    for c in ("open", "high", "low", "close", "tick_volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=list(required)).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    # Caller normally passes a live cache where the final row is unfinished.
    return df.iloc[:-1].copy() if closed_only else df


def atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 2:
        return 0.0
    prev = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]).abs(), (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def rsi(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 2:
        return 50.0
    delta = df["close"].diff()
    up = delta.clip(lower=0.0).ewm(alpha=1 / period, adjust=False).mean()
    down = (-delta.clip(upper=0.0)).ewm(alpha=1 / period, adjust=False).mean()
    value = 100 - 100 / (1 + up / down.replace(0, np.nan))
    value = value.where(down > 0, np.where(up > 0, 100.0, 50.0))
    return float(value.iloc[-1]) if np.isfinite(value.iloc[-1]) else 50.0


def adx(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period * 2 + 2:
        return 0.0
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    prev = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]).abs(), (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1 / period, adjust=False).mean().replace(0, np.nan)
    plus = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    minus = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    dx = 100 * (plus - minus).abs() / (plus + minus).replace(0, np.nan)
    value = dx.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    return float(value) if np.isfinite(value) else 0.0


def relative_volume(df: pd.DataFrame, lookback: int = 20) -> float:
    if "tick_volume" not in df.columns or len(df) < lookback + 2:
        return 1.0
    v = pd.to_numeric(df["tick_volume"], errors="coerce")
    base = v.shift(1).rolling(lookback).median().iloc[-1]
    return float(v.iloc[-1] / base) if np.isfinite(base) and base > 0 else 1.0


def ema_slope(df: pd.DataFrame, span: int, bars: int = 3) -> float:
    if len(df) < span + bars + 2:
        return 0.0
    ema = df["close"].ewm(span=span, adjust=False).mean()
    a = float(ema.iloc[-1] - ema.iloc[-1 - bars])
    a_atr = atr(df)
    return a / a_atr if a_atr > 0 else 0.0


def candle_geometry(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"body_atr": 0.0, "upper_wick_atr": 0.0, "lower_wick_atr": 0.0, "range_atr": 0.0, "close_location": 0.5}
    row = df.iloc[-1]
    a = max(atr(df), 1e-9)
    body = abs(float(row.close - row.open))
    upper = float(row.high - max(row.open, row.close))
    lower = float(min(row.open, row.close) - row.low)
    rng = max(float(row.high - row.low), 1e-9)
    return {
        "body_atr": body / a,
        "upper_wick_atr": upper / a,
        "lower_wick_atr": lower / a,
        "range_atr": rng / a,
        "close_location": float((row.close - row.low) / rng),
    }


def candle_features(candles: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for tf in ("M1", "M5", "M15", "H1", "H4"):
        df = clean_candles(candles.get(tf), closed_only=True)
        prefix = tf.lower()
        if df.empty:
            out[f"{prefix}_atr"] = 0.0
            out[f"{prefix}_rsi"] = 50.0
            out[f"{prefix}_adx"] = 0.0
            out[f"{prefix}_ema12_slope_atr"] = 0.0
            out[f"{prefix}_ema26_slope_atr"] = 0.0
            out[f"{prefix}_ema_gap_atr"] = 0.0
            out[f"{prefix}_relative_volume"] = 1.0
            continue
        a = atr(df)
        ema12 = df.close.ewm(span=12, adjust=False).mean().iloc[-1]
        ema26 = df.close.ewm(span=26, adjust=False).mean().iloc[-1]
        geom = candle_geometry(df)
        out.update({
            f"{prefix}_atr": a,
            f"{prefix}_rsi": rsi(df),
            f"{prefix}_adx": adx(df),
            f"{prefix}_ema12_slope_atr": ema_slope(df, 12),
            f"{prefix}_ema26_slope_atr": ema_slope(df, 26),
            f"{prefix}_ema_gap_atr": (ema12 - ema26) / a if a > 0 else 0.0,
            f"{prefix}_relative_volume": relative_volume(df),
        })
        for k, v in geom.items():
            out[f"{prefix}_{k}"] = v
    return out


def tick_features(ticks: Any, now: pd.Timestamp | None = None) -> dict[str, float | str]:
    """Compute executable tick/microstructure features without inventing data.

    time_msc is the primary clock.  Wide spreads and gaps are represented as
    regime/quality features rather than silently deleted.
    """
    df = ticks.copy() if isinstance(ticks, pd.DataFrame) else pd.DataFrame(ticks)
    empty = {
        "tick_imbalance_1s": 0.0, "tick_imbalance_5s": 0.0,
        "quote_pressure_1s": 0.0, "quote_pressure_5s": 0.0,
        "velocity_1s": 0.0, "velocity_5s": 0.0, "efficiency_5s": 0.0,
        "reversal_5s": 0.0, "spread_mean_5s": 0.0, "spread_std_5s": 0.0,
        "spread_expansion_5s": 0.0, "tick_rate_5s": 0.0, "realized_move_5s": 0.0,
        "gap_max_5s": 0.0, "gap_count_gt_1s_5s": 0.0,
        "spread_ratio_5s": 1.0, "spread_zscore_robust_5s": 0.0,
        "wide_spread_ratio_5s": 0.0, "extreme_spread_ratio_5s": 0.0,
        "tick_quality_5s": 0.0, "session_transition_5s": 0.0,
    }
    if df.empty or not {"bid", "ask"}.issubset(df.columns):
        return empty
    if "time_msc" in df.columns:
        ts = pd.to_datetime(pd.to_numeric(df.time_msc, errors="coerce"), unit="ms", utc=True)
    elif "timestamp" in df.columns:
        ts = pd.to_datetime(df.timestamp, utc=True, errors="coerce", format="mixed")
    elif "time" in df.columns:
        ts = pd.to_datetime(pd.to_numeric(df.time, errors="coerce"), unit="s", utc=True)
    else:
        return empty
    df = df.assign(_time=ts)
    for c in ("bid", "ask"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["_time", "bid", "ask"]).sort_values("_time").copy()
    if df.empty:
        return empty
    now = pd.Timestamp(now) if now is not None else df._time.iloc[-1]
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    df = df[df._time <= now].copy()
    if df.empty:
        return empty
    df["mid"] = (df.bid + df.ask) / 2
    df["spread"] = df.ask - df.bid
    df["gap_ms"] = df["_time"].diff().dt.total_seconds().mul(1000).fillna(0).clip(lower=0)
    baseline = df["spread"].where(df["spread"] >= 0).rolling(500, min_periods=20).median()
    baseline = baseline.fillna(df["spread"].where(df["spread"] >= 0).expanding(min_periods=1).median()).clip(lower=1e-9)
    df["spread_ratio"] = df["spread"] / baseline
    df["spread_z"] = (df["spread"] - baseline) / (1.4826 * (df["spread"] - baseline).abs().rolling(500, min_periods=20).median().replace(0, np.nan))
    df["spread_z"] = df["spread_z"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df["session_transition"] = (df["_time"].dt.hour != df["_time"].dt.hour.shift(1)).astype(int)
    df["quality"] = 1.0
    df.loc[(df.bid <= 0) | (df.ask <= 0) | (df.bid > df.ask), "quality"] = 0.0
    df.loc[df["spread_ratio"] >= 3, "quality"] -= 0.10
    df.loc[df["spread_ratio"] >= 8, "quality"] -= 0.20
    df.loc[df["gap_ms"] >= 5000, "quality"] -= 0.10
    df["quality"] = df["quality"].clip(0, 1)
    out = empty.copy()
    for seconds in (1, 5):
        s = df[df._time >= now - pd.Timedelta(seconds=seconds)].copy()
        if len(s) < 4:
            continue
        changes = s.mid.diff().dropna()
        nonzero = changes[changes != 0]
        signs = np.sign(changes.to_numpy())
        tick_imb = float(np.mean(np.sign(nonzero))) if not nonzero.empty else 0.0
        quote_p = float(np.mean((np.sign(s.bid.diff().fillna(0)) + np.sign(s.ask.diff().fillna(0))) / 2))
        net = float(s.mid.iloc[-1] - s.mid.iloc[0])
        path = float(changes.abs().sum())
        spread_mean = float(s.spread.mean())
        spread_baseline = float(s.spread_ratio.median())
        out.update({
            f"tick_imbalance_{seconds}s": tick_imb,
            f"quote_pressure_{seconds}s": quote_p,
            f"velocity_{seconds}s": net / max(seconds, 1),
            f"efficiency_{seconds}s": abs(net) / path if path > 0 else 0.0,
            f"reversal_{seconds}s": float(np.mean(signs[1:] != signs[:-1])) if len(signs) > 1 else 0.0,
            f"spread_mean_{seconds}s": spread_mean,
            f"spread_std_{seconds}s": float(s.spread.std(ddof=0)),
            f"spread_expansion_{seconds}s": float((s.spread.iloc[-1] - s.spread.iloc[0]) / max(spread_mean, 1e-9)),
            f"tick_rate_{seconds}s": len(s) / max(seconds, 1),
            f"realized_move_{seconds}s": float(np.sqrt(np.square(changes.to_numpy()).sum())),
        })
        if seconds == 5:
            out["gap_max_5s"] = float(s.gap_ms.max())
            out["gap_count_gt_1s_5s"] = float((s.gap_ms > 1000).sum())
            out["spread_ratio_5s"] = spread_baseline
            out["spread_zscore_robust_5s"] = float(s.spread_z.iloc[-1])
            out["wide_spread_ratio_5s"] = float((s.spread_ratio >= 3).mean())
            out["extreme_spread_ratio_5s"] = float((s.spread_ratio >= 8).mean())
            out["tick_quality_5s"] = float(s.quality.mean())
            out["session_transition_5s"] = float(s.session_transition.max())
    return out


def time_features(timestamp: Any) -> dict[str, float | str]:
    t = pd.Timestamp(timestamp)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    hour = t.hour + t.minute / 60 + t.second / 3600
    angle = 2 * math.pi * hour / 24
    # Session labels are deliberately coarse and UTC-based.
    session = "ASIA" if hour < 8 else "LONDON" if hour < 13 else "NEW_YORK" if hour < 21 else "LATE_US"
    return {"hour_sin": math.sin(angle), "hour_cos": math.cos(angle), "utc_hour": hour, "session": session}
