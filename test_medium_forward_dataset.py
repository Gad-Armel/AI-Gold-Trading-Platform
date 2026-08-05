from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import pandas as pd

from services.research.medium_forward_dataset import (
    _write_csv,
    aggregate_tick_costs,
    forward_readiness,
    merge_forward_rows,
)


class ForwardDatasetTests(unittest.TestCase):
    def test_merge_appends_only_unseen_rows(self) -> None:
        old = pd.DataFrame({"time": ["2026-07-24T10:00:00Z"], "close": [4000.0]})
        new = pd.DataFrame({
            "time": ["2026-07-24T10:00:00Z", "2026-07-24T10:01:00Z"],
            "close": [4000.0, 4001.0],
        })
        result = merge_forward_rows(old, new)
        self.assertEqual(len(result), 2)
        self.assertEqual(float(result.iloc[-1]["close"]), 4001.0)

    def test_merge_rejects_historical_revision(self) -> None:
        old = pd.DataFrame({"time": ["2026-07-24T10:00:00Z"], "close": [4000.0]})
        revised = pd.DataFrame({"time": ["2026-07-24T10:00:00Z"], "close": [4000.5]})
        with self.assertRaisesRegex(ValueError, "immutable"):
            merge_forward_rows(old, revised)

    def test_tick_costs_are_aggregated_by_minute(self) -> None:
        ticks = pd.DataFrame({
            "time_msc": [1784887200100, 1784887200200, 1784887260100],
            "bid": [4000.00, 4000.10, 4000.20],
            "ask": [4000.20, 4000.40, 4000.30],
        })
        result = aggregate_tick_costs(ticks)
        self.assertEqual(len(result), 2)
        self.assertEqual(int(result.iloc[0]["tick_count"]), 2)
        self.assertAlmostEqual(float(result.iloc[0]["spread_median"]), 0.25)
        self.assertAlmostEqual(float(result.iloc[1]["spread_p90"]), 0.10)

    def test_csv_time_serialization_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.csv"
            frame = pd.DataFrame({"time": ["2026-07-24T10:00:00Z"], "close": [4000.0]})
            _write_csv(frame, path)
            first = path.read_bytes()
            _write_csv(pd.read_csv(path), path)
            self.assertEqual(first, path.read_bytes())

    def test_readiness_does_not_unseal_small_forward_sample(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            symbol_folder = Path(folder) / "XAUUSD"
            symbol_folder.mkdir()
            (symbol_folder / "cohort.json").write_text(
                '{"anchor_utc":"2026-07-24T04:19:44+00:00"}', encoding="utf-8"
            )
            rows = pd.DataFrame({
                "time": ["2026-07-24T04:20:00Z", "2026-07-24T04:21:00Z"],
                "close": [4000.0, 4001.0],
            })
            costs = pd.DataFrame({
                "time": ["2026-07-24T04:20:00Z", "2026-07-24T04:21:00Z"],
                "spread_p90": [0.2, 0.3],
            })
            rows.to_csv(symbol_folder / "forward_M1.csv", index=False)
            costs.to_csv(symbol_folder / "forward_M1_costs.csv", index=False)
            report = forward_readiness(folder, "XAUUSD")
            self.assertFalse(report["ready"])
            self.assertTrue(report["sealed"])
            self.assertEqual(report["matched_minutes"], 2)


if __name__ == "__main__":
    unittest.main()
