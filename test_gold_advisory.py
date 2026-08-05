from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from models.scalping_state import ScalpingSnapshotState
from services.research.gold_advisory import build_gold_advisory
from run_gold_advisor import _print


def frame(up: bool = True, rows: int = 100) -> pd.DataFrame:
    sign = 1.0 if up else -1.0
    closes = [4000.0 + sign * index * 0.10 for index in range(rows)]
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=rows, freq="min", tz="UTC"),
        "open": [value-sign*0.04 for value in closes], "high": [value+0.08 for value in closes],
        "low": [value-0.08 for value in closes], "close": closes, "tick_volume": [100]*rows,
    })


def snapshot(*, spread: float = 0.15) -> ScalpingSnapshotState:
    candles={name:frame(True) for name in ("M1","M5","M15","H1","H4")}
    return ScalpingSnapshotState(symbol="XAUUSD",timestamp=datetime.now(timezone.utc),bid=4009.80,ask=4009.80+spread,
        spread=spread,mid=4009.80+spread/2,session="London",active_sessions=["London"],candles=candles,
        contract_size=100.0,point=0.01,quote_age_seconds=0.1,system_timestamp=datetime.now(timezone.utc))


class GoldAdvisoryTests(unittest.TestCase):
    @patch("services.research.gold_advisory.build_v6_market_structure", return_value={"direction":"BUY"})
    @patch("services.research.gold_advisory.build_verified_market_context", return_value={"vwap_distance_atr":0.4})
    def test_aligned_market_produces_levels(self, _context, _structure) -> None:
        report=build_gold_advisory(snapshot())
        self.assertEqual(report["overall"],"BUY")
        self.assertFalse(report["execution_enabled"])
        for item in report["horizons"].values():
            self.assertEqual(item["action"],"BUY")
            self.assertEqual(item["bias"],"BUY")
            self.assertLess(item["levels"]["sl"],item["levels"]["entry_reference"])
            self.assertGreater(item["levels"]["tp3"],item["levels"]["tp1"])
            self.assertIsNone(item["calibrated_probability"])

    @patch("services.research.gold_advisory.build_v6_market_structure", return_value={"direction":"BUY"})
    @patch("services.research.gold_advisory.build_verified_market_context", return_value={"vwap_distance_atr":0.4})
    def test_wide_spread_forces_wait(self, _context, _structure) -> None:
        report=build_gold_advisory(snapshot(spread=.55))
        self.assertEqual(report["overall"],"WAIT")
        self.assertTrue(all(item["action"]=="WAIT" for item in report["horizons"].values()))
        self.assertTrue(all(item["bias"]=="BUY" for item in report["horizons"].values()))

    def test_runner_has_no_order_call(self) -> None:
        source=Path("run_gold_advisor.py").read_text(encoding="utf-8")+Path("services/research/gold_advisory.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(",source)

    @patch("services.research.gold_advisory.build_v6_market_structure", return_value={"direction":"BUY"})
    @patch("services.research.gold_advisory.build_verified_market_context", return_value={"vwap_distance_atr":8.93})
    def test_wait_dashboard_is_clear(self, _context, _structure) -> None:
        report=build_gold_advisory(snapshot())
        output=StringIO()
        with redirect_stdout(output):
            _print(report)
        rendered=output.getvalue()
        self.assertIn("DECISION   : WAIT - NO ENTRY",rendered)
        self.assertIn("WHY THERE IS NO ENTRY",rendered)
        self.assertIn("Do not chase the move",rendered)
        self.assertIn("SCALP",rendered)
        self.assertIn("Analysis completed (UTC)",rendered)
        self.assertIn("VALID WINDOW (UTC)",rendered)
        self.assertIn("no longer valid",rendered)
        self.assertIn("->",rendered)


if __name__=="__main__": unittest.main(verbosity=2)
