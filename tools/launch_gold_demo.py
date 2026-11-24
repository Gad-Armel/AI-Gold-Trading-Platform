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
from datetime import datetime, timezone
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


def start_dashboard(*, open_browser: bool = True) -> None:
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
    if open_browser:
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


def validate_demo_configuration() -> None:
    """Refuse a detached launch if the user-approved hard limits drift."""
    from config import gold_consensus_settings as settings

    errors: list[str] = []
    if settings.SYMBOL != "XAUUSD":
        errors.append("symbol must be XAUUSD")
    if float(settings.LOT_SIZE) != 0.01:
        errors.append("lot size must be exactly 0.01")
    if int(settings.MAX_POSITION_SLOTS) != 3:
        errors.append("total position limit must be exactly 3")
    scalp = settings.HORIZON_LANES.get("SCALP", {})
    if scalp.get("trade_enabled") is not True or int(scalp.get("max_positions", 0)) > 3:
        errors.append("SCALP must be enabled with at most 3 positions")
    active_slower = [
        name
        for name in ("INTRADAY", "SWING")
        if settings.HORIZON_LANES.get(name, {}).get("trade_enabled") is True
    ]
    if active_slower:
        errors.append("only the SCALP lane may submit orders")
    if errors:
        raise RuntimeError("Unsafe AIGold demo configuration: " + "; ".join(errors))


def demo_bot_command(python_executable: str, confirmation: str) -> list[str]:
    return [
        str(python_executable),
        "-B",
        str(ROOT / "run_gold_ai.py"),
        "--mode",
        "demo",
        "--confirm",
        str(confirmation),
        "--no-dashboard",
    ]


def read_consensus_status() -> dict | None:
    try:
        value = json.loads(
            (ROOT / "data" / "runtime" / "gold_consensus_status.json").read_text(
                encoding="utf-8"
            )
        )
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def status_is_live(status: dict | None, *, now: float | None = None, max_age: float = 20.0) -> bool:
    if not isinstance(status, dict) or str(status.get("status", "")).upper() != "RUNNING":
        return False
    try:
        updated = datetime.fromisoformat(str(status["updated_at"]).replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age = (time.time() if now is None else float(now)) - updated.timestamp()
        return -5.0 <= age <= float(max_age)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def start_demo_bot_background(
    python_executable: str,
    confirmation: str,
    *,
    runtime_directory: Path | None = None,
    timeout: float = 120.0,
) -> int:
    """Start AIGold independently of PowerShell and require a fresh heartbeat."""
    validate_demo_configuration()
    runtime = runtime_directory or ROOT / "data" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    pid_path = runtime / "aigold-demo.pid.json"

    existing = read_consensus_status()
    if status_is_live(existing):
        try:
            return int(json.loads(pid_path.read_text(encoding="utf-8"))["pid"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return 0

    stdout_path = runtime / "aigold-demo.stdout.log"
    stderr_path = runtime / "aigold-demo.stderr.log"
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open(
        "a", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            demo_bot_command(python_executable, confirmation),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=flags,
            env=environment,
            close_fds=True,
        )

    temporary = pid_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "pid": process.pid,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "mode": "demo",
                "symbol": "XAUUSD",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, pid_path)

    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            detail = ""
            try:
                detail = stderr_path.read_text(encoding="utf-8")[-2000:]
            except OSError:
                pass
            raise RuntimeError(
                f"AIGold exited during startup (code {process.returncode}). {detail}".strip()
            )
        if status_is_live(read_consensus_status()):
            return int(process.pid)
        time.sleep(0.5)

    process.terminate()
    raise RuntimeError(
        "AIGold did not publish a fresh RUNNING heartbeat within "
        f"{int(timeout)} seconds. See data/runtime/aigold-demo.stderr.log."
    )


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
    background = "--background" in sys.argv
    confirmed = "--yes-demo-risk" in sys.argv
    no_browser = "--no-browser" in sys.argv
    try:
        start_dashboard(open_browser=not no_browser)
        verify_demo_terminal()
        if background:
            if not confirmed:
                raise RuntimeError(
                    "Detached demo execution requires --yes-demo-risk."
                )
            from config import scalping_settings

            required = str(scalping_settings.SCALPING_REQUIRED_DEMO_CONFIRMATION or "")
            if not required:
                raise RuntimeError("Demo confirmation is not configured.")
            pid = start_demo_bot_background(sys.executable, required)
            print(
                f"AIGold demo is RUNNING independently (PID {pid}). "
                "PowerShell and VS Code may now be closed."
            )
            return 0
        return run_confirmed_demo_bot()
    except (RuntimeError, OSError) as error:
        print(f"Gold demo startup stopped: {error}")
        return 1
    except KeyboardInterrupt:
        print("\nGold demo startup cancelled.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
