from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import scalping_settings
from services.research.v6_approval import write_v6_approval, v6_settings_hash
from services.research.v63_self_learning import load_v63_champion_status
from services.research.v6_outcome_quality import research_outcome_eligible


def _load_history() -> pd.DataFrame:
    path = Path(scalping_settings.SCALPING_V6_SHADOW_HISTORY_PATH)
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(row, dict)
                and row.get("status") == "CLOSED"
                and research_outcome_eligible(row)
            ):
                rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["closed_at"] = pd.to_datetime(df.get("closed_at"), utc=True, errors="coerce")
    df["opened_at"] = pd.to_datetime(df.get("opened_at"), utc=True, errors="coerce")
    df["pnl"] = pd.to_numeric(df.get("final_profit_usd"), errors="coerce")
    df = df[df["pnl"].notna() & df["closed_at"].notna()].sort_values("closed_at").reset_index(drop=True)
    return df


def _metrics(values: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return {"trades": 0, "net_profit": 0.0, "expectancy": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "maximum_drawdown": 0.0}
    gross_profit = float(values[values > 0].sum())
    gross_loss = float(-values[values < 0].sum())
    equity = values.cumsum()
    drawdown = equity.cummax() - equity
    return {
        "trades": int(len(values)),
        "net_profit": round(float(values.sum()), 4),
        "expectancy": round(float(values.mean()), 6),
        "win_rate": round(float((values > 0).mean()), 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "maximum_drawdown": round(float(drawdown.max()), 4),
        "average_win": round(float(values[values > 0].mean()), 6) if (values > 0).any() else 0.0,
        "average_loss": round(float(values[values < 0].mean()), 6) if (values < 0).any() else 0.0,
    }


def _walk_forward_folds(df: pd.DataFrame) -> list[dict[str, Any]]:
    requested = int(scalping_settings.SCALPING_V6_PROMOTION_MIN_WALK_FORWARD_FOLDS)
    if len(df) < requested * 20:
        return []
    test_size = max(20, len(df) // (requested + 2))
    initial_train = len(df) - requested * test_size
    folds=[]
    for index in range(requested):
        test_start = initial_train + index * test_size
        test_end = len(df) if index == requested - 1 else test_start + test_size
        train = df.iloc[:test_start]
        test = df.iloc[test_start:test_end]
        folds.append({
            "fold": index + 1,
            "train_trades": int(len(train)),
            "test_start": test["closed_at"].min().isoformat() if not test.empty else None,
            "test_end": test["closed_at"].max().isoformat() if not test.empty else None,
            "test": _metrics(test["pnl"]),
        })
    return folds


def build_v6_walk_forward_report(*, write_approval: bool = True) -> dict[str, Any]:
    df = _load_history()
    overall = _metrics(df["pnl"]) if not df.empty else _metrics(pd.Series(dtype=float))
    active_days = int(df["closed_at"].dt.date.nunique()) if not df.empty else 0
    recent_n = int(scalping_settings.SCALPING_V6_PROMOTION_RECENT_TRADES)
    recent = _metrics(df.tail(recent_n)["pnl"]) if not df.empty else _metrics(pd.Series(dtype=float))
    folds = _walk_forward_folds(df)
    negative_folds = sum(1 for fold in folds if float(fold["test"]["net_profit"]) <= 0.0)

    bootstrap_p05 = 0.0
    if len(df) >= 20:
        rng = np.random.default_rng(20260717)
        values = df["pnl"].to_numpy(float)
        samples = int(scalping_settings.SCALPING_V6_PROMOTION_BOOTSTRAP_SAMPLES)
        means = rng.choice(values, size=(samples, len(values)), replace=True).mean(axis=1)
        bootstrap_p05 = float(np.quantile(means, 0.05))

    model_status = load_v63_champion_status()
    checks = {
        "closed_shadow_trades": overall["trades"] >= int(scalping_settings.SCALPING_V6_PROMOTION_MIN_CLOSED_SHADOW_TRADES),
        "active_days": active_days >= int(scalping_settings.SCALPING_V6_PROMOTION_MIN_ACTIVE_DAYS),
        "walk_forward_folds": len(folds) >= int(scalping_settings.SCALPING_V6_PROMOTION_MIN_WALK_FORWARD_FOLDS),
        "profit_factor": float(overall["profit_factor"]) >= float(scalping_settings.SCALPING_V6_PROMOTION_MIN_PROFIT_FACTOR),
        "minimum_win_rate": float(overall["win_rate"]) >= float(scalping_settings.SCALPING_V63_TARGET_WIN_RATE),
        "approved_calibrated_model": (not bool(getattr(scalping_settings, "SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL", True))) or bool(model_status.get("approved", False)),
        "expectancy": float(overall["expectancy"]) >= float(scalping_settings.SCALPING_V6_PROMOTION_MIN_EXPECTANCY_USD),
        "recent_profit_factor": float(recent["profit_factor"]) >= float(scalping_settings.SCALPING_V6_PROMOTION_MIN_RECENT_PROFIT_FACTOR),
        "maximum_drawdown": float(overall["maximum_drawdown"]) <= float(scalping_settings.SCALPING_V6_PROMOTION_MAX_DRAWDOWN_USD),
        "negative_folds": negative_folds <= int(scalping_settings.SCALPING_V6_PROMOTION_MAX_NEGATIVE_FOLDS),
        "bootstrap_expectancy_p05": bootstrap_p05 >= float(scalping_settings.SCALPING_V6_PROMOTION_MIN_BOOTSTRAP_EXPECTANCY_P05),
    }
    approved = all(checks.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "settings_hash": v6_settings_hash(),
        "approved": approved,
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "active_days": active_days,
        "overall": overall,
        "recent": recent,
        "bootstrap_expectancy_p05": round(bootstrap_p05, 6),
        "negative_folds": negative_folds,
        "folds": folds,
        "history_path": scalping_settings.SCALPING_V6_SHADOW_HISTORY_PATH,
        "v63_model_status": model_status,
    }
    if write_approval:
        report["approval_path"] = write_v6_approval(report, approved=approved)
    return report


def print_v6_walk_forward_report(report: dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print("V6 WALK-FORWARD SHADOW PROMOTION REPORT")
    print("=" * 78)
    print(f"Status: {'APPROVED FOR CONTROLLED DEMO' if report['approved'] else 'SHADOW ONLY / BLOCKED'}")
    overall=report["overall"]; recent=report["recent"]
    print(f"Closed shadow trades: {overall['trades']} | active days: {report['active_days']}")
    print(f"Net=${overall['net_profit']:.2f} | expectancy=${overall['expectancy']:.3f} | PF={overall['profit_factor']:.2f} | WR={overall['win_rate']*100:.1f}% | max DD=${overall['maximum_drawdown']:.2f}")
    print(f"Recent {recent['trades']}: PF={recent['profit_factor']:.2f} | expectancy=${recent['expectancy']:.3f}")
    print(f"Walk-forward folds={len(report['folds'])} | negative folds={report['negative_folds']} | bootstrap expectancy p05=${report['bootstrap_expectancy_p05']:.3f}")
    model = report.get("v63_model_status", {}) or {}
    print(f"Calibrated model: {'APPROVED' if model.get('approved') else 'BLOCKED'} | threshold={model.get('threshold')} | rows={model.get('training_rows')}")
    if report["failed_checks"]:
        print("Failed: " + ", ".join(report["failed_checks"]))
    print("Approval artifact: " + str(report.get("approval_path", "not written")))
    print("=" * 78)
