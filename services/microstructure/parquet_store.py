from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable

import pandas as pd


def _json_safe(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class PartitionedParquetBuffer:
    """Small, thread-safe buffered writer for partitioned Parquet datasets.

    The class creates Hive-style folders such as ``date=2026-07-15`` and
    ``symbol=XAUUSD``. Each flush writes a new immutable part file, which makes
    the dataset directly queryable with DuckDB glob patterns and prevents a
    process interruption from corrupting an existing file.
    """

    def __init__(
        self,
        root: str,
        *,
        compression: str = "zstd",
        max_rows: int = 1000,
        flush_interval_seconds: float = 5.0,
        dataset_name: str = "dataset",
    ) -> None:
        self.root = os.path.abspath(root)
        self.compression = compression
        self.max_rows = max(1, int(max_rows))
        self.flush_interval_seconds = max(0.1, float(flush_interval_seconds))
        self.dataset_name = str(dataset_name or "dataset")
        self._buffers: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self._last_flush = time.monotonic()
        self._lock = threading.RLock()
        self.last_error = ""
        self.rows_written = 0
        self.files_written = 0

    def append(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        partition_date: str,
        symbol: str,
        force: bool = False,
    ) -> dict[str, Any]:
        normalized = [
            {str(key): _json_safe(value) for key, value in row.items()}
            for row in rows
            if isinstance(row, dict)
        ]
        if not normalized:
            return self.status(buffered_only=True)

        key = (str(partition_date), str(symbol or "UNKNOWN"))
        with self._lock:
            self._buffers[key].extend(normalized)
            total_buffered = sum(len(items) for items in self._buffers.values())
            due = (
                force
                or total_buffered >= self.max_rows
                or (time.monotonic() - self._last_flush) >= self.flush_interval_seconds
            )
            if due:
                self.flush()
            return self.status(buffered_only=not due)

    def flush(self) -> dict[str, Any]:
        with self._lock:
            pending = dict(self._buffers)
            self._buffers.clear()
            self._last_flush = time.monotonic()
            flushed_rows = 0
            flushed_files = 0

            for (partition_date, symbol), rows in pending.items():
                if not rows:
                    continue
                folder = os.path.join(
                    self.root,
                    f"date={partition_date}",
                    f"symbol={symbol}",
                )
                os.makedirs(folder, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                token = uuid.uuid4().hex[:10]
                filename = f"part-{stamp}-{token}.parquet"
                destination = os.path.join(folder, filename)
                temporary = destination + ".tmp"
                try:
                    frame = pd.DataFrame.from_records(rows)
                    frame.to_parquet(
                        temporary,
                        index=False,
                        engine="pyarrow",
                        compression=self.compression,
                    )
                    os.replace(temporary, destination)
                    self.rows_written += len(rows)
                    self.files_written += 1
                    flushed_rows += len(rows)
                    flushed_files += 1
                    self.last_error = ""
                except Exception as error:
                    # Restore failed rows to memory so a later flush may retry.
                    self._buffers[(partition_date, symbol)][0:0] = rows
                    self.last_error = f"{type(error).__name__}: {error}"
                    try:
                        if os.path.exists(temporary):
                            os.remove(temporary)
                    except OSError:
                        pass
            status = self.status(buffered_only=False)
            status["flushed_rows"] = flushed_rows
            status["flushed_files"] = flushed_files
            return status

    def status(self, *, buffered_only: bool = False) -> dict[str, Any]:
        with self._lock:
            return {
                "dataset": self.dataset_name,
                "root": self.root,
                "buffered_rows": sum(len(items) for items in self._buffers.values()),
                "rows_written": self.rows_written,
                "files_written": self.files_written,
                "last_error": self.last_error,
                "buffered_only": buffered_only,
            }
