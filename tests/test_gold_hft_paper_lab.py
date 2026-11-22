import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import run_gold_consensus_bot


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gold_hft_paper_lab", ROOT / "tools" / "gold_hft_paper_lab.py")
LAB = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LAB
SPEC.loader.exec_module(LAB)


class GoldHftPaperLabTests(unittest.TestCase):
    def test_main_bot_replay_mode_does_not_require_trading_mode(self):
        with patch.object(sys, "argv", ["run_gold_consensus_bot.py", "--hft-paper-replay", "observed.npz"]):
            args = run_gold_consensus_bot._arguments()
        self.assertIsNone(args.mode)
        self.assertEqual(args.hft_paper_replay, Path("observed.npz"))

    def test_main_bot_replay_mode_rejects_demo_execution_flags(self):
        with patch.object(sys, "argv", [
            "run_gold_consensus_bot.py", "--hft-paper-replay", "observed.npz",
            "--mode", "demo", "--confirm", "CONFIRM",
        ]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                run_gold_consensus_bot._arguments()
        self.assertEqual(error.exception.code, 2)

    def test_reads_tick_probe_npz_schema_without_pickle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ticks.npz"
            np.savez(path, utc_time_msc=[1, 2], bid=[10.0, 10.1], ask=[10.1, 10.2])
            quotes = LAB.load_quotes(path)
        self.assertEqual(quotes, [LAB.Quote(1, 10.0, 10.1), LAB.Quote(2, 10.1, 10.2)])

    def test_rejects_nonchronological_ticks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ticks.npz"
            np.savez(path, utc_time_msc=[2, 1], bid=[10.0, 10.1], ask=[10.1, 10.2])
            with self.assertRaisesRegex(ValueError, "strictly increasing"):
                LAB.load_quotes(path)

    def test_paper_fill_waits_for_latency_and_crosses_the_spread(self):
        quotes = [
            LAB.Quote(1000, 100.00, 100.02),
            LAB.Quote(1100, 100.01, 100.03),
            LAB.Quote(1200, 100.02, 100.04),
            LAB.Quote(1300, 100.10, 100.12),
            LAB.Quote(1350, 100.11, 100.13),
            LAB.Quote(1400, 100.16, 100.18),
            LAB.Quote(1450, 100.18, 100.20),
        ]
        report = LAB.replay(
            quotes, lookback_ms=200, entry_threshold=0.05, max_spread=0.20,
            latency_ms=50, holding_ms=100, max_quote_gap_ms=500,
            reentry_cooldown_ms=500,
        )
        self.assertEqual(report["mode"], "PAPER_REPLAY_ONLY")
        self.assertEqual(report["paper_trades_closed"], 1)
        trade = report["trades"][0]
        self.assertEqual(trade["side"], "BUY")
        self.assertEqual(trade["entry_time_msc"], 1350)
        self.assertEqual(trade["entry_price"], 100.13)
        self.assertEqual(trade["exit_time_msc"], 1450)
        self.assertAlmostEqual(trade["gross_price_units"], 0.05)
        self.assertAlmostEqual(trade["estimated_net_price_units"], 0.05)
        self.assertTrue(report["limitations"])

    def test_assumed_fees_and_slippage_reduce_price_unit_result(self):
        quotes = [
            LAB.Quote(1000, 100.00, 100.02),
            LAB.Quote(1100, 100.01, 100.03),
            LAB.Quote(1200, 100.10, 100.12),
            LAB.Quote(1300, 100.12, 100.14),
            LAB.Quote(1400, 100.22, 100.24),
        ]
        report = LAB.replay(
            quotes, lookback_ms=100, entry_threshold=0.05, max_spread=0.20,
            latency_ms=0, holding_ms=100, max_quote_gap_ms=500,
            reentry_cooldown_ms=500, round_trip_cost_price=0.03,
            slippage_per_side_price=0.01,
        )
        self.assertEqual(report["paper_trades_closed"], 1)
        trade = report["trades"][0]
        self.assertAlmostEqual(trade["gross_price_units"], 0.06)
        self.assertAlmostEqual(trade["estimated_net_price_units"], 0.03)

    def test_hourly_entry_cap_blocks_additional_paper_entries(self):
        quotes = [
            LAB.Quote(1000, 100.00, 100.02),
            LAB.Quote(1100, 100.00, 100.02),
            LAB.Quote(1200, 100.20, 100.22),
            LAB.Quote(1300, 100.20, 100.22),
            LAB.Quote(1400, 100.30, 100.32),
            LAB.Quote(1500, 100.40, 100.42),
        ]
        report = LAB.replay(
            quotes, lookback_ms=100, entry_threshold=0.05, max_spread=0.20,
            latency_ms=0, holding_ms=100, max_quote_gap_ms=500,
            reentry_cooldown_ms=0, max_entries_per_hour=1,
        )
        self.assertEqual(len([quote for quote in report["trades"]]), 1)
        self.assertGreater(report["hourly_cap_rejections"], 0)

    def test_wide_spread_does_not_create_entry(self):
        quotes = [
            LAB.Quote(1000, 100.0, 100.8),
            LAB.Quote(1100, 100.1, 100.9),
            LAB.Quote(1200, 100.2, 101.0),
        ]
        report = LAB.replay(
            quotes, lookback_ms=100, entry_threshold=0.05, max_spread=0.2,
            latency_ms=0, holding_ms=100, max_quote_gap_ms=500,
        )
        self.assertEqual(report["paper_trades_closed"], 0)
        self.assertEqual(report["spread_rejections"], len(quotes))

    def test_wide_spread_at_simulated_fill_cancels_pending_entry(self):
        quotes = [
            LAB.Quote(1000, 100.0, 100.02),
            LAB.Quote(1100, 100.0, 100.02),
            LAB.Quote(1200, 100.2, 100.22),
            LAB.Quote(1300, 100.0, 100.8),
            LAB.Quote(1400, 100.0, 100.02),
        ]
        report = LAB.replay(
            quotes, lookback_ms=100, entry_threshold=0.05, max_spread=0.2,
            latency_ms=50, holding_ms=100, max_quote_gap_ms=500,
            reentry_cooldown_ms=500,
        )
        self.assertEqual(report["paper_trades_closed"], 0)
        self.assertIsNone(report["open_paper_position"])
        self.assertIsNone(report["pending_paper_entry"])
        self.assertGreaterEqual(report["spread_rejections"], 1)

    def test_quote_gap_resets_signal_warmup_and_cancels_pending_entry(self):
        quotes = [
            LAB.Quote(1000, 100.0, 100.02),
            LAB.Quote(1100, 100.0, 100.02),
            LAB.Quote(1200, 100.2, 100.22),
            LAB.Quote(2000, 100.3, 100.32),
            LAB.Quote(2100, 100.3, 100.32),
        ]
        report = LAB.replay(
            quotes, lookback_ms=100, entry_threshold=0.05, max_spread=0.2,
            latency_ms=1000, holding_ms=100, max_quote_gap_ms=500,
            reentry_cooldown_ms=500,
        )
        self.assertEqual(report["gaps_over_limit"], 1)
        self.assertEqual(report["stale_entry_cancellations"], 1)
        self.assertIsNone(report["open_paper_position"])

    def test_quote_gap_with_open_position_marks_settlement_unresolved(self):
        quotes = [
            LAB.Quote(1000, 100.0, 100.02),
            LAB.Quote(1100, 100.0, 100.02),
            LAB.Quote(1200, 100.2, 100.22),
            LAB.Quote(1300, 100.2, 100.22),
            LAB.Quote(2200, 100.3, 100.32),
            LAB.Quote(2300, 100.3, 100.32),
        ]
        report = LAB.replay(
            quotes, lookback_ms=100, entry_threshold=0.05, max_spread=0.2,
            latency_ms=0, holding_ms=100, max_quote_gap_ms=500,
            reentry_cooldown_ms=500,
        )
        self.assertTrue(report["unresolved_position_after_data_gap"])
        self.assertEqual(report["paper_trades_closed"], 0)
        self.assertIsNotNone(report["open_paper_position"])

    def test_replay_rejects_invalid_timing(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            LAB.replay(
                [LAB.Quote(1, 10.0, 10.1), LAB.Quote(2, 10.0, 10.1)],
                lookback_ms=0,
            )


if __name__ == "__main__":
    unittest.main()
