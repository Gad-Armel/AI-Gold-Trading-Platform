"""
Local REST API Bridge for MetaTrader 5 Expert Advisor and Quantitative Client.
Allows MT5 EA to query live Market Intelligence via MQL5 `WebRequest()`
or standard HTTP requests.
"""

from typing import Dict, Any, Optional
import json
import logging
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

logger = logging.getLogger("XAUUSD_APIBridge")

# Global holder for latest market intelligence payload
_CURRENT_INTELLIGENCE: Dict[str, Any] = {
    "status": "INITIALIZING",
    "symbol": "XAUUSD",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "signal": "NO_TRADE",
    "confidence": 0.0,
    "regime": "RANGING_MEAN_REVERT",
    "expected_volatility_points": 18.0,
    "recommended_sl_distance_points": 45.0,
    "recommended_tp_distance_points": 67.5,
    "risk_reward_ratio": 1.5,
    "ea_override_permitted": False,
    "execution_authority": "MT5_EA_RISK_MANAGER",
    "service_available": True
}


def update_intelligence_state(payload: Dict[str, Any]):
    """Thread-safe update of current market intelligence payload."""
    global _CURRENT_INTELLIGENCE
    _CURRENT_INTELLIGENCE = {
        **payload,
        "service_available": True,
        "last_updated_utc": datetime.now(timezone.utc).isoformat()
    }


class MT5HTTPRequestHandler(BaseHTTPRequestHandler):
    """Minimalistic zero-dependency HTTP request handler for MT5 WebRequest compatibility."""

    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/v1/market-intelligence") or self.path == "/":
            self._send_json_response(_CURRENT_INTELLIGENCE)
        elif self.path.startswith("/api/v1/health"):
            health = {
                "status": "HEALTHY",
                "service": "XAUUSD_AI_Market_Intelligence_Engine",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "symbol": "XAUUSD",
                "ea_override_permitted": False
            }
            self._send_json_response(health)
        else:
            self._send_json_response({"error": "Endpoint not found"}, status_code=404)

    def log_message(self, format, *args):
        # Suppress noisy standard HTTP access logs
        return


class MT5APIBridgeServer:
    """Manages the background HTTP daemon server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Starts HTTP server in background thread."""
        try:
            self.server = HTTPServer((self.host, self.port), MT5HTTPRequestHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info("MT5 API Bridge Server listening at http://%s:%d", self.host, self.port)
        except Exception as e:
            logger.error("Failed to start API Bridge Server on %s:%d: %s", self.host, self.port, e)

    def stop(self):
        """Stops HTTP server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("MT5 API Bridge Server stopped.")
