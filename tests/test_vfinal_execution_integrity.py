import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from vfinal.execution.decision import decide
from vfinal.execution.vfinal_meta_engine import apply_gate, score_candidate


class ProbabilityModel:
    features = ["direction"]

    def __init__(self, probability):
        self.probability = probability

    def predict_proba(self, frame):
        return np.array([[1 - self.probability, self.probability]])


class ExecutionIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.artifact = dict(approved=True, format_version=2, direction="BUY", threshold=.65, model=ProbabilityModel(.8))
        self.profile = dict(direction="BUY")

    def decide(self, **kwargs):
        with patch("vfinal.execution.decision.load_artifact", return_value=self.artifact):
            return decide(self.profile, artifact_path="unused", reward_usd=2, risk_usd=1, cost_usd=kwargs.get("cost", .1))

    def score(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "model.joblib"
            path.touch()
            with patch("vfinal.execution.vfinal_meta_engine.joblib.load", return_value=self.artifact):
                return score_candidate(self.profile, str(path))

    def test_nonfinite_probability_cannot_authorize_either_gate(self):
        for probability in (float("nan"), float("inf"), -.1, 1.1):
            self.artifact["model"] = ProbabilityModel(probability)
            self.assertEqual(self.decide()["action"], "WAIT")
            self.assertFalse(self.score()["allowed"])

    def test_legacy_validation_and_wrong_direction_require_revalidation(self):
        self.artifact["format_version"] = 1
        self.assertEqual(self.decide()["action"], "WAIT")
        self.assertFalse(self.score()["allowed"])
        self.artifact["format_version"] = 2
        self.artifact["direction"] = "SELL"
        self.assertEqual(self.decide()["action"], "WAIT")
        self.assertFalse(self.score()["allowed"])

    def test_invalid_costs_cannot_authorize_expected_value(self):
        self.assertEqual(self.decide(cost=float("nan"))["action"], "WAIT")
        result = apply_gate(dict(allowed=True), self.profile, reward_usd=2, risk_usd=1, cost_usd=float("nan"))
        self.assertFalse(result["allowed"])

    def test_valid_probability_does_not_override_existing_block(self):
        with patch("vfinal.execution.decision.load_artifact", return_value=self.artifact):
            result = decide(self.profile, artifact_path="unused", reward_usd=2, risk_usd=1, cost_usd=.1, hard_blocks=["NEWS"])
        self.assertEqual(result["action"], "WAIT")
        self.assertEqual(self.decide()["action"], "BUY")
