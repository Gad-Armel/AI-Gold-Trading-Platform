from __future__ import annotations

"""Chronological, cost-aware bar backtest for the medium shadow hypothesis.

This is a research screen, not an execution simulator. Historical MT5 bars do
not expose executable bid/ask history, so a configurable fixed spread is
charged and bars touching target and stop are resolved against the strategy.
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import scalping_settings


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    return frame.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def _aggregate(frame: pd.DataFrame, rule: str, expected: int, duration: pd.Timedelta) -> pd.DataFrame:
    work = frame.set_index("time")
    grouped = work.resample(rule, origin="epoch", label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    result = result.loc[grouped["close"].count() >= expected].dropna().reset_index()
    result["available_at"] = result["time"] + duration
    return result


def _directions(frame: pd.DataFrame, *, available_after: pd.Timedelta) -> pd.DataFrame:
    result = frame.copy()
    close = pd.to_numeric(result["close"])
    high = pd.to_numeric(result["high"])
    low = pd.to_numeric(result["low"])
    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()
    previous = close.shift()
    tr = pd.concat([(high-low).abs(), (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    separation = fast - slow
    slope = fast - fast.shift(3)
    threshold = atr * float(scalping_settings.SCALPING_MEDIUM_MIN_EMA_SEPARATION_ATR)
    result["direction"] = "NEUTRAL"
    result.loc[(separation >= threshold) & (slope > 0), "direction"] = "BUY"
    result.loc[(separation <= -threshold) & (slope < 0), "direction"] = "SELL"
    result["atr"] = atr
    result["last_close"] = close
    if "available_at" not in result:
        result["available_at"] = result["time"] + available_after
    return result[["available_at", "direction", "atr", "last_close"]].dropna().sort_values("available_at")


def _attach(base: pd.DataFrame, view: pd.DataFrame, prefix: str) -> pd.DataFrame:
    renamed = view.rename(columns={
        "direction": f"{prefix}_direction",
        "atr": f"{prefix}_atr",
        "last_close": f"{prefix}_last_close",
    })
    return pd.merge_asof(
        base.sort_values("time"),
        renamed.sort_values("available_at"),
        left_on="time",
        right_on="available_at",
        direction="backward",
    ).drop(columns=["available_at"])


def run_medium_horizon_backtest(
    dataset_folder: str,
    *,
    assumed_spread_usd: float = 0.30,
) -> dict[str, Any]:
    folder = Path(dataset_folder)
    symbol = "XAUUSD"
    m15 = _load(folder / f"{symbol}_M15.csv")
    h1 = _load(folder / f"{symbol}_H1.csv")
    h4 = _load(folder / f"{symbol}_H4.csv")
    m45 = _aggregate(m15, "45min", 3, pd.Timedelta(minutes=45))
    h2 = _aggregate(h1, "2h", 2, pd.Timedelta(hours=2))

    timeline = m15.copy()
    for name, frame, delay in (
        ("M45", m45, pd.Timedelta(0)),
        ("H1", h1, pd.Timedelta(hours=1)),
        ("H2", h2, pd.Timedelta(0)),
        ("H4", h4, pd.Timedelta(hours=4)),
    ):
        timeline = _attach(timeline, _directions(frame, available_after=delay), name)
    timeline = timeline.dropna().reset_index(drop=True)

    positions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    target = float(scalping_settings.SCALPING_MEDIUM_TARGET_USD)
    stop = float(scalping_settings.SCALPING_MEDIUM_HARD_STOP_USD)
    maximum_bars = int(float(scalping_settings.SCALPING_MEDIUM_MAX_HOLD_SECONDS) / 900)
    max_positions = int(scalping_settings.SCALPING_MEDIUM_MAX_OPEN_POSITIONS)
    spread = float(assumed_spread_usd)
    episode_direction = ""
    episode_consumed = False

    for index, bar in timeline.iterrows():
        survivors: list[dict[str, Any]] = []
        for trade in positions:
            age_bars = index - trade["entry_index"] + 1
            if trade["direction"] == "BUY":
                target_mid = trade["entry_price"] + target + spread / 2
                stop_mid = trade["entry_price"] - stop + spread / 2
                hit_target = float(bar["high"]) >= target_mid
                hit_stop = float(bar["low"]) <= stop_mid
            else:
                target_mid = trade["entry_price"] - target - spread / 2
                stop_mid = trade["entry_price"] + stop - spread / 2
                hit_target = float(bar["low"]) <= target_mid
                hit_stop = float(bar["high"]) >= stop_mid
            reason = ""
            pnl = 0.0
            if hit_stop:  # pessimistic when both barriers occur inside one bar
                reason, pnl = "STOP", -stop
            elif hit_target:
                reason, pnl = "TARGET", target
            elif age_bars >= maximum_bars:
                exit_quote = float(bar["close"]) - spread / 2 if trade["direction"] == "BUY" else float(bar["close"]) + spread / 2
                move = exit_quote - trade["entry_price"]
                pnl = move if trade["direction"] == "BUY" else -move
                reason = "TIME"
            if reason:
                trades.append({
                    **trade,
                    "exit_time": bar["time"].isoformat(),
                    "pnl_usd": round(pnl, 4),
                    "reason": reason,
                })
            else:
                survivors.append(trade)
        positions = survivors

        directions = [str(bar[f"{name}_direction"]) for name in ("M45", "H1", "H2", "H4")]
        buy_votes, sell_votes = directions.count("BUY"), directions.count("SELL")
        required = int(scalping_settings.SCALPING_MEDIUM_MIN_DIRECTIONAL_VOTES)
        direction = "BUY" if buy_votes >= required else "SELL" if sell_votes >= required else "NEUTRAL"
        if (
            direction in {"BUY", "SELL"}
            and bool(scalping_settings.SCALPING_MEDIUM_REQUIRE_H4_NOT_OPPOSED)
            and str(bar["H4_direction"]) in {"BUY", "SELL"}
            and str(bar["H4_direction"]) != direction
        ):
            direction = "NEUTRAL"
        distance = abs(float(bar["open"]) - float(bar["H1_last_close"])) / max(float(bar["H1_atr"]), 0.01)
        if distance > float(scalping_settings.SCALPING_MEDIUM_MAX_ENTRY_DISTANCE_ATR):
            direction = "NEUTRAL"
        if positions and any(item["direction"] != direction for item in positions):
            direction = "NEUTRAL"
        if direction not in {"BUY", "SELL"}:
            episode_direction, episode_consumed = "", False
        elif direction != episode_direction:
            episode_direction, episode_consumed = direction, False
        if direction in {"BUY", "SELL"} and not episode_consumed and len(positions) < max_positions:
            entry = float(bar["open"]) + spread / 2 if direction == "BUY" else float(bar["open"]) - spread / 2
            positions.append({
                "direction": direction,
                "entry_time": bar["time"].isoformat(),
                "entry_price": round(entry, 6),
                "entry_index": index,
            })
            episode_consumed = True

    values = [float(item["pnl_usd"]) for item in trades]
    wins = sum(value > 0 for value in values)
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    equity, peak, max_drawdown = 0.0, 0.0, 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    folds = []
    if trades:
        trade_frame = pd.DataFrame(trades)
        trade_frame["exit_time"] = pd.to_datetime(trade_frame["exit_time"], utc=True)
        quarter_key = trade_frame["exit_time"].dt.tz_localize(None).dt.to_period("Q")
        for period, group in trade_frame.groupby(quarter_key):
            fold_values = group["pnl_usd"].astype(float)
            folds.append({
                "quarter": str(period),
                "trades": int(len(group)),
                "win_rate": round(float((fold_values > 0).mean()), 6),
                "net_profit": round(float(fold_values.sum()), 4),
                "expectancy": round(float(fold_values.mean()), 6),
            })
    win_rate = wins / len(values) if values else 0.0
    expectancy = sum(values) / len(values) if values else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else 0.0
    negative_folds = sum(item["expectancy"] <= 0 for item in folds)
    approval_checks = {
        "minimum_trades": len(values) >= int(scalping_settings.SCALPING_MEDIUM_APPROVAL_MIN_TRADES),
        "minimum_win_rate": win_rate >= float(scalping_settings.SCALPING_MEDIUM_APPROVAL_MIN_WIN_RATE),
        "positive_expectancy": expectancy >= float(scalping_settings.SCALPING_MEDIUM_APPROVAL_MIN_EXPECTANCY_USD),
        "profit_factor": profit_factor >= float(scalping_settings.SCALPING_MEDIUM_APPROVAL_MIN_PROFIT_FACTOR),
        "fold_stability": negative_folds <= int(scalping_settings.SCALPING_MEDIUM_APPROVAL_MAX_NEGATIVE_FOLDS),
    }
    return {
        "research_only": True,
        "approved": all(approval_checks.values()),
        "approval_checks": approval_checks,
        "spread_assumption_usd": spread,
        "intrabar_policy": "STOP_FIRST_IF_TARGET_AND_STOP_TOUCH_SAME_M15_BAR",
        "trades": len(values),
        "wins": wins,
        "losses": sum(value < 0 for value in values),
        "win_rate": round(win_rate, 6),
        "net_profit": round(sum(values), 4),
        "expectancy": round(expectancy, 6),
        "profit_factor": round(profit_factor, 6),
        "max_drawdown_usd": round(max_drawdown, 4),
        "quarterly_folds": folds,
        "warning": "Bar backtest with assumed spread; validate on forward shadow bid/ask outcomes.",
    }


def save_backtest_report(report: dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
