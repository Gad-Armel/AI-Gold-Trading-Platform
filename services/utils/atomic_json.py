from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def _flush_json_file(handle: Any, payload: Any, *, indent: int) -> None:
    json.dump(payload, handle, indent=indent, ensure_ascii=False, default=str)
    handle.flush()
    os.fsync(handle.fileno())


def atomic_write_json(
    path: str | os.PathLike[str],
    payload: Any,
    *,
    indent: int = 4,
    replace_retries: int = 12,
    retry_delay_seconds: float = 0.04,
) -> str:
    """Persist JSON safely, including on Windows with transient file locks.

    A unique temporary file prevents two writers from sharing the same ``.tmp``
    path. ``os.replace`` is retried because antivirus, indexing and dashboard
    readers may briefly hold the destination without delete sharing on Windows.
    When rename remains unavailable but the destination is writable, a guarded
    direct replacement is used after preserving the previous valid file as
    ``.backup``. The temporary file is retained as ``.pending`` only when every
    recovery path fails.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    attempts = max(1, int(replace_retries))
    base_delay = max(0.0, float(retry_delay_seconds))

    with _path_lock(target):
        descriptor, temporary_name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                _flush_json_file(handle, payload, indent=indent)

            last_error: OSError | None = None
            for attempt in range(attempts):
                try:
                    os.replace(temporary, target)
                    return str(target)
                except PermissionError as error:
                    last_error = error
                    if attempt + 1 < attempts:
                        time.sleep(base_delay * min(attempt + 1, 5))
                except OSError as error:
                    last_error = error
                    if attempt + 1 < attempts:
                        time.sleep(base_delay * min(attempt + 1, 5))

            # Windows can deny rename/delete sharing while still allowing a
            # normal overwrite. Preserve the previous journal before using that
            # compatibility path.
            backup = Path(f"{target}.backup")
            if target.exists():
                try:
                    shutil.copy2(target, backup)
                except OSError:
                    pass

            try:
                with temporary.open("r", encoding="utf-8") as source:
                    recovered_payload = json.load(source)
                with target.open("w", encoding="utf-8", newline="") as destination:
                    _flush_json_file(destination, recovered_payload, indent=indent)
                temporary.unlink(missing_ok=True)
                return str(target)
            except Exception as fallback_error:
                pending = target.with_name(
                    f"{target.name}.pending-{int(time.time() * 1000)}.json"
                )
                try:
                    os.replace(temporary, pending)
                except OSError:
                    pending = temporary
                detail = last_error or fallback_error
                raise OSError(
                    f"Could not safely replace JSON file '{target}'. "
                    f"Recovery copy preserved at '{pending}': {detail}"
                ) from fallback_error
        except Exception:
            # Do not delete a fully written temporary recovery file after a
            # failed destination update. Empty/partial files are cleaned up.
            if temporary.exists() and temporary.stat().st_size == 0:
                temporary.unlink(missing_ok=True)
            raise
