"""Offline confidence experiment on local caches; never connects to MT5 or promotes a model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from vfinal.model.calibration import apply_calibrator, fit_logistic_calibrator
from vfinal.model.metrics import brier, ece


FEATURES = (
    "spread", "tick_age", "spread_ratio", "quote_rate", "c_cost_atr",
    "efficiency_6", "efficiency_30", "c_atr", "c_m5_vol_ratio",
    "signed_pressure_6", "signed_pressure_30", "signed_acceleration",
    "signed_extension", "m1_agrees", "m5_agrees", "m15_agrees",
    "c_hour_sin", "c_hour_cos",
)


def episode_indices(frame, probabilities, threshold, *, stress=False, cooldown=30.0):
    probabilities = np.asarray(probabilities, dtype=float)
    if len(probabilities) != len(frame) or not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("Finite probabilities must match every candidate")
    entry = frame.normal_entry_epoch.to_numpy(dtype=float)
    exits = frame["stress_exit" if stress else "normal_exit"].to_numpy(dtype=float)
    if not np.isfinite(entry).all() or not np.isfinite(exits).all() or np.any(np.diff(entry) < 0) or np.any(exits < entry):
        raise ValueError("Episodes need chronological entries and valid exits")
    selected = []
    available = -np.inf
    for index, (opened, closed, probability) in enumerate(zip(entry, exits, probabilities)):
        if probability >= threshold and opened >= available:
            selected.append(index)
            available = closed + cooldown
    return np.asarray(selected, dtype=int)


def day_bootstrap(values, days, *, repetitions=2000):
    daily = pd.DataFrame(dict(profit=values, day=days)).groupby("day").profit.agg(["sum", "count"])
    if len(daily) < 2:
        return None
    generator = np.random.default_rng(20261015)
    indices = generator.integers(0, len(daily), size=(repetitions, len(daily)))
    estimates = daily["sum"].to_numpy()[indices].sum(axis=1) / daily["count"].to_numpy()[indices].sum(axis=1)
    return [round(float(value), 6) for value in np.quantile(estimates, [.025, .975])]


def summarize(frame, probabilities, threshold, *, commission=.10, stress=False):
    selected = episode_indices(frame, probabilities, threshold, stress=stress)
    chosen = frame.iloc[selected]
    pnl = chosen["stress_profit" if stress else "normal_profit"].to_numpy() - commission
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    path = np.r_[0.0, pnl.cumsum()]
    target = (pnl > 0).astype(int)
    prediction = np.asarray(probabilities)[selected]
    return dict(
        trades=len(chosen), days=int(chosen.day.nunique()),
        net=round(float(pnl.sum()), 4),
        expectancy=round(float(pnl.mean()), 6) if len(pnl) else None,
        win_rate=round(float(target.mean()), 6) if len(pnl) else None,
        profit_factor=round(float(gains / losses), 6) if losses > 0 else None,
        drawdown=round(float((np.maximum.accumulate(path) - path).max()), 4),
        brier=round(brier(target, prediction), 6) if len(pnl) else None,
        ece=round(ece(target, prediction), 6) if len(pnl) else None,
        expectancy_day_bootstrap_95=day_bootstrap(pnl, chosen.day.to_numpy()),
        daily=[dict(day=str(day), trades=len(group), net=round(float((group["stress_profit" if stress else "normal_profit"] - commission).sum()), 4))
               for day, group in chosen.groupby("day")],
    )


def reliability(frame, probabilities, commission):
    indices = episode_indices(frame, probabilities, 0.0)
    probability = np.asarray(probabilities)[indices]
    outcomes = (frame.iloc[indices].normal_profit.to_numpy() - commission > 0).astype(int)
    bins = []
    for lower in np.arange(0, 1, .1):
        mask = (probability >= lower) & (probability < lower + .1)
        if mask.any():
            bins.append(dict(lower=round(float(lower), 1), count=int(mask.sum()),
                             predicted=round(float(probability[mask].mean()), 6),
                             observed=round(float(outcomes[mask].mean()), 6)))
    return bins


def experiment(cache_directory, *, commission=.10):
    paths = sorted(Path(cache_directory).glob("*.pkl"))
    if len(paths) < 15:
        raise ValueError("At least 15 captured days are required; no synthetic history is created")
    train_end, validation_end = int(len(paths) * .6), int(len(paths) * .8)
    used = paths[:validation_end]
    frame = pd.concat([pd.read_pickle(path) for path in used], ignore_index=True)
    frame = frame.sort_values("feature_epoch", kind="stable").reset_index(drop=True)
    frame["day"] = frame.day.astype(str)
    biases = frame[["c_m1_bias", "c_m5_bias", "c_m15_bias"]].to_numpy()
    direction = np.where((biases == 1).sum(axis=1) >= 2, 1,
                         np.where((biases == -1).sum(axis=1) >= 2, -1, 0))
    frame["direction"] = direction
    for prefix in ("normal", "stress"):
        frame[prefix + "_profit"] = np.where(direction == 1, frame[prefix + "_buy_profit"], frame[prefix + "_sell_profit"])
        frame[prefix + "_exit"] = np.where(direction == 1, frame[prefix + "_buy_exit_epoch"], frame[prefix + "_sell_exit_epoch"])
    frame["signed_pressure_6"] = direction * frame.pressure_6
    frame["signed_pressure_30"] = direction * frame.pressure_30
    frame["signed_acceleration"] = direction * frame.acceleration
    frame["signed_extension"] = direction * frame.c_m1_extension
    for name in ("m1", "m5", "m15"):
        frame[name + "_agrees"] = (direction == frame["c_" + name + "_bias"]).astype(float)
    frame = frame[(direction != 0) & frame.normal_valid & frame.stress_valid].copy()
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=list(FEATURES) + ["normal_profit", "stress_profit"])
    training_days = [path.stem for path in paths[:train_end]]
    validation_days = [path.stem for path in paths[train_end:validation_end]]
    calibration_days = training_days[-max(3, int(len(training_days) * .2)):]
    fit_days = training_days[:-len(calibration_days)]
    calibration_start = frame.loc[frame.day.isin(calibration_days), "feature_epoch"].min()
    validation_start = frame.loc[frame.day.isin(validation_days), "feature_epoch"].min()
    label_end = frame.normal_entry_epoch + 180
    fit = frame[frame.day.isin(fit_days) & (label_end < calibration_start)].copy()
    calibration = frame[frame.day.isin(calibration_days) & (label_end < validation_start)].copy()
    validation = frame[frame.day.isin(validation_days)].copy()
    target = lambda part: (part.normal_profit.to_numpy() - commission > 0).astype(int)
    if min(len(fit), len(calibration), len(validation)) < 100 or min(len(np.unique(target(part))) for part in (fit, calibration)) < 2:
        raise ValueError("Insufficient independent periods or class diversity")
    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          LogisticRegression(C=.1, max_iter=1000, random_state=20261015))
    model.fit(fit[list(FEATURES)], target(fit))
    raw_calibration = model.predict_proba(calibration[list(FEATURES)])[:, 1]
    calibrator = fit_logistic_calibrator(raw_calibration, target(calibration))
    raw = model.predict_proba(validation[list(FEATURES)])[:, 1]
    probabilities = apply_calibrator(calibrator, raw)
    baseline = np.full(len(validation), target(fit).mean())
    policies = {}
    for name, predictions, threshold in (("all_candidates", probabilities, 0.0),
                                          ("calibrated_055", probabilities, .55),
                                          ("calibrated_065", probabilities, .65),
                                          ("calibrated_075", probabilities, .75)):
        policies[name] = {"normal": summarize(validation, predictions, threshold, commission=commission),
                          "stress_1_5": summarize(validation, predictions, threshold, commission=commission, stress=True)}
    baseline_summary = summarize(validation, baseline, 0.0, commission=commission)
    return dict(
        generated_at=pd.Timestamp.now(tz="UTC").isoformat(), live_approved=False, orders_sent=False,
        fit_days=fit_days, calibration_days=calibration_days, validation_days=validation_days,
        excluded_final_period_files=[path.name for path in paths[validation_end:]],
        excluded_final_period_read=False, fit_rows=len(fit), calibration_rows=len(calibration), validation_rows=len(validation),
        features=list(FEATURES), model="standardized logistic C=0.1 + disjoint chronological sigmoid calibration",
        target="positive net executable 180-second outcome after specified commission, with $5 protective stop",
        commission_usd=commission, policies=policies,
        baseline_constant_probability=float(baseline[0]), baseline_episode_brier=baseline_summary["brier"],
        reliability_bins_nonoverlapping=reliability(validation, probabilities, commission),
        source_manifest=[dict(path=str(path.relative_to(PROJECT)) if path.is_relative_to(PROJECT) else str(path),
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in used],
        limitations=[
            "Exploratory: these training/validation periods were inspected by previous research; no fresh holdout claim.",
            "Cached pickle files must be trusted local project artifacts; they can execute code when loaded.",
            "Candle-majority approximates Advisor 1; it does not reproduce the current runner or native EA.",
            "One simulated position at a time, then 30-second cooldown; five-position portfolio effects are not measured.",
            "Labels include archived bid/ask, 100ms nominal latency and $0.05 per-side slippage; commission is an explicit extra assumption.",
            "Full quote liquidity, stop execution during disconnections and dynamic production exits are not reconstructed.",
            "Few validation days and clustered labels limit uncertainty estimates; day bootstrap is descriptive, not promotion evidence.",
            "A higher probability of profit need not imply positive expected profit; payoff magnitude and costs also matter.",
            "No model artifact is saved, approved, promoted or wired to execution.",
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-directory", type=Path, default=PROJECT / "data/research/entry_efficiency/tick_datasets")
    parser.add_argument("--output", type=Path, default=PROJECT / "data/research/review_20261015/signal_confidence.json")
    parser.add_argument("--commission-usd", type=float, default=.10)
    args = parser.parse_args()
    if not np.isfinite(args.commission_usd) or args.commission_usd < 0:
        parser.error("commission-usd must be finite and nonnegative")
    report = experiment(args.cache_directory, commission=args.commission_usd)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("fit_rows", "calibration_rows", "validation_rows", "policies", "live_approved")}, indent=2))


if __name__ == "__main__":
    main()
