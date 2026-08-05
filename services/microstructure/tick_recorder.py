from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import MetaTrader5 as mt5

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.microstructure.parquet_store import PartitionedParquetBuffer
from services.utils.atomic_json import atomic_write_json


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _m1_atr(signal: ScalpSignalState | None) -> float:
    if signal is None or not isinstance(signal.metrics, dict):
        return 0.0
    m1 = signal.metrics.get("M1", {})
    return _safe_float(m1.get("atr")) if isinstance(m1, dict) else 0.0


class MT5TickRecorder:
    """Capture every MT5 tick available since the previous millisecond cursor."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._recent: deque[dict[str, Any]] = deque()
        self._last_time_msc: dict[str, int] = {}
        self._cursor_loaded: set[str] = set()
        self._cursor_write_errors: dict[str, str] = {}
        self._writer = PartitionedParquetBuffer(
            scalping_settings.SCALPING_TICK_DATA_ROOT,
            compression=scalping_settings.SCALPING_TICK_PARQUET_COMPRESSION,
            max_rows=scalping_settings.SCALPING_TICK_BUFFER_MAX_ROWS,
            flush_interval_seconds=scalping_settings.SCALPING_TICK_FLUSH_INTERVAL_SECONDS,
            dataset_name="mt5_ticks",
        )

    @staticmethod
    def _cursor_path(symbol: str) -> str:
        root = os.path.abspath(scalping_settings.SCALPING_TICK_CURSOR_ROOT)
        os.makedirs(root, exist_ok=True)
        safe = "".join(character if character.isalnum() else "_" for character in symbol)
        return os.path.join(root, f"{safe}_cursor.json")

    def _load_cursor(self, symbol: str) -> None:
        if symbol in self._cursor_loaded:
            return
        self._cursor_loaded.add(symbol)
        path = self._cursor_path(symbol)
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            self._last_time_msc[symbol] = _safe_int(payload.get("last_time_msc"), 0)
        except Exception:
            self._last_time_msc[symbol] = 0

    def _save_cursor(self, symbol: str, value: int) -> str:
        """Persist the resume cursor without ever terminating the live runner.

        Windows antivirus, indexers and dashboard readers can briefly hold the
        destination JSON without delete-sharing.  The shared atomic writer uses
        a unique temporary file, retries ``os.replace`` and falls back to a
        guarded overwrite.  If every persistence path is unavailable, the
        recorder keeps the newest cursor in memory and returns a warning.  A
        later cycle can persist it, and a later process restart safely
        resynchronizes to the current MT5 tape instead of replaying old ticks.
        """
        path = self._cursor_path(symbol)
        overlap_msc = int(
            max(0.0, float(scalping_settings.SCALPING_TICK_CURSOR_OVERLAP_SECONDS))
            * 1000.0
        )
        safe_resume = max(0, int(value) - overlap_msc)
        payload = {
            "symbol": symbol,
            "last_time_msc": safe_resume,
            "latest_captured_time_msc": int(value),
            "cursor_overlap_seconds": float(
                scalping_settings.SCALPING_TICK_CURSOR_OVERLAP_SECONDS
            ),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            atomic_write_json(
                path,
                payload,
                indent=2,
                replace_retries=20,
                retry_delay_seconds=0.05,
            )
            self._cursor_write_errors.pop(symbol, None)

            # Best-effort cleanup for the fixed ``.tmp`` file used by V5.1.3.
            # A locked legacy file is harmless because all new writes use
            # unique temporary names.
            legacy_temporary = Path(path + ".tmp")
            try:
                legacy_temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return ""
        except Exception as error:
            warning = f"{type(error).__name__}: {error}"
            self._cursor_write_errors[symbol] = warning
            return warning

    @staticmethod
    def _record_value(raw: Any, name: str, default: Any = 0) -> Any:
        if isinstance(raw, dict):
            return raw.get(name, default)
        try:
            return raw[name]
        except Exception:
            return getattr(raw, name, default)

    def _fetch_ticks(
        self,
        snapshot: ScalpingSnapshotState,
    ) -> tuple[list[Any], str, dict[str, Any]]:
        """Fetch only ticks that are recent enough to represent the live tape.

        A persisted cursor can be far behind after a terminal restart, a market
        closure, or a copied project folder. Replaying that backlog into the
        demo meta-controller would make historical ticks look live. When the
        cursor lag exceeds the configured ceiling, the recorder intentionally
        resynchronizes to a short window anchored on the current MT5 quote.
        """
        symbol = snapshot.symbol
        self._load_cursor(symbol)
        stored_last = int(self._last_time_msc.get(symbol, 0) or 0)
        current_msc = int(
            snapshot.tick_time_msc
            or int(snapshot.timestamp.timestamp() * 1000.0)
        )
        lookback_msc = int(
            max(0.1, float(scalping_settings.SCALPING_TICK_INITIAL_LOOKBACK_SECONDS))
            * 1000.0
        )
        max_lag_msc = int(
            max(1.0, float(scalping_settings.SCALPING_TICK_MAX_CURSOR_LAG_SECONDS))
            * 1000.0
        )
        future_tolerance_msc = int(
            max(0.0, float(scalping_settings.SCALPING_TICK_FUTURE_TOLERANCE_SECONDS))
            * 1000.0
        )
        lag_msc = current_msc - stored_last if stored_last > 0 else 0
        cursor_resynced = bool(
            stored_last <= 0
            or lag_msc > max_lag_msc
            or stored_last > current_msc + future_tolerance_msc
        )
        effective_last = (
            max(0, current_msc - lookback_msc)
            if cursor_resynced
            else stored_last
        )
        start = datetime.fromtimestamp(max(0, effective_last - 999) / 1000.0, tz=timezone.utc)
        metadata = {
            "cursor_resynced": cursor_resynced,
            "stored_cursor_time_msc": stored_last,
            "effective_cursor_time_msc": effective_last,
            "current_tick_time_msc": current_msc,
            "cursor_lag_before_seconds": round(max(0, lag_msc) / 1000.0, 3),
            "discarded_old_ticks": 0,
            "discarded_future_ticks": 0,
        }
        try:
            copied = mt5.copy_ticks_from(
                symbol,
                start,
                int(scalping_settings.SCALPING_TICK_MAX_BATCH),
                mt5.COPY_TICKS_ALL,
            )
        except Exception as error:
            return [], f"{type(error).__name__}: {error}", metadata
        if copied is None:
            return [], "MT5 copy_ticks_from returned None", metadata

        rows = list(copied)
        accepted: list[Any] = []
        oldest_live_msc = current_msc - max_lag_msc
        latest_live_msc = current_msc + future_tolerance_msc
        for row in rows:
            row_msc = _safe_int(self._record_value(row, "time_msc", 0))
            if row_msc <= effective_last:
                continue
            if row_msc < oldest_live_msc:
                metadata["discarded_old_ticks"] += 1
                continue
            if row_msc > latest_live_msc:
                metadata["discarded_future_ticks"] += 1
                continue
            accepted.append(row)
        return accepted, "", metadata

    @staticmethod
    def _fallback_current_tick(snapshot: ScalpingSnapshotState) -> dict[str, Any]:
        time_msc = int(snapshot.tick_time_msc or int(snapshot.timestamp.timestamp() * 1000.0))
        return {
            "time": int(time_msc // 1000),
            "time_msc": time_msc,
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "last": snapshot.last_price,
            "volume": snapshot.tick_volume,
            "volume_real": snapshot.tick_volume_real,
            "flags": snapshot.tick_flags,
        }

    def capture(
        self,
        snapshot: ScalpingSnapshotState,
        signal: ScalpSignalState | None,
        *,
        open_position_count: int,
        intermarket: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not bool(scalping_settings.SCALPING_TICK_RECORDER_ENABLED):
            return {
                "enabled": False,
                "captured": 0,
                "recent_ticks": list(self._recent),
                "storage": self._writer.status(buffered_only=True),
            }

        with self._lock:
            raw_ticks, fetch_error, cursor_status = self._fetch_ticks(snapshot)
            if bool(cursor_status.get("cursor_resynced", False)):
                self._last_time_msc[snapshot.symbol] = int(
                    cursor_status.get("effective_cursor_time_msc", 0) or 0
                )
            if not raw_ticks:
                fallback = self._fallback_current_tick(snapshot)
                last = self._last_time_msc.get(snapshot.symbol, 0)
                if int(fallback["time_msc"]) > last:
                    raw_ticks = [fallback]

            atr = _m1_atr(signal)
            signal_direction = str(getattr(signal, "direction", "NONE") or "NONE")
            signal_allowed = bool(getattr(signal, "allowed", False))
            intermarket = intermarket or {}
            values = intermarket.get("values", {}) if isinstance(intermarket, dict) else {}
            returns = intermarket.get("returns", {}) if isinstance(intermarket, dict) else {}
            now_utc = datetime.now(timezone.utc).isoformat()
            normalized: list[dict[str, Any]] = []
            seen_tick_keys: set[str] = set()
            for raw in raw_ticks:
                time_msc = _safe_int(self._record_value(raw, "time_msc", 0))
                bid = _safe_float(self._record_value(raw, "bid", 0.0))
                ask = _safe_float(self._record_value(raw, "ask", 0.0))
                if time_msc <= 0 or bid <= 0 or ask <= 0 or ask < bid:
                    continue
                mid = (bid + ask) / 2.0
                broker_time = datetime.fromtimestamp(time_msc / 1000.0, tz=timezone.utc)
                tick_key = f"{snapshot.symbol}:{time_msc}:{bid:.10f}:{ask:.10f}"
                if tick_key in seen_tick_keys:
                    continue
                seen_tick_keys.add(tick_key)
                row = {
                    "recorded_at_utc": now_utc,
                    "broker_time_utc": broker_time.isoformat(),
                    "timestamp_msc": time_msc,
                    "time_msc": time_msc,
                    "symbol": snapshot.symbol,
                    "tick_key": tick_key,
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "spread": ask - bid,
                    "last": _safe_float(self._record_value(raw, "last", 0.0)),
                    "tick_volume": _safe_float(self._record_value(raw, "volume", 0.0)),
                    "volume_real": _safe_float(self._record_value(raw, "volume_real", 0.0)),
                    "tick_flags": _safe_int(self._record_value(raw, "flags", 0)),
                    "session": snapshot.session,
                    "active_sessions": ",".join(snapshot.active_sessions),
                    "m1_atr": atr,
                    "signal_direction": signal_direction,
                    "signal_allowed": signal_allowed,
                    "signal_stage": "V4_TECHNICAL_CANDIDATE",
                    "open_position_count": int(open_position_count),
                    "has_open_position": int(open_position_count) > 0,
                    "dxy_symbol": intermarket.get("resolved_symbols", {}).get("dxy", ""),
                    "dxy_value": _safe_float(values.get("dxy")),
                    "dxy_return_1s": _safe_float(returns.get("dxy", {}).get("1s")),
                    "dxy_return_5s": _safe_float(returns.get("dxy", {}).get("5s")),
                    "dxy_return_15s": _safe_float(returns.get("dxy", {}).get("15s")),
                    "us10y_symbol": intermarket.get("resolved_symbols", {}).get("us10y", ""),
                    "us10y_value": _safe_float(values.get("us10y")),
                    "us10y_return_1s": _safe_float(returns.get("us10y", {}).get("1s")),
                    "us10y_return_5s": _safe_float(returns.get("us10y", {}).get("5s")),
                    "us10y_return_15s": _safe_float(returns.get("us10y", {}).get("15s")),
                    "tnote_symbol": intermarket.get("resolved_symbols", {}).get("tnote", ""),
                    "tnote_value": _safe_float(values.get("tnote")),
                    "tnote_return_1s": _safe_float(returns.get("tnote", {}).get("1s")),
                    "tnote_return_5s": _safe_float(returns.get("tnote", {}).get("5s")),
                    "tnote_return_15s": _safe_float(returns.get("tnote", {}).get("15s")),
                    "intermarket_gold_bias": intermarket.get("gold_bias", "NEUTRAL"),
                    "intermarket_pressure_score": _safe_float(intermarket.get("pressure_score")),
                }
                normalized.append(row)

            normalized.sort(key=lambda item: item["time_msc"])
            cursor_write_error = ""
            if normalized:
                newest = int(normalized[-1]["time_msc"])
                self._last_time_msc[snapshot.symbol] = newest
                cursor_write_error = self._save_cursor(snapshot.symbol, newest)
                self._recent.extend(normalized)
            else:
                cursor_write_error = self._cursor_write_errors.get(snapshot.symbol, "")

            cursor_status["cursor_persisted"] = not bool(cursor_write_error)
            cursor_status["cursor_write_error"] = cursor_write_error

            latest_seen = (
                int(self._recent[-1].get("time_msc", 0))
                if self._recent
                else int(self._last_time_msc.get(snapshot.symbol, 0))
            )
            cutoff = latest_seen - int(
                float(scalping_settings.SCALPING_TICK_RECENT_MEMORY_SECONDS) * 1000.0
            )
            while self._recent and int(self._recent[0].get("time_msc", 0)) < cutoff:
                self._recent.popleft()

            storage = self._writer.status(buffered_only=True)
            if normalized:
                partition = datetime.fromtimestamp(normalized[-1]["time_msc"] / 1000.0, tz=timezone.utc).date().isoformat()
                storage = self._writer.append(
                    normalized,
                    partition_date=partition,
                    symbol=snapshot.symbol,
                )

            return {
                "enabled": True,
                "captured": len(normalized),
                "latest_time_msc": self._last_time_msc.get(snapshot.symbol, 0),
                "recent_tick_count": len(self._recent),
                "recent_ticks": list(self._recent),
                "fetch_error": fetch_error,
                "cursor": cursor_status,
                "cursor_write_error": cursor_write_error,
                "storage": storage,
            }

    def flush(self) -> dict[str, Any]:
        return self._writer.flush()


_RECORDER = MT5TickRecorder()


def capture_mt5_ticks(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState | None,
    *,
    open_position_count: int,
    intermarket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _RECORDER.capture(
        snapshot,
        signal,
        open_position_count=open_position_count,
        intermarket=intermarket,
    )


def flush_tick_recorder() -> dict[str, Any]:
    return _RECORDER.flush()
