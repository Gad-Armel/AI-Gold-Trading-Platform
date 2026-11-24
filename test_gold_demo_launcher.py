from __future__ import annotations

import unittest
from types import SimpleNamespace
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.launch_gold_demo import confirmation_matches, find_mt5_terminal, is_demo_account


class GoldDemoLauncherTests(unittest.TestCase):
    def test_only_demo_accounts_pass_preflight(self):
        demo_mode = 0
        self.assertTrue(is_demo_account(SimpleNamespace(trade_mode=demo_mode), demo_mode))
        self.assertFalse(is_demo_account(SimpleNamespace(trade_mode=2), demo_mode))
        self.assertFalse(is_demo_account(None, demo_mode))

    def test_confirmation_must_match_configured_phrase(self):
        self.assertTrue(confirmation_matches("confirm demo", "confirm demo"))
        self.assertFalse(confirmation_matches("confirm demo", "CONFIRM DEMO"))
        self.assertFalse(confirmation_matches("", "anything"))

    def test_explicit_mt5_terminal_override_must_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            terminal = Path(folder) / "terminal64.exe"
            terminal.write_bytes(b"fixture")
            with patch.dict(os.environ, {"GOLD_MT5_TERMINAL": str(terminal)}):
                self.assertEqual(find_mt5_terminal(), terminal)
            with patch.dict(os.environ, {"GOLD_MT5_TERMINAL": str(terminal) + ".missing"}):
                with self.assertRaisesRegex(RuntimeError, "does not point to a file"):
                    find_mt5_terminal()


if __name__ == "__main__":
    unittest.main()
