from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import urlopen

from services.dashboard.gold_advisor_web import read_advisor
from services.dashboard.gold_scalp_web import create_server


def report():
    start = datetime(2026, 9, 29, 23, 58, tzinfo=timezone.utc)
    data = dict(generated_at=start.isoformat(), symbol="XAUUSD", bid=4100, ask=4100.3,
                spread=0.3, overall="WAIT", session="London", horizons={})
    for name, minutes in (("SCALP", 5), ("INTRADAY", 30), ("SWING", 120)):
        data["horizons"][name] = dict(action="WAIT", bias="SELL", directional_score=72,
            valid_for_minutes=minutes, review_at=(start+timedelta(minutes=1)).isoformat(),
            valid_until=(start+timedelta(minutes=minutes)).isoformat(),
            reasons=["Closed-bar evidence"], blocks=["Spread too high"], levels={})
    return data


class AdvisorWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "advisor.json"
        self.data = report()
        self.now = datetime.fromisoformat(self.data["generated_at"]).timestamp()

    def read(self, age=0):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return read_advisor(self.path, self.now + age)

    def test_original_analysis_is_preserved_across_midnight(self):
        before = json.dumps(self.data)
        state = self.read(15)
        self.assertEqual(state["state"], "live")
        self.assertEqual(state["report"], self.data)
        self.assertEqual(self.path.read_text(), before)
        self.assertTrue(state["report"]["horizons"]["SCALP"]["valid_until"].startswith("2026-09-30"))

    def test_age_uses_analysis_time_not_file_write_time(self):
        self.assertEqual(self.read(91)["state"], "stale")
        self.assertEqual(self.read(-6)["state"], "stale")
        self.assertEqual(self.read(90)["state"], "live")

    def test_absent_or_corrupt_report_is_not_live(self):
        self.assertEqual(read_advisor(self.path)["state"], "waiting")
        for payload in ('{"generated_at":', '[]', '{}', 'null', '"text"'):
            self.path.write_text(payload)
            self.assertEqual(read_advisor(self.path)["state"], "error")

    def test_invalid_timestamps_and_non_finite_values(self):
        for value in ("2026-09-29T23:58:00", "not a timestamp"):
            self.data = report(); self.data["generated_at"] = value
            self.assertEqual(self.read()["state"], "error")
        for value in (float("nan"), float("inf"), -1):
            self.data = report(); self.data["bid"] = value
            self.assertEqual(self.read()["state"], "error")

    def test_all_horizons_and_validity_are_required(self):
        self.data["horizons"].pop("SWING")
        self.assertEqual(self.read()["state"], "error")
        self.data = report(); self.data["horizons"]["SCALP"]["review_at"] = self.data["generated_at"]
        self.assertEqual(self.read()["state"], "error")

    def test_actionable_levels_are_required_and_preserved(self):
        self.data["overall"] = "SELL"
        scalp = self.data["horizons"]["SCALP"]; scalp["action"] = "SELL"
        self.assertEqual(self.read()["state"], "error")
        scalp["levels"] = dict(entry_zone=[4100,4101], sl=4103, tp1=4098, tp2=4095, tp3=4090)
        self.assertEqual(self.read()["report"]["horizons"]["SCALP"]["levels"], scalp["levels"])

    def test_separate_pages_and_original_report_endpoint(self):
        self.read()
        server = create_server(Path(self.temp.name), 0, self.path)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_port}"
            for route, marker in (("/", b"Live desk"), ("/advisor", b"Analysis desk"),
                                  ("/advisor.js", b"WHY THERE IS NO ENTRY"), ("/advisor.css", b"horizon-details")):
                with urlopen(root+route, timeout=3) as response:
                    self.assertIn(marker, response.read())
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
            with urlopen(root+"/api/advisor", timeout=3) as response:
                self.assertEqual(json.load(response)["report"], self.data)
            with urlopen(root+"/api/status", timeout=3) as response:
                self.assertEqual(json.load(response)["state"], "waiting")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == "__main__": unittest.main()
