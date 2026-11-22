"""Local display and acknowledged demo controls for the native GoldScalpAI EA.

No MT5 Python connection, trade functions, credentials, external requests or packages.
The EA remains the sole source of positions, statistics and decision state.
"""
from __future__ import annotations

import json
import math
import os
import re
import socket
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .gold_advisor_web import read_advisor, REPORT
from .gold_manual_scalp_web import read_manual_scalp, REPORT as MANUAL_SCALP_REPORT
from .gold_scalp_controls import ControlMailbox, ControlConflict

ASSETS = Path(__file__).with_name("gold_scalp_assets")
SOURCE_NAME = re.compile(r"dashboard_[A-Za-z0-9_]+\.json\Z")
MAX_SNAPSHOT_BYTES = 1_000_000
STALE_SECONDS = 5


class LocalDashboardServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can let an older server keep serving the same port.
    # A dashboard restart must never silently leave two versions listening.
    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def default_feed_directory() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ValueError("APPDATA is unavailable; supply --feed-directory explicitly.")
    return Path(appdata) / "MetaQuotes/Terminal/Common/Files/GoldScalp"


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def read_status(directory: Path, source: str = "", now: float | None = None) -> dict:
    """Never silently switch accounts or describe an old snapshot as live."""
    now = time.time() if now is None else now
    result = {"state": "waiting", "message": "Waiting for GoldScalpAI in MT5. Use tools/start_gold_scalp_mt5.ps1; keep ExportWebDashboard=true.",
              "sources": [], "source": source, "snapshot": None, "age_seconds": None}
    try:
        paths = sorted(p for p in directory.glob("dashboard_*.json")
                       if SOURCE_NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink())
        result["sources"] = [p.name for p in paths]
        if source and not SOURCE_NAME.fullmatch(source):
            raise ValueError("Invalid feed name.")
        if not source:
            if not paths:
                return result
            if len(paths) != 1:
                result.update(state="choose", message="Choose the MT5 account feed above. Accounts are never switched automatically.")
                return result
            source = paths[0].name
        result["source"] = source
        path = next((p for p in paths if p.name == source), None)
        if path is None:
            result.update(message="Selected EA feed is absent. Start that EA or choose another feed.")
            return result
        # Open once: content and timestamp belong to the same file replacement.
        with path.open("rb") as handle:
            modified = os.fstat(handle.fileno()).st_mtime
            payload = handle.read(MAX_SNAPSHOT_BYTES + 1)
        if len(payload) > MAX_SNAPSHOT_BYTES:
            raise ValueError("EA snapshot exceeds the size limit.")
        snapshot = json.loads(payload.decode("utf-8-sig"), parse_constant=_reject_constant, parse_float=_finite_float)
        if not isinstance(snapshot, dict) or snapshot.get("schema") != 1:
            raise ValueError("Unsupported EA snapshot schema; install the current GoldScalpAI build.")
        for key in ("account", "kpi", "market", "filters", "risk"):
            if not isinstance(snapshot.get(key), dict):
                raise ValueError(f"Incomplete EA snapshot: {key}")
        for key in ("controls", "scalp", "macro"):
            if key in snapshot and not isinstance(snapshot[key], dict):
                raise ValueError(f"Invalid EA snapshot: {key}")
        if "macro" in snapshot:
            events = snapshot["macro"].get("events")
            if not isinstance(events, list) or len(events) > 64 or any(not isinstance(event, dict) for event in events):
                raise ValueError("Invalid economic calendar events")
        for key, limit in (("positions", 100), ("candles", 180), ("deals", 60), ("events", 40)):
            items = snapshot.get(key)
            if not isinstance(items, list) or len(items) > limit or any(not isinstance(x, dict) for x in items):
                raise ValueError(f"Invalid EA snapshot: {key}")
        age = now - modified
        result.update(snapshot=snapshot, age_seconds=round(max(0, age), 1))
        if age < -5:
            result.update(state="stale", message="Snapshot timestamp is in the future. Check the computer clock.")
        elif snapshot.get("stopped"):
            result.update(state="stopped", message="The EA has stopped. Values below are its last snapshot.")
        elif age > STALE_SECONDS:
            result.update(state="stale", message="EA heartbeat is stale. Values below are the last received snapshot.")
        elif not snapshot.get("connected"):
            result.update(state="disconnected", message="EA is running, but MT5 is disconnected from the broker.")
        else:
            result.update(state="live", message="Connected to the native EA. Refreshing every second.")
        return result
    except (OSError, ValueError, TypeError, RecursionError) as error:
        result.update(state="error", message=f"Cannot read EA snapshot: {error}")
        return result


def create_server(directory: Path, port: int = 8766, advisor_report: Path = REPORT,
                  manual_scalp_report: Path = MANUAL_SCALP_REPORT) -> ThreadingHTTPServer:
    mailbox = ControlMailbox(directory)
    control_token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args: object) -> None:
            pass

        def reply(self, code: int, data: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            # Loopback only, plus Host validation to reject DNS rebinding.
            port = self.server.server_address[1]
            if self.headers.get("Host", "") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.reply(403, b"Local access only", "text/plain")
                return
            request = urlsplit(self.path)
            if request.path == "/api/advisor":
                status = read_advisor(advisor_report)
                support = getattr(self.server, "advisor_support", None)
                if support is not None:
                    status["support"] = support.health.copy()
                self.reply(200, json.dumps(status, ensure_ascii=True, allow_nan=False).encode(), "application/json; charset=utf-8")
                return
            if request.path == "/api/manual-scalp":
                status = read_manual_scalp(manual_scalp_report)
                self.reply(200, json.dumps(status, ensure_ascii=True, allow_nan=False).encode(), "application/json; charset=utf-8")
                return
            if request.path == "/api/status":
                source = parse_qs(request.query).get("source", [""])[0]
                status = read_status(directory, source)
                if (status.get('snapshot') or {}).get('controls', {}).get('enabled'):
                    status['control_token'] = control_token
                support = getattr(self.server, "advisor_support", None)
                if support is not None:
                    status["support"] = support.health.copy()
                body = json.dumps(status, ensure_ascii=True, allow_nan=False).encode()
                self.reply(200, body, "application/json; charset=utf-8")
                return
            assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
            assets.update({"/advisor": ("advisor.html", "text/html"), "/advisor/": ("advisor.html", "text/html"),
                           "/advisor.js": ("advisor.js", "text/javascript"), "/advisor.css": ("advisor.css", "text/css")})
            if request.path not in assets:
                self.reply(404, b"Not found", "text/plain")
                return
            name, mime = assets[request.path]
            self.reply(200, (ASSETS / name).read_bytes(), mime + "; charset=utf-8")

        def do_POST(self) -> None:
            port = self.server.server_address[1]
            host = self.headers.get('Host', '')
            if host not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                self.reply(403, b'Local access only', 'text/plain'); return
            if urlsplit(self.path).path != '/api/control':
                self.reply(404, b'Not found', 'text/plain'); return
            if (self.headers.get('Origin') != 'http://' + host or
                    not secrets.compare_digest(self.headers.get('X-Gold-Control', '').encode('utf-8'), control_token.encode('ascii'))):
                self.reply(403, b'Invalid origin or control token', 'text/plain'); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2048 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Expected a small JSON command')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict) or not isinstance(payload.get('source'), str):
                    raise ValueError('Explicit account feed required')
                status = read_status(directory, payload['source'])
                result = mailbox.enqueue(payload, status)
                self.reply(202, json.dumps(result).encode(), 'application/json')
            except ControlConflict as error:
                self.reply(409, str(error).encode(), 'text/plain')
            except (OSError, ValueError, TypeError, RecursionError) as error:
                self.reply(400, str(error).encode(), 'text/plain')

    server = LocalDashboardServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
