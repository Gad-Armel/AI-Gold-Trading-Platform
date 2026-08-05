from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from config import scalping_settings


class ScalpingInstanceAlreadyRunning(RuntimeError):
    """Raised when another paper-scalping runner owns the process lock."""


class ScalpingInstanceLock:
    """Cross-platform process lock released automatically when Python exits."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(
            path
            or getattr(
                scalping_settings,
                "SCALPING_INSTANCE_LOCK_PATH",
                "data/runtime/scalping_loop.lock",
            )
        )
        self._handle: BinaryIO | None = None
        self._locked = False

    def acquire(self) -> "ScalpingInstanceLock":
        if self._locked:
            return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)

        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as error:
            handle.close()
            raise ScalpingInstanceAlreadyRunning(
                "Another paper-scalping loop is already running. "
                "Stop the existing PowerShell/Python process before starting a second one."
            ) from error

        self._handle = handle
        self._locked = True
        metadata = {
            "pid": os.getpid(),
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
            "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
            "paper_only": bool(scalping_settings.SCALPING_PAPER_ONLY),
        }
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(metadata, indent=2).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
        return self

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None
            self._locked = False

    def __enter__(self) -> "ScalpingInstanceLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
