from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


def fit_logistic_calibrator(raw_probability: np.ndarray, target: np.ndarray):
    raw = np.asarray(raw_probability, dtype=float)
    y = np.asarray(target, dtype=int)
    if len(raw) < 20 or len(np.unique(y)) < 2:
        return None
    eps = 1e-6
    logits = np.log(np.clip(raw, eps, 1 - eps) / np.clip(1 - raw, eps, 1 - eps)).reshape(-1, 1)
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=2026)
    model.fit(logits, y)
    return model


def apply_calibrator(calibrator, raw_probability: np.ndarray) -> np.ndarray:
    raw = np.asarray(raw_probability, dtype=float)
    if calibrator is None:
        return np.clip(raw, 1e-6, 1 - 1e-6)
    eps = 1e-6
    logits = np.log(np.clip(raw, eps, 1 - eps) / np.clip(1 - raw, eps, 1 - eps)).reshape(-1, 1)
    return np.clip(calibrator.predict_proba(logits)[:, 1], 1e-6, 1 - 1e-6)
