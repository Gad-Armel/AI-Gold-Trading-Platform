from __future__ import annotations

import getpass
import hmac
import json
import os
import runpy
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_URL = "http://127.0.0.1:8777/"
HEALTH_URL = DASHBOARD_URL + "health"
EXPECTED_HEALTH = {"ok": True, "dashboard": "aurum-gold-unified"}

sys.path.insert(0, str(ROOT))


def is_demo_account(account: object, demo_mode: int) -> bool:
    return account is not None and getattr(account, "trade_mode", None) == demo_mode


def confirmation_matches(required: str, supplied: str) -> bool:
    return bool(required) and hmac.compare_digest(required, supplied)


def dashboard_health() -> dict | None:
    try:
        with urlopen(HEALTH_URL, timeout=1) as response:
            payload = json.load(response)
            return payload if response.status == 200 and isinstance(payload, dict) else None
    except (OSError, ValueError, URLError):
        return None


def dashboard_is_ready() -> bool:
    return dashboard_health() == EXPECTED_HEALTH


def start_dashboard() -> None:
    health = dashboard_health()
    if health is not None and health != EXPECTED_HEALTH:
        raise RuntimeError(
            "Port 8777 is occupied by a different dashboard. Close it before launching the unified desk."
        )
    if health != EXPECTED_HEALTH:
        command = [
            sys.executable,
            "-B",
            str(ROOT / "run_gold_unified_dashboard.py"),
            "--no-browser",
        ]
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        process = subprocess.Popen(command, cwd=ROOT, creationflags=flags)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if dashboard_is_ready():
                break
            if process.poll() is not None:
                raise RuntimeError(
                    f"Dashboard exited during startup (code {process.returncode})."
                )
            time.sleep(0.25)
        else:
            raise RuntimeError("Dashboard did not become healthy on port 8777.")
    webbrowser.open(DASHBOARD_URL)
    print(f"Dashboard ready: {DASHBOARD_URL}")


def find_mt5_terminal() -> Path | None:
    configured = os.environ.get("GOLD_MT5_TERMINAL")
    if configured:
        terminal = Path(configured).expanduser()
        if not terminal.is_file():
            raise RuntimeError(f"GOLD_MT5_TERMINAL does not point to a file: {terminal}")
        return terminal
    candidates = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "MetaTrader 5" / "terminal64.exe")
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def verify_demo_terminal() -> None:
    try:
        import MetaTrader5 as mt5
    except ImportError as error:
        raise RuntimeError(
            "MetaTrader5 Python package is unavailable; install the project's requirements."
        ) from error

    terminal = find_mt5_terminal()
    if terminal:
        print(f"Connecting to MetaTrader 5: {terminal}")
        connected = mt5.initialize(str(terminal), timeout=60000)
    else:
        print("Connecting to the MetaTrader 5 terminal registered with the system.")
        connected = mt5.initialize(timeout=60000)
    if not connected:
        raise RuntimeError(f"MT5 is not ready: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        if not is_demo_account(account, mt5.ACCOUNT_TRADE_MODE_DEMO):
            raise RuntimeError(
                "Startup refused: connect MetaTrader 5 to a DEMO account first."
            )
    finally:
        mt5.shutdown()


def run_confirmed_demo_bot() -> int:
    from config import scalping_settings

    required = str(scalping_settings.SCALPING_REQUIRED_DEMO_CONFIRMATION or "")
    if not required:
        raise RuntimeError(
            "Demo confirmation is not configured; no trading bot was started."
        )
    supplied = getpass.getpass(
        "Enter the locally configured DEMO confirmation phrase (hidden; blank cancels): "
    )
    if not confirmation_matches(required, supplied):
        raise RuntimeError("Confirmation did not match; no trading bot was started.")

    sys.argv = [
        str(ROOT / "run_gold_ai.py"),
        "--mode",
        "demo",
        "--confirm",
        supplied,
        "--no-dashboard",
    ]
    print("Starting the XAUUSD demo AI. Keep this window open to keep it running.")
    try:
        runpy.run_path(str(ROOT / "run_gold_ai.py"), run_name="__main__")
    except SystemExit as error:
        return int(error.code or 0)
    return 0


def main() -> int:
    try:
        start_dashboard()
        verify_demo_terminal()
        return run_confirmed_demo_bot()
    except (RuntimeError, OSError) as error:
        print(f"Gold demo startup stopped: {error}")
        return 1
    except KeyboardInterrupt:
        print("\nGold demo startup cancelled.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
