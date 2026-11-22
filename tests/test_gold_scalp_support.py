import json
from pathlib import Path
import tempfile
import unittest

from services.dashboard.gold_scalp_support import advisor_line, publish_advisor


def report():
    return {"generated_at": "2026-09-29T08:00:00+00:00", "symbol": "XAUUSD", "bid": 4100.1, "ask": 4100.3,
            "horizons": {"SCALP": {"valid_until": "2026-09-29T08:05:00+00:00", "action": "WAIT", "bias": "SELL", "directional_score": 72.5}}}


class AdvisorTransportTests(unittest.TestCase):
    def test_preserves_timestamp_and_wait(self):
        line, generated = advisor_line(report())
        fields = line.strip().split(";")
        self.assertEqual(fields[1], str(int(generated)))
        self.assertEqual(fields[4:7], ["WAIT", "SELL", "72.5"])
        self.assertEqual(int(fields[2]) - int(fields[1]), 300)

    def test_repeated_atomic_publication_preserves_original_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "original.json"; destination = root / "feeds"
            source.write_text(json.dumps(report()), encoding="utf-8")
            before = source.read_bytes()
            publish_advisor(source, destination)
            first = (destination / "advisor1.csv").read_bytes()
            publish_advisor(source, destination)
            self.assertEqual(first, (destination / "advisor1.csv").read_bytes())
            self.assertEqual(before, source.read_bytes())
            changed = report(); changed["horizons"]["SCALP"]["action"] = "SELL"
            source.write_text(json.dumps(changed), encoding="utf-8")
            publish_advisor(source, destination)
            self.assertIn(b";SELL;SELL;", (destination / "advisor1.csv").read_bytes())
            self.assertEqual(list(destination.glob("*.tmp")), [])

    def test_rejects_bad_quotes_and_injection(self):
        for value in (float("nan"), -1, 4101):
            data = report(); data["bid"] = value
            with self.assertRaises(ValueError): advisor_line(data)
        data = report(); data["symbol"] = "XAUUSD;BUY"
        with self.assertRaises(ValueError): advisor_line(data)

    def test_rejects_ambiguous_timezone(self):
        data = report(); data["generated_at"] = "2026-09-29T08:00:00"
        with self.assertRaises(ValueError): advisor_line(data)


if __name__ == "__main__": unittest.main()
