from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState
from services.research.medium_horizon_shadow import analyze_medium_horizon, update_medium_horizon_shadow


def _frame(direction: str, *, end: str, periods: int = 180, freq: str = "15min") -> pd.DataFrame:
    step = 0.18 if direction == "BUY" else -0.18
    closes = [4000.0 + index * step for index in range(periods)]
    rows = []
    times = pd.date_range(end=end, periods=periods, freq=freq)
    for stamp, close in zip(times, closes):
        opened = close - step * 0.5
        rows.append({"time": stamp, "open": opened, "high": max(opened, close) + 0.12, "low": min(opened, close) - 0.12, "close": close})
    return pd.DataFrame(rows)


def snapshot(direction: str = "BUY", *, bid: float | None = None, ask: float | None = None, minute: int = 0) -> ScalpingSnapshotState:
    m15 = _frame(direction, end=f"2026-07-24 12:{minute:02d}:00", periods=180, freq="15min")
    h1 = _frame(direction, end="2026-07-24 12:00:00", periods=180, freq="1h")
    h4 = _frame(direction, end="2026-07-24 12:00:00", periods=180, freq="4h")
    midpoint = float(h1.iloc[-2]["close"])
    bid = midpoint - 0.10 if bid is None else bid
    ask = midpoint + 0.10 if ask is None else ask
    return ScalpingSnapshotState(
        symbol="XAUUSD", timestamp=datetime(2026, 7, 24, 12, minute, tzinfo=timezone.utc),
        bid=bid, ask=ask, spread=ask-bid, mid=(ask+bid)/2, session="NEW_YORK",
        active_sessions=["NEW_YORK"], candles={"M15": m15, "H1": h1, "H4": h4},
        contract_size=100.0, quote_age_seconds=0.0,
    )


class MediumHorizonShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patchers = [
            patch.object(scalping_settings, "SCALPING_MEDIUM_STATE_PATH", str(root / "state.json")),
            patch.object(scalping_settings, "SCALPING_MEDIUM_HISTORY_PATH", str(root / "history.jsonl")),
            patch.object(scalping_settings, "SCALPING_MEDIUM_ENTRY_ENABLED", True),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patchers):
            item.stop()
        self.temp.cleanup()

    def test_four_views_are_derived_from_closed_broker_bars(self) -> None:
        result = analyze_medium_horizon(snapshot())
        self.assertEqual(set(result["views"]), {"M45", "H1", "H2", "H4"})
        self.assertEqual(result["direction"], "BUY")
        self.assertGreaterEqual(result["buy_votes"], 3)

    def test_direction_episode_must_rearm_before_another_entry(self) -> None:
        first = update_medium_horizon_shadow(snapshot(minute=0))
        self.assertEqual(first["action"], "OPEN")
        duplicate = update_medium_horizon_shadow(snapshot(minute=0))
        self.assertIsNone(duplicate["opened"])
        second = update_medium_horizon_shadow(snapshot(minute=15))
        self.assertIsNone(second["opened"])
        self.assertTrue(any("episode already entered" in item for item in second["block_reasons"]))

    def test_wide_spread_blocks_entry(self) -> None:
        item = snapshot()
        item.bid, item.ask, item.spread = item.mid - 0.2, item.mid + 0.2, 0.4
        result = update_medium_horizon_shadow(item)
        self.assertIsNone(result["opened"])
        self.assertIn("spread above medium-model ceiling", result["block_reasons"])

    def test_verified_news_and_available_opposing_usd_context_veto_entries(self) -> None:
        news = update_medium_horizon_shadow(
            snapshot(),
            news_risk={"allowed": False, "block_reasons": ["verified FOMC window"]},
        )
        self.assertIsNone(news["opened"])
        self.assertIn("verified FOMC window", news["block_reasons"])

        opposing = update_medium_horizon_shadow(
            snapshot(minute=15),
            cross_market={"status": "OK", "gold_bias": "SELL"},
        )
        self.assertIsNone(opposing["opened"])
        self.assertTrue(any("USD-pressure" in item for item in opposing["block_reasons"]))

    def test_unavailable_external_context_fails_neutral_not_blocked(self) -> None:
        result = update_medium_horizon_shadow(
            snapshot(),
            news_risk={"allowed": True},
            cross_market={"status": "INSUFFICIENT_DATA", "gold_bias": "NEUTRAL"},
        )
        self.assertIsNotNone(result["opened"])

    def test_target_and_stop_are_explicit(self) -> None:
        result = update_medium_horizon_shadow(snapshot())
        self.assertAlmostEqual(result["opened"]["target_profit_usd"], 1.50)
        self.assertAlmostEqual(result["opened"]["hard_stop_usd"], 1.80)

    def test_source_cannot_send_broker_orders(self) -> None:
        source = Path(__file__).parent.joinpath("services/research/medium_horizon_shadow.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(", source)
        self.assertNotIn("services.execution", source)

    def test_failed_research_gate_blocks_entries_by_default(self) -> None:
        with patch.object(scalping_settings, "SCALPING_MEDIUM_ENTRY_ENABLED", False):
            result = update_medium_horizon_shadow(snapshot())
        self.assertIsNone(result["opened"])
        self.assertTrue(any("failed historical validation" in item for item in result["block_reasons"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
