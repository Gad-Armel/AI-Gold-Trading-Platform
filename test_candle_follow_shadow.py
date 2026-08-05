from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from config import scalping_settings
from models.scalping_state import ScalpingSnapshotState
from services.research.candle_follow_shadow import candle_follow_metrics, update_candle_follow_shadow


def snapshot(bid: float, ask: float, *, green: bool = True, minute: int = 1) -> ScalpingSnapshotState:
    previous_open = 4000.0
    previous_close = 4000.5 if green else 3999.5
    live_mid = (bid + ask) / 2
    live_open = live_mid - 0.5 if green else live_mid + 0.5
    candles = pd.DataFrame(
        [
            {"time": pd.Timestamp(f"2026-07-21 12:{minute:02d}:00"), "open": previous_open, "high": 4000.7, "low": 3999.3, "close": previous_close},
            {"time": pd.Timestamp(f"2026-07-21 12:{minute+1:02d}:00"), "open": live_open, "high": max(live_open, live_mid), "low": min(live_open, live_mid), "close": live_mid},
        ]
    )
    return ScalpingSnapshotState(
        symbol="XAUUSD", timestamp=datetime(2026, 7, 21, 12, minute+1, 30, tzinfo=timezone.utc), bid=bid, ask=ask,
        spread=ask-bid, mid=(bid+ask)/2, session="NEW_YORK",
        active_sessions=["NEW_YORK"], candles={"M1": candles},
        contract_size=100.0, quote_age_seconds=0.0,
    )


class CandleFollowShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patchers = [
            patch.object(scalping_settings, "SCALPING_CANDLE_FOLLOW_STATE_PATH", str(root / "state.json")),
            patch.object(scalping_settings, "SCALPING_CANDLE_FOLLOW_HISTORY_PATH", str(root / "history.jsonl")),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patchers):
            item.stop()
        self.temp.cleanup()

    def test_green_sells_red_buys_and_can_reenter_same_candle(self) -> None:
        opened = update_candle_follow_shadow(snapshot(4000.0, 4000.2, green=True))
        self.assertEqual(opened["action"], "OPEN")
        self.assertEqual(opened["open_trade"]["direction"], "SELL")

        closed = update_candle_follow_shadow(snapshot(3999.3, 3999.5, green=True))
        self.assertEqual(closed["action"], "CLOSE")
        self.assertAlmostEqual(closed["closed_record"]["final_profit_usd"], 0.4)

        same_candle = update_candle_follow_shadow(snapshot(3999.3, 3999.5, green=True))
        self.assertEqual(same_candle["action"], "OPEN")
        self.assertEqual(same_candle["open_trade"]["direction"], "SELL")
        # Close the re-entry before testing a red live candle.
        update_candle_follow_shadow(snapshot(3998.0, 3998.2, green=True))
        red = update_candle_follow_shadow(snapshot(4001.5, 4001.7, green=False, minute=2))
        self.assertEqual(red["action"], "OPEN")
        self.assertEqual(red["open_trade"]["direction"], "BUY")
        self.assertEqual(candle_follow_metrics()["trades"], 2)

    def test_maximum_hold_is_five_seconds(self) -> None:
        self.assertEqual(float(scalping_settings.SCALPING_CANDLE_FOLLOW_MAX_HOLD_SECONDS), 5.0)

    def test_target_is_forty_cents(self) -> None:
        self.assertAlmostEqual(float(scalping_settings.SCALPING_CANDLE_FOLLOW_TARGET_USD), 0.40)

    def test_benchmark_source_has_no_broker_order_call(self) -> None:
        source = Path(__file__).parent.joinpath("services/research/candle_follow_shadow.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(", source)

    def test_stale_closed_candle_does_not_open(self) -> None:
        stale = snapshot(4000.0, 4000.2)
        stale.timestamp = datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc)
        result = update_candle_follow_shadow(stale)
        self.assertEqual(result["action"], "STALE")
        self.assertIsNone(result["open_trade"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
