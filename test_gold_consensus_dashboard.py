from __future__ import annotations

import json
import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from services.dashboard.gold_consensus_web import HTML, open_dashboard_url, start_dashboard_server


class GoldConsensusDashboardTests(unittest.TestCase):
    def test_entry_engine_is_distinguished_from_advisor_context(self):
        self.assertIn('Entry engine:', HTML)
        self.assertIn('CONTEXT ONLY, not an order instruction', HTML)
        self.assertIn('NOT AUTHORIZED TO OPEN', HTML)

    def test_advisor_page_assets_and_read_only_report(self):
        server, url = start_dashboard_server(port=0, open_browser=False)
        try:
            for path in ('/advisor', '/advisor.js', '/advisor.css', '/style.css'):
                with urlopen(url + path, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.read())
            with urlopen(url + '/api/advisor', timeout=2) as response:
                self.assertIn('state', json.load(response))
        finally:
            server.shutdown()
            server.server_close()

    def test_large_status_is_compressed_only_when_client_accepts_gzip(self):
        payload = json.dumps({'status': 'RUNNING', 'details': 'sample '*3000}).encode()
        with patch('services.dashboard.gold_consensus_web.STATUS_PATH') as status_path:
            status_path.read_bytes.return_value = payload
            server, url = start_dashboard_server(port=0, open_browser=False)
            try:
                for encoding, compressed in (('gzip', True), ('gzip;q=0', False)):
                    request = Request(url+'/api/status', headers={'Accept-Encoding': encoding})
                    with urlopen(request, timeout=2) as response:
                        body = response.read()
                        self.assertEqual(len(body), int(response.headers['Content-Length']))
                        if compressed:
                            self.assertEqual(response.headers['Content-Encoding'], 'gzip')
                            self.assertLess(len(body), len(payload))
                            self.assertEqual(gzip.decompress(body), payload)
                        else:
                            self.assertIsNone(response.headers.get('Content-Encoding'))
                            self.assertEqual(body, payload)
            finally:
                server.shutdown()
                server.server_close()

    def test_locked_status_returns_retryable_error_not_fake_waiting_status(self):
        with patch('services.dashboard.gold_consensus_web.STATUS_PATH') as status_path:
            status_path.read_bytes.side_effect = PermissionError('temporary lock')
            server, url = start_dashboard_server(port=0, open_browser=False)
            try:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(url+'/api/status', timeout=2)
                self.assertEqual(caught.exception.code, 503)
                self.assertIn('temporarily unavailable', caught.exception.read().decode())
            finally:
                server.shutdown()
                server.server_close()

    def test_refresh_keeps_cached_data_and_retries_without_overlapping_requests(self):
        self.assertIn('if(refreshPending)return', HTML)
        self.assertIn('new AbortController()', HTML)
        self.assertIn('if(!r.ok)throw', HTML)
        self.assertIn('Displayed values are cached, NOT live.', HTML)
        self.assertIn('DASHBOARD CONNECTION LOST', HTML)
        self.assertIn('lastDashboardHtml=$(\'app\').innerHTML', HTML)
        self.assertIn('finally{clearTimeout(deadline);refreshPending=false;}', HTML)
        self.assertIn('await refresh();setTimeout(pollDashboard,2000)', HTML)
        self.assertNotIn('setInterval(refresh,2000)', HTML)
        self.assertNotIn('Waiting for bot status...', HTML)

    def test_only_scalp_sections_are_rendered_without_removing_context_data(self):
        self.assertIn("${laneCard('SCALP',l.SCALP||{})}", HTML)
        self.assertIn("${history('SCALP',l.SCALP||{})}", HTML)
        for name in ('INTRADAY', 'SWING'):
            self.assertNotIn("${laneCard('" + name, HTML)
            self.assertNotIn("${history('" + name, HTML)
        self.assertIn("filter(([name])=>name==='SCALP')", HTML)
        self.assertIn('up to 4 positions', HTML)

    def test_dashboard_launch_uses_run_specific_refresh_url(self) -> None:
        with patch("services.dashboard.gold_consensus_web.time.time", return_value=123.456), \
                patch("services.dashboard.gold_consensus_web.os.name", "posix"), \
                patch("services.dashboard.gold_consensus_web.webbrowser.open") as browser_open:
            url = open_dashboard_url(8765)
        self.assertEqual(url, "http://127.0.0.1:8765/?run=123456")
        browser_open.assert_called_once_with(url, new=0, autoraise=True)

    def test_dashboard_and_status_api_are_available_on_localhost(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            status_path = Path(folder) / "status.json"
            status_path.write_text(json.dumps({"status": "RUNNING", "consensus": {"direction": "WAIT"},
                "lanes": {name: {"context": "retained"} for name in ('SCALP', 'INTRADAY', 'SWING')}}), encoding="utf-8")
            with patch("services.dashboard.gold_consensus_web.STATUS_PATH", status_path):
                server, url = start_dashboard_server(port=0, open_browser=False)
                try:
                    with urlopen(url, timeout=2) as response:  # nosec B310 - test-only localhost server
                        page = response.read().decode("utf-8")
                    with urlopen(url + "/api/status", timeout=2) as response:  # nosec B310
                        payload = json.loads(response.read().decode("utf-8"))
                finally:
                    server.shutdown()
                    server.server_close()
        self.assertIn("Gold Scalping Command Center", page)
        self.assertIn("V3 MT5 Tick Flow", page)
        self.assertIn("Latest 30 closed trades", page)
        self.assertIn("Possible TP1 / TP2 / TP3", page)
        self.assertIn("Valid until (local)", page)
        self.assertIn("Combined lane P/L", page)
        self.assertIn("Reset 24h P/L baseline", page)
        self.assertIn("Number(x)<0?'-$'+", page)
        self.assertNotIn("â", page)
        self.assertNotIn("Â", page)
        self.assertEqual(payload["status"], "RUNNING")
        self.assertEqual(payload["consensus"]["direction"], "WAIT")
        self.assertEqual(set(payload['lanes']), {'SCALP', 'INTRADAY', 'SWING'})


if __name__ == "__main__":
    unittest.main(verbosity=2)
