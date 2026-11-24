from __future__ import annotations

import math
import numpy as np


def brier(y, p) -> float:
    y = np.asarray(y, dtype=float); p = np.asarray(p, dtype=float)
    return float(np.mean((p - y) ** 2)) if len(y) else float("nan")


def ece(y, p, bins: int = 10) -> float:
    y = np.asarray(y, dtype=float); p = np.asarray(p, dtype=float)
    if not len(y): return float("nan")
    edges = np.linspace(0, 1, bins + 1); total = len(y); value = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if not mask.any(): continue
        value += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(value)


def profit_factor(pnl) -> float:
    pnl = np.asarray(pnl, dtype=float)
    gains = pnl[pnl > 0].sum(); losses = -pnl[pnl < 0].sum()
    return float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)


def metrics(y, p, pnl, selected) -> dict:
    y = np.asarray(y, dtype=int); p = np.asarray(p, dtype=float); pnl = np.asarray(pnl, dtype=float); selected = np.asarray(selected, dtype=bool)
    count = int(selected.sum())
    chosen_y = y[selected]; chosen_pnl = pnl[selected]
    return {
        "trades": count,
        "coverage": float(count / len(y)) if len(y) else 0.0,
        "win_rate": float(chosen_y.mean()) if count else 0.0,
        "expectancy": float(chosen_pnl.mean()) if count else 0.0,
        "profit_factor": profit_factor(chosen_pnl) if count else 0.0,
        "brier": brier(y, p),
        "ece": ece(y, p),
        "total_pnl": float(chosen_pnl.sum()) if count else 0.0,
    }


def expected_value(probability: float, reward: float, risk: float, cost: float) -> float:
    return probability * reward - (1.0 - probability) * risk - cost


def wilson_lower_bound(wins: int, total: int, z: float = 1.6448536269514722) -> float:
    if total <= 0: return 0.0
    p = wins / total; denom = 1 + z*z/total
    centre = p + z*z/(2*total); spread = z * math.sqrt((p*(1-p) + z*z/(4*total))/total)
    return float(max(0.0, (centre - spread) / denom))
