from __future__ import annotations

import tempfile
import unittest
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from services.market_data import free_macro_context


def _frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=len(values), freq="D", tz="UTC"),
        "value": values,
    })


class FreeMacroContextTests(unittest.TestCase):
    def test_latest_metrics_include_smoothed_short_versus_medium_trend(self) -> None:
        metrics = free_macro_context._latest_metrics(_frame([float(value) for value in range(1, 21)]))
        self.assertEqual(metrics["mean_5"], 18.0)
        self.assertEqual(metrics["mean_20"], 10.5)
        self.assertEqual(metrics["mean_5_minus_20"], 7.5)

    def test_configured_key_uses_official_api_and_keeps_series_independent(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_fetch(series_id: str, api_key: str, timeout: float = 8.0) -> pd.DataFrame:
            calls.append((series_id, api_key))
            if series_id == "BROKEN":
                raise TimeoutError("source unavailable")
            return _frame([100, 101, 102, 103, 104, 105])

        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "macro.json"
            with (
                patch.object(free_macro_context, "DEFAULT_SERIES", {"ok": "GOOD", "bad": "BROKEN"}),
                patch.object(free_macro_context, "_fetch_api", side_effect=fake_fetch),
                patch.object(free_macro_context, "_fetch_csv", return_value=_frame([90, 91, 92, 93, 94, 95])) as csv_fetch,
            ):
                result = free_macro_context.build_free_macro_context(
                    cache_path=str(cache), api_key="configured-key", max_cache_age_seconds=0,
                    include_world_bank=False,
                )

        self.assertEqual(sorted(calls), [("BROKEN", "configured-key"), ("GOOD", "configured-key")])
        csv_fetch.assert_called_once_with("BROKEN", timeout=8.0)
        self.assertIn("ok", result["observations"])
        self.assertIn("bad", result["observations"])
        self.assertNotIn("bad", result["errors"])
        self.assertIn("bad", result["warnings"])
        self.assertEqual(result["observations"]["bad"]["retrieval_method"], "FRED_GRAPH_CSV_FALLBACK")
        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "FRED official observations API")

    def test_no_key_falls_back_to_graph_csv(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "macro.json"
            with (
                patch.object(free_macro_context, "DEFAULT_SERIES", {"one": "SERIES"}),
                patch.object(free_macro_context, "_fetch_csv", return_value=_frame([1, 2, 3, 4, 5, 6])) as csv_fetch,
                patch.object(free_macro_context, "_fetch_api") as api_fetch,
            ):
                result = free_macro_context.build_free_macro_context(
                    cache_path=str(cache), api_key="", max_cache_age_seconds=0,
                    include_world_bank=False,
                )

        csv_fetch.assert_called_once()
        api_fetch.assert_not_called()
        self.assertEqual(result["source"], "FRED graph CSV current observations")

    def test_failed_refresh_retains_last_valid_observation_without_refreshing_its_date(self) -> None:
        observed = "2026-09-01T00:00:00+00:00"
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "macro.json"
            cache.write_text(json.dumps({
                "generated_at": "2026-09-01T00:00:00+00:00",
                "observations": {"kept": {"value": 42.0, "observation_time": observed}},
            }), encoding="utf-8")
            with (
                patch.object(free_macro_context, "DEFAULT_SERIES", {"kept": "SERIES"}),
                patch.object(free_macro_context, "_fetch_api", side_effect=TimeoutError("api")),
                patch.object(free_macro_context, "_fetch_csv", side_effect=TimeoutError("csv")),
            ):
                result = free_macro_context.build_free_macro_context(
                    cache_path=str(cache), api_key="configured-key", max_cache_age_seconds=0,
                    include_world_bank=False,
                )
        kept = result["observations"]["kept"]
        self.assertEqual(kept["value"], 42.0)
        self.assertEqual(kept["observation_time"], observed)
        self.assertEqual(kept["retrieval_method"], "STALE_CACHE_FALLBACK")
        self.assertIn("kept", result["errors"])

    def test_world_bank_global_growth_parser_preserves_forecast_context(self) -> None:
        payload = {
            "lastupdated": "2026-06-11",
            "source": {"data": [
                {"variable": [{"concept": "Time", "value": "2025"}], "value": 2.9},
                {"variable": [{"concept": "Time", "value": "2026"}], "value": 2.5},
                {"variable": [{"concept": "Time", "value": "2027"}], "value": 2.8},
            ]},
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps(payload).encode("utf-8")

        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        with patch.object(free_macro_context, "urlopen", return_value=Response()):
            result = free_macro_context._fetch_world_bank_global_growth(now=now)
        self.assertEqual(result["forecast_year"], 2026)
        self.assertEqual(result["value"], 2.5)
        self.assertAlmostEqual(result["change_from_previous_year"], -0.4)
        self.assertEqual(result["next_year_growth"], 2.8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
