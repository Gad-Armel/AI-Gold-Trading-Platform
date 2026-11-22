from __future__ import annotations

import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from vfinal.model.walk_forward import _time_purged_train_end, purged_history, calibration_split, non_overlapping_selection, walk_forward_evaluate, NUMERIC, CATEGORICAL
from vfinal.data.labels import label_one
from vfinal.data.dataset import merge_features_labels


class WalkForwardIntegrityTests(unittest.TestCase):
    def test_time_purge_uses_elapsed_seconds_not_row_count(self) -> None:
        frame = pd.DataFrame({"snapshot_timestamp": pd.to_datetime([
            "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z",
            "2026-01-01T00:00:50Z", "2026-01-01T00:01:40Z",
        ])})
        # Test begins at 100s; a 60s purge permits timestamps <=40s, i.e. rows 0-1.
        self.assertEqual(_time_purged_train_end(frame, test_start=3, purge_seconds=60), 2)

    def test_time_purge_rejects_invalid_timestamps(self) -> None:
        frame = pd.DataFrame({"snapshot_timestamp": ["2026-01-01T00:00:00Z", "bad"]})
        with self.assertRaisesRegex(ValueError, "snapshot_timestamp"):
            _time_purged_train_end(frame, test_start=1, purge_seconds=60)

    def test_wait_is_never_silently_labeled_as_buy(self) -> None:
        snapshot = {"timestamp": "2026-01-01T00:00:00Z", "direction": "WAIT"}
        with self.assertRaisesRegex(ValueError, "BUY or SELL"):
            label_one(snapshot, pd.DataFrame(), "SCALP_15S")

    def test_labels_cannot_cross_a_later_period_even_with_short_purge(self):
        frame = pd.DataFrame({
            "snapshot_timestamp": pd.to_datetime([0, 10, 20, 30], unit="s", utc=True),
            "horizon_seconds": [40, 5, 10, 5],
        })
        self.assertEqual(purged_history(frame, 3, 0).index.tolist(), [1])

    def test_known_horizon_names_and_elapsed_purge_are_both_respected(self):
        frame = pd.DataFrame({
            "snapshot_timestamp": pd.to_datetime([0, 10, 20, 100], unit="s", utc=True),
            "horizon": ["SCALP_15S"] * 4,
        })
        self.assertEqual(purged_history(frame, 3, 85).index.tolist(), [0, 1])

    def test_missing_or_invalid_label_horizons_fail_closed(self):
        frame = pd.DataFrame({"snapshot_timestamp": pd.to_datetime([0, 20], unit="s", utc=True)})
        with self.assertRaisesRegex(ValueError, "horizon"):
            purged_history(frame, 1, 0)
        frame["horizon_seconds"] = [float("nan"), 15]
        with self.assertRaisesRegex(ValueError, "positive"):
            purged_history(frame, 1, 0)

    def test_calibration_labels_and_fit_labels_are_separated_in_time(self):
        frame = pd.DataFrame({
            "snapshot_timestamp": pd.date_range("2026-01-01", periods=200, freq="10s", tz="UTC"),
            "horizon_seconds": [120] * 200,
        })
        fit, cal = calibration_split(frame, 100, 60)
        self.assertGreaterEqual(len(fit), 100)
        self.assertLess((fit.snapshot_timestamp + pd.Timedelta(seconds=120)).max(), cal.snapshot_timestamp.min())

    def test_truncated_future_path_cannot_become_a_training_outcome(self):
        snapshot = dict(timestamp="2026-01-01T00:00:00Z", symbol="XAUUSD", direction="BUY", bid=100, ask=100.2)
        ticks = pd.DataFrame(dict(timestamp=["2026-01-01T00:00:01Z"], bid=[102], ask=[102.2]))
        result = label_one(snapshot, ticks, "SCALP_15S")
        self.assertEqual(result.label_quality, "INCOMPLETE_HORIZON")
        self.assertTrue(merge_features_labels([snapshot], pd.DataFrame([result.to_dict()])).empty)

    def test_invalid_executable_quotes_cannot_create_confident_labels(self):
        snapshot = dict(timestamp="2026-01-01T00:00:00Z", symbol="XAUUSD", direction="BUY", bid=100, ask=100.2)
        ticks = pd.DataFrame(dict(timestamp=["2026-01-01T00:00:01Z", "2026-01-01T00:00:15Z"],
                                 bid=[102, 103], ask=[101, 103.2]))
        with self.assertRaisesRegex(ValueError, "quote"):
            label_one(snapshot, ticks, "SCALP_15S")

    def test_complete_evaluation_purges_every_model_and_calibration_boundary(self):
        rows = 600
        frame = pd.DataFrame({name: [0.0] * rows for name in NUMERIC})
        for name in CATEGORICAL:
            frame[name] = "UNKNOWN"
        frame["spread"] = np.arange(rows) * 30.0
        frame["snapshot_timestamp"] = pd.to_datetime(frame.spread, unit="s", utc=True)
        frame["horizon_seconds"] = 60
        frame["target"] = (np.arange(rows) % 5 != 0).astype(int)
        frame["pnl"] = np.where(frame.target, 2.0, -1.0)
        boundaries = []

        class Estimator:
            def fit(self, features, target):
                self.latest = features.spread.max()

            def predict_proba(self, features):
                boundaries.append((self.latest, features.spread.min()))
                return np.tile([.2, .8], (len(features), 1))

        with patch("vfinal.model.walk_forward._pipeline", side_effect=lambda kind: Estimator()):
            report = walk_forward_evaluate(frame, "target", "pnl", purge=30, min_train=30)
        self.assertIn("holdout", report)
        self.assertTrue(boundaries)
        for latest_fit, earliest_prediction in boundaries:
            self.assertLess(latest_fit + 60, earliest_prediction)
        self.assertEqual(report["models"]["LOGISTIC"]["folds_completed"], 5)

    def test_overlapping_labels_cannot_be_counted_as_independent_trades(self):
        frame = pd.DataFrame(dict(snapshot_timestamp=pd.to_datetime([0, 0, 5, 60, 65], unit="s", utc=True),
                                  horizon_seconds=[60] * 5))
        selected = non_overlapping_selection(frame, np.ones(5, dtype=bool))
        self.assertEqual(selected.tolist(), [True, False, False, True, False])


if __name__ == "__main__":
    unittest.main()
