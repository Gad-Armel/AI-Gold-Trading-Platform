"""Dashboard transport regressions: stale data, account isolation and HTTP exposure."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.dashboard.gold_scalp_web import create_server, read_status


def sample():
    return {"schema": 1, "connected": True, "stopped": False, "account": {}, "kpi": {},
            "market": {}, "filters": {}, "risk": {}, "positions": [], "candles": [], "deals": [], "events": []}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "dashboard_GS_ACCOUNT_1_100_92563101.json"

    def publish(self, data=None, when=1000):
        self.path.write_text(json.dumps(sample() if data is None else data), encoding="utf-8")
        os.utime(self.path, (when, when))

    def test_missing_feed_is_waiting_not_live(self):
        self.assertEqual(read_status(self.directory)["state"], "waiting")

    def test_fresh_connected_ea_is_live(self):
        self.publish()
        result = read_status(self.directory, now=1002)
        self.assertEqual(result["state"], "live")
        self.assertEqual(result["age_seconds"], 2)

    def test_fresh_heartbeat_does_not_hide_disconnection(self):
        data = sample(); data["connected"] = False; self.publish(data)
        self.assertEqual(read_status(self.directory, now=1001)["state"], "disconnected")

    def test_stopped_ea_preserves_last_snapshot_as_stopped(self):
        data = sample(); data["stopped"] = True; self.publish(data)
        self.assertEqual(read_status(self.directory, now=1001)["state"], "stopped")

    def test_stale_snapshot_is_never_live(self):
        self.publish()
        self.assertEqual(read_status(self.directory, now=1006)["state"], "stale")

    def test_future_clock_is_not_live(self):
        self.publish(when=1020)
        self.assertEqual(read_status(self.directory, now=1000)["state"], "stale")

    def test_multiple_accounts_require_explicit_selection(self):
        self.publish()
        other = self.directory / "dashboard_GS_ACCOUNT_2_200_92563101.json"
        other.write_bytes(self.path.read_bytes())
        self.assertEqual(read_status(self.directory, now=1001)["state"], "choose")
        self.assertEqual(read_status(self.directory, self.path.name, now=1001)["state"], "live")

    def test_selected_account_never_falls_back_to_other(self):
        self.publish()
        result = read_status(self.directory, "dashboard_missing.json", now=1001)
        self.assertEqual(result["state"], "waiting")
        self.assertIsNone(result["snapshot"])

    def test_path_traversal_rejected(self):
        self.publish()
        self.assertEqual(read_status(self.directory, "../secret.json")["state"], "error")

    def test_truncated_json_is_error_not_live(self):
        self.path.write_text('{"schema":1', encoding="utf-8")
        self.assertEqual(read_status(self.directory)["state"], "error")

    def test_nan_and_overflow_rejected(self):
        for bad in ("NaN", "Infinity", "1e9999"):
            self.path.write_text(json.dumps(sample())[:-1] + ',"bad":' + bad + '}', encoding="utf-8")
            self.assertEqual(read_status(self.directory)["state"], "error")

    def test_oversized_snapshot_rejected(self):
        self.path.write_bytes(b" " * 1_000_001)
        self.assertEqual(read_status(self.directory)["state"], "error")

    def test_wrong_shape_rejected(self):
        data = sample(); data["positions"] = [None]; self.publish(data)
        self.assertEqual(read_status(self.directory)["state"], "error")

    def test_malformed_calendar_cannot_appear_live(self):
        for macro in ([], {"events": {}}, {"events": [None]}, {"events": [{}]*65}):
            data = sample(); data["macro"] = macro; self.publish(data)
            self.assertEqual(read_status(self.directory, now=1001)["state"], "error")

    def test_calendar_preserves_unknown_actual_and_zero_forecast(self):
        data = sample(); data["macro"] = {"fresh": True, "events": [{"actual": "NA", "forecast": "0.0"}]}; self.publish(data)
        result = read_status(self.directory, now=1001)
        self.assertEqual(result["state"], "live")
        self.assertEqual(result["snapshot"]["macro"]["events"][0], {"actual": "NA", "forecast": "0.0"})

    def test_unicode_bom_round_trip(self):
        data = sample(); data["status"] = 'Prix "XAU" / clôture\nattente'
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
        self.assertEqual(read_status(self.directory)["snapshot"]["status"], data["status"])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manual_report = Path(self.temp.name) / "manual-report.json"
        self.server = create_server(Path(self.temp.name), 0, manual_scalp_report=self.manual_report)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_local_assets_and_empty_status(self):
        for path in ("/", "/app.js", "/style.css", "/api/status", "/api/manual-scalp"):
            with urlopen(self.url + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
                if path == "/api/status":
                    self.assertEqual(json.load(response)["state"], "waiting")
                if path == "/api/manual-scalp":
                    self.assertEqual(json.load(response)["state"], "waiting")

    def test_no_file_browser_or_trade_endpoint(self):
        for path in ("/.env", "/../run_gold_advisor.py", "/api/trade"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url + path, timeout=3)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url + "/api/status", method="POST", data=b"{}"), timeout=3)
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_manual_report_route_and_main_panel(self):
        now = datetime.now(timezone.utc)
        report = {
            "symbol": "XAUUSD", "generated_at": now.isoformat(),
            "valid_until": (now + timedelta(seconds=15)).isoformat(),
            "action": "WAIT", "bias": "WAIT", "directional_evidence_score": 0,
            "quote": {"bid": 2500.0, "ask": 2500.02, "spread": 0.02},
            "scenario_levels": {}, "reports": {
                "candle_action": "WAIT", "candle_score": 0,
                "tick_action": "WAIT", "tick_score": 0,
            },
            "reasons": [], "blocks": ["No confirmed direction."],
            "execution_enabled": False, "orders_sent": False,
        }
        self.manual_report.write_text(json.dumps(report), encoding="utf-8")
        with urlopen(self.url + "/api/manual-scalp", timeout=3) as response:
            self.assertEqual(json.load(response)["state"], "live")
        with urlopen(self.url + "/", timeout=3) as response:
            self.assertIn(b"Manual scalp analysis", response.read())

    def test_rebinding_host_rejected(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url + "/api/status", headers={"Host": "external.example"}), timeout=3)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_second_dashboard_cannot_share_the_port(self):
        with self.assertRaises(OSError):
            other = create_server(Path(self.temp.name), self.server.server_port)
            other.server_close()


if __name__ == "__main__":
    unittest.main()
