from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from vfinal.model.train import train


class DummyModel:
    features = []


def _frame(rows: int = 300) -> pd.DataFrame:
    return pd.DataFrame({
        "horizon": ["SCALP_60S"] * rows,
        "direction": ["BUY"] * rows,
        "outcome": [index % 2 for index in range(rows)],
        "pnl_if_exit": [1.0 if index % 2 else -1.0 for index in range(rows)],
    })


def _passing_result() -> dict:
    return {"approved": True, "threshold": 0.61, "selected_model": "LOGISTIC", "fitted_model": DummyModel()}


class TrainingPromotionTests(unittest.TestCase):
    def test_validation_does_not_implicitly_promote(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            with patch("vfinal.model.train.MODELS", target), patch("vfinal.model.train.REPORTS", target), \
                    patch("vfinal.model.train.walk_forward_evaluate", return_value=_passing_result()):
                result = train(_frame(), horizon="SCALP_60S", direction="BUY", promote=False)
        self.assertEqual(result["status"], "VALIDATED_NOT_PROMOTED")
        self.assertFalse(result["approved"])
        self.assertFalse(result["artifact"]["approved"])

    def test_explicit_promotion_requires_passing_validation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            with patch("vfinal.model.train.MODELS", target), patch("vfinal.model.train.REPORTS", target), \
                    patch("vfinal.model.train.walk_forward_evaluate", return_value=_passing_result()):
                result = train(_frame(), horizon="SCALP_60S", direction="BUY", promote=True)
        self.assertEqual(result["status"], "APPROVED")
        self.assertTrue(result["approved"])


if __name__ == "__main__":
    unittest.main()
