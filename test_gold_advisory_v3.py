from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from services.research.gold_advisory_v3 import build_gold_advisory_v3, _tick_frame, _window


class FakeTickMT5:
    COPY_TICKS_ALL = -1
    BOOK_TYPE_BUY = 2
    BOOK_TYPE_SELL = 1

    def __init__(self, *, upward: bool = True, stale: bool = False) -> None:
        now = datetime.now(timezone.utc).timestamp() - (10 if stale else 0)
        count = 1900
        times = np.linspace(now - 919, now, count)
        sign = 1.0 if upward else -1.0
        mids = 4000.0 + sign * np.linspace(0.0, 9.5, count)
        self.rows = np.zeros(count, dtype=[("time", "i8"), ("time_msc", "i8"), ("bid", "f8"), ("ask", "f8")])
        self.rows["time"] = times.astype(int); self.rows["time_msc"] = (times * 1000).astype(np.int64)
        self.rows["bid"] = mids - 0.1; self.rows["ask"] = mids + 0.1
        self.tick = SimpleNamespace(bid=float(self.rows["bid"][-1]), ask=float(self.rows["ask"][-1]))

    def copy_ticks_from(self, *_args): return self.rows
    def symbol_info_tick(self, _symbol): return self.tick
    def market_book_add(self, _symbol): return True
    def market_book_get(self, _symbol):
        return (SimpleNamespace(type=2, volume_dbl=12.0), SimpleNamespace(type=1, volume_dbl=8.0))
    def market_book_release(self, _symbol): return True


class GoldAdvisoryV3Tests(unittest.TestCase):
    def setUp(self):
        clock_patch=patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS',0)
        clock_patch.start();self.addCleanup(clock_patch.stop)
    def test_upward_tick_pressure_produces_buy_horizons(self) -> None:
        report = build_gold_advisory_v3(FakeTickMT5(upward=True))
        self.assertEqual(report["overall"], "BUY")
        self.assertGreater(report["tick_count"], 1000)
        self.assertTrue(report["market_depth"]["available"])
        self.assertTrue(all(item["bias"] == "BUY" for item in report["horizons"].values()))
        # This sparse fixture has insufficient 1-second data for SCALP action.
        self.assertEqual(report['horizons']['SCALP']['action'], 'WAIT')
        self.assertTrue(report['horizons']['SCALP']['blocks'])

    def test_downward_tick_pressure_produces_sell_horizons(self) -> None:
        report = build_gold_advisory_v3(FakeTickMT5(upward=False))
        self.assertEqual(report["overall"], "SELL")
        self.assertTrue(all(item["bias"] == "SELL" for item in report["horizons"].values()))

    def test_stale_tick_flow_forces_wait(self) -> None:
        report = build_gold_advisory_v3(FakeTickMT5(stale=True))
        self.assertEqual(report["overall"], "WAIT")
        self.assertTrue(all(item["action"] == "WAIT" for item in report["horizons"].values()))

    def test_v3_is_read_only(self) -> None:
        source = Path("services/research/gold_advisory_v3.py").read_text(encoding="utf-8")
        self.assertNotIn("order_send(", source)

    def test_trade_volume_is_not_depth_and_future_ticks_cannot_vote(self):
        mt5 = FakeTickMT5()
        frame = _tick_frame(mt5.rows)
        frame['volume'] = 10; frame['volume_real'] = 10.5
        now = float(frame.timestamp.iloc[-1])
        self.assertFalse(_window(frame, 60, now)['microprice_available'])
        self.assertEqual(_window(frame, 60, now-2000)['ticks'], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
