from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen, Request
from unittest.mock import patch

from services.dashboard.gold_unified_web import (
    BridgeWriteError,
    classify_consensus_status,
    create_unified_server,
    read_unified_config,
    save_unified_config,
    _compact_consensus_status,
    _compact_native_status,
    _compact_advisor_status,
)
from services.dashboard.gold_scalp_support import consensus_is_running


class UnifiedDashboardTests(unittest.TestCase):
    def test_compact_consensus_payload_drops_large_research_trees(self):
        raw = {"status": "RUNNING", "account": {"equity": 100}, "lanes": {"SCALP": {
            "decision": {"direction": "BUY", "contributors": [{"raw": "x" * 10000}]},
            "closed_trades": [{"ticket": 1}] * 40, "positions": [],
        }}}
        payload = _compact_consensus_status(raw)
        self.assertNotIn("contributors", payload["lanes"]["SCALP"]["decision"])
        self.assertEqual(len(payload["lanes"]["SCALP"]["closed_trades"]), 30)
        self.assertLess(len(json.dumps(payload)), 5000)

    def test_compact_status_readers_limit_historical_exports(self):
        native = _compact_native_status({"state": "stopped", "snapshot": {
            "candles": [{"close": 1}] * 500, "deals": [{"ticket": 1}] * 50,
            "positions": [], "account": {"equity": 100}, "large": "x" * 10000,
        }})
        self.assertEqual(len(native["snapshot"]["candles"]), 120)
        self.assertEqual(len(native["snapshot"]["deals"]), 30)
        advisor = _compact_advisor_status({"state": "live", "report": {
            "symbol": "XAUUSD", "views": {"raw": "x" * 10000},
            "horizons": {"SCALP": {"action": "BUY", "levels": {}, "raw": "x" * 10000}},
        }})
        self.assertNotIn("views", advisor["report"])
        self.assertNotIn("raw", advisor["report"]["horizons"]["SCALP"])

    def test_main_consensus_heartbeat_can_supervise_advisor(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            now = 1_800_000_000.0
            path.write_text(json.dumps({
                "status": "RUNNING",
                "updated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            }), encoding="utf-8")
            self.assertTrue(consensus_is_running(path, now=now))
            self.assertFalse(consensus_is_running(path, now=now + 16))

    def test_unified_page_and_api_are_available(self):
        with tempfile.TemporaryDirectory() as folder:
            server = create_unified_server(Path(folder), 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                root = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(root + "/", timeout=3) as response:
                    body = response.read()
                    self.assertIn(b"Gold Unified Command Center", body)
                    self.assertIn(b"New-entry schedule (UTC)", body)
                    self.assertIn(b"Live", body)
                    self.assertIn(b"DEMO ONLY", body)
                    self.assertIn(b"Fast-loop telemetry", body)
                    self.assertIn(b"Adaptive exit", body)
                    self.assertIn(b"Full ${esc(name)} decision and exit telemetry", body)
                with urlopen(root + "/api/unified", timeout=3) as response:
                    payload = json.load(response)
                    self.assertIn("native", payload)
                    self.assertIn("consensus", payload)
                    self.assertIn("advisor", payload)
                    self.assertIn("manual", payload)
                    self.assertIn("vfinal", payload)
                with urlopen(root + "/health", timeout=3) as response:
                    self.assertEqual(
                        json.load(response),
                        {"ok": True, "dashboard": "aurum-gold-unified"},
                    )
                request = Request(root + "/api/config", data=json.dumps({
                    "symbol": "XAUUSD", "mode": "demo", "timeframe": "M1",
                    "execution_enabled": True, "schedule_mode": "exclude_window",
                    "blocked_start_utc": 22, "blocked_end_utc": 23,
                }).encode(), method="POST", headers={
                    "Content-Type": "application/json",
                    "Origin": root,
                })
                with patch("services.dashboard.gold_unified_web.CONFIG_PATH", Path(folder) / "config.json"):
                    with urlopen(request, timeout=3) as response:
                        config = json.load(response)
                        self.assertEqual(config["symbol"], "XAUUSD")
                        self.assertEqual(config["mode"], "demo")
                        self.assertEqual(config["bridge_write_state"], "written")
                        self.assertEqual(config["schedule_mode"], "exclude_window")
                        self.assertEqual(config["blocked_start_utc"], 22)
                        self.assertEqual(config["blocked_end_utc"], 23)
                self.assertEqual(
                    (Path(folder) / "unified_config.csv").read_text(encoding="ascii").strip(),
                    "GOLD_UNIFIED_V2;XAUUSD;demo;M1;enabled;exclude_window;22;23;END",
                )
            finally:
                server.shutdown()
                server.server_close()

    def test_consensus_status_requires_a_fresh_running_heartbeat(self):
        now = 1_800_000_000.0
        fresh = classify_consensus_status(
            {
                "status": "RUNNING",
                "updated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            },
            now,
        )
        self.assertEqual(fresh["state"], "running")

        stale = classify_consensus_status(
            {
                "status": "RUNNING",
                "updated_at": datetime.fromtimestamp(now - 11, timezone.utc).isoformat(),
            },
            now,
        )
        self.assertEqual(stale["state"], "stale")
        self.assertIn("cached values are not live", stale["message"])

        stopped = classify_consensus_status(
            {"status": "STOPPED", "updated_at": datetime.fromtimestamp(now, timezone.utc).isoformat()},
            now,
        )
        self.assertEqual(stopped["state"], "stopped")

    def test_bridge_write_failure_is_persisted_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / "config.json"
            not_a_directory = Path(folder) / "file"
            not_a_directory.write_text("block mkdir", encoding="ascii")
            with patch("services.dashboard.gold_unified_web.CONFIG_PATH", config_path):
                with self.assertRaises(BridgeWriteError):
                    save_unified_config({
                        "symbol": "XAUUSD", "mode": "demo", "timeframe": "M1",
                        "execution_enabled": True,
                    }, not_a_directory / "GoldScalp")
                config = read_unified_config()
            self.assertEqual(config["bridge_write_state"], "failed")
            self.assertTrue(config["bridge_write_error"])

    def test_schedule_rejects_invalid_hours(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("services.dashboard.gold_unified_web.CONFIG_PATH", Path(folder) / "config.json"):
                with self.assertRaisesRegex(ValueError, "must differ"):
                    save_unified_config({
                        "symbol": "XAUUSD", "mode": "demo", "timeframe": "M1",
                        "execution_enabled": True, "schedule_mode": "exclude_window",
                        "blocked_start_utc": 22, "blocked_end_utc": 22,
                    }, Path(folder) / "feed")
                with self.assertRaisesRegex(ValueError, "integers"):
                    save_unified_config({
                        "symbol": "XAUUSD", "mode": "demo", "timeframe": "M1",
                        "execution_enabled": True, "schedule_mode": "exclude_window",
                        "blocked_start_utc": 22.5, "blocked_end_utc": 23,
                    }, Path(folder) / "feed")

    def test_live_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("services.dashboard.gold_unified_web.CONFIG_PATH", Path(folder) / "config.json"):
                with self.assertRaisesRegex(ValueError, "observe or demo"):
                    save_unified_config({
                        "symbol": "XAUUSD", "mode": "live", "timeframe": "M1",
                        "execution_enabled": True,
                    }, Path(folder) / "feed")

    def test_bridge_write_failure_returns_http_503(self):
        with tempfile.TemporaryDirectory() as folder:
            server = create_unified_server(Path(folder), 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            original_replace = os.replace

            def fail_bridge_replace(source, destination):
                if Path(destination).name == "unified_config.csv":
                    raise PermissionError("bridge unavailable")
                original_replace(source, destination)

            try:
                root = f"http://127.0.0.1:{server.server_address[1]}"
                request = Request(root + "/api/config", data=json.dumps({
                    "symbol": "XAUUSD", "mode": "demo", "timeframe": "M1",
                    "execution_enabled": True,
                }).encode(), method="POST", headers={
                    "Content-Type": "application/json",
                    "Origin": root,
                })
                with patch("services.dashboard.gold_unified_web.CONFIG_PATH", Path(folder) / "config.json"):
                    with patch("services.dashboard.gold_unified_web.os.replace", side_effect=fail_bridge_replace):
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(request, timeout=3)
                self.assertEqual(raised.exception.code, 503)
                body = json.load(raised.exception)
                self.assertIn("bridge unavailable", body["error"])
                self.assertEqual(body["config"]["bridge_write_state"], "failed")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
