from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.microstructure.parquet_store import PartitionedParquetBuffer
from services.risk.scalping_risk_guard import get_scalping_log_folder


_AUDIT_FIELDS = [
    "audit_timestamp_utc",
    "event_type",
    "trade_id",
    "strategy_id",
    "symbol",
    "direction",
    "paper_only",
    "decision_timestamp_utc",
    "order_request_timestamp_utc",
    "broker_response_timestamp_utc",
    "decision_to_request_ms",
    "request_to_response_ms",
    "signal_bid",
    "signal_ask",
    "signal_spread",
    "requested_entry_price",
    "actual_entry_fill",
    "entry_slippage_price",
    "entry_slippage_usd",
    "requested_exit_price",
    "actual_exit_fill",
    "exit_slippage_price",
    "exit_slippage_usd",
    "spread_at_entry",
    "spread_at_exit",
    "lot_size",
    "contract_size",
    "target_profit_usd",
    "stop_loss_usd",
    "maximum_favorable_excursion_usd",
    "maximum_adverse_excursion_usd",
    "hold_seconds",
    "realized_profit_usd",
    "exit_reason",
    "fill_type",
    "signal_direction",
    "signal_score",
    "signal_confidence",
    "signal_pattern",
    "microstructure_direction",
    "microstructure_confidence",
    "microstructure_data_quality",
    "meta_allowed",
    "meta_confidence",
    "meta_block_reasons",
]


_NUMERIC_AUDIT_FIELDS = {
    "decision_to_request_ms",
    "request_to_response_ms",
    "signal_bid",
    "signal_ask",
    "signal_spread",
    "requested_entry_price",
    "actual_entry_fill",
    "entry_slippage_price",
    "entry_slippage_usd",
    "requested_exit_price",
    "actual_exit_fill",
    "exit_slippage_price",
    "exit_slippage_usd",
    "spread_at_entry",
    "spread_at_exit",
    "lot_size",
    "contract_size",
    "target_profit_usd",
    "stop_loss_usd",
    "maximum_favorable_excursion_usd",
    "maximum_adverse_excursion_usd",
    "hold_seconds",
    "realized_profit_usd",
    "signal_score",
    "signal_confidence",
    "microstructure_confidence",
    "microstructure_data_quality",
    "meta_confidence",
}
_BOOLEAN_AUDIT_FIELDS = {"paper_only", "meta_allowed"}


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_audit_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give every Parquet batch a stable schema across ENTRY and EXIT rows."""
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for field in _AUDIT_FIELDS:
            value = row.get(field)
            if field in _NUMERIC_AUDIT_FIELDS:
                item[field] = _optional_float(value)
            elif field in _BOOLEAN_AUDIT_FIELDS:
                item[field] = bool(value)
            else:
                item[field] = "" if value is None else str(value)
        normalized.append(item)
    return normalized


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _utc_iso(value: datetime | str | None) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _milliseconds(start: datetime, end: datetime) -> float:
    return round(max(0.0, (end - start).total_seconds() * 1000.0), 3)


def _adverse_entry_slippage(direction: str, requested: float, actual: float) -> float:
    if direction == "BUY":
        return actual - requested
    if direction == "SELL":
        return requested - actual
    return 0.0


def _adverse_exit_slippage(direction: str, requested: float, actual: float) -> float:
    if direction == "BUY":
        return requested - actual
    if direction == "SELL":
        return actual - requested
    return 0.0


def _signal_context(signal: ScalpSignalState | None) -> dict[str, Any]:
    metrics = signal.metrics if signal and isinstance(signal.metrics, dict) else {}
    micro = metrics.get("microstructure", {}) if isinstance(metrics, dict) else {}
    meta = metrics.get("meta_controller", {}) if isinstance(metrics, dict) else {}
    return {
        "signal_direction": getattr(signal, "direction", "") if signal else "",
        "signal_score": getattr(signal, "score", 0.0) if signal else 0.0,
        "signal_confidence": getattr(signal, "confidence", 0.0) if signal else 0.0,
        "signal_pattern": getattr(signal, "pattern", "") if signal else "",
        "microstructure_direction": micro.get("direction", ""),
        "microstructure_confidence": micro.get("confidence", 0.0),
        "microstructure_data_quality": micro.get("data_quality", 0.0),
        "meta_allowed": meta.get("allowed", False),
        "meta_confidence": meta.get("confidence", 0.0),
        "meta_block_reasons": json.dumps(meta.get("block_reasons", []), ensure_ascii=False),
    }


class PaperExecutionAudit:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._writer = PartitionedParquetBuffer(
            scalping_settings.SCALPING_EXECUTION_AUDIT_PARQUET_ROOT,
            compression=scalping_settings.SCALPING_EXECUTION_AUDIT_PARQUET_COMPRESSION,
            max_rows=scalping_settings.SCALPING_EXECUTION_AUDIT_BUFFER_MAX_ROWS,
            flush_interval_seconds=scalping_settings.SCALPING_EXECUTION_AUDIT_FLUSH_INTERVAL_SECONDS,
            dataset_name="paper_execution_audit",
        )

    @staticmethod
    def _csv_path() -> str:
        return os.path.join(
            get_scalping_log_folder(),
            scalping_settings.SCALPING_EXECUTION_AUDIT_CSV_FILENAME,
        )

    def _append_csv(self, rows: list[dict[str, Any]]) -> str:
        path = self._csv_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        exists = os.path.exists(path) and os.path.getsize(path) > 0
        with open(path, "a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=_AUDIT_FIELDS, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in _AUDIT_FIELDS})
        return path

    def record_transition(
        self,
        before_trades: list[dict[str, Any]],
        after_trades: list[dict[str, Any]],
        *,
        snapshot: ScalpingSnapshotState,
        signal: ScalpSignalState | None,
        decision_timestamp: datetime,
        request_timestamp: datetime,
        response_timestamp: datetime,
    ) -> dict[str, Any]:
        if not bool(scalping_settings.SCALPING_EXECUTION_AUDIT_ENABLED):
            return {"enabled": False, "rows_appended": 0}

        with self._lock:
            before = {str(item.get("id")): item for item in before_trades if item.get("id")}
            after = {str(item.get("id")): item for item in after_trades if item.get("id")}
            context = _signal_context(signal)
            rows: list[dict[str, Any]] = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for trade_id, trade in after.items():
                previous = before.get(trade_id)
                previous_status = str(previous.get("status", "")).upper() if previous else ""
                status = str(trade.get("status", "")).upper()
                is_entry = previous is None
                is_exit = status == "CLOSED" and previous_status != "CLOSED"
                direction = str(trade.get("direction", "")).upper()
                lot = _safe_float(trade.get("lot_size"), scalping_settings.SCALPING_LOT_SIZE)
                contract = _safe_float(trade.get("contract_size"), snapshot.contract_size)

                if is_entry:
                    requested = snapshot.ask if direction == "BUY" else snapshot.bid
                    actual = _safe_float(trade.get("entry_price"))
                    slip = _adverse_entry_slippage(direction, requested, actual)
                    row = {
                        "audit_timestamp_utc": now_iso,
                        "event_type": "ENTRY",
                        "trade_id": trade_id,
                        "strategy_id": trade.get("strategy_id", scalping_settings.SCALPING_STRATEGY_ID),
                        "symbol": trade.get("symbol", snapshot.symbol),
                        "direction": direction,
                        "paper_only": True,
                        "decision_timestamp_utc": _utc_iso(decision_timestamp),
                        "order_request_timestamp_utc": _utc_iso(request_timestamp),
                        "broker_response_timestamp_utc": _utc_iso(response_timestamp),
                        "decision_to_request_ms": _milliseconds(decision_timestamp, request_timestamp),
                        "request_to_response_ms": _milliseconds(request_timestamp, response_timestamp),
                        "signal_bid": snapshot.bid,
                        "signal_ask": snapshot.ask,
                        "signal_spread": snapshot.spread,
                        "requested_entry_price": requested,
                        "actual_entry_fill": actual,
                        "entry_slippage_price": round(slip, 8),
                        "entry_slippage_usd": round(slip * lot * contract, 6),
                        "requested_exit_price": None,
                        "actual_exit_fill": None,
                        "exit_slippage_price": None,
                        "exit_slippage_usd": None,
                        "spread_at_entry": trade.get("entry_spread", snapshot.spread),
                        "spread_at_exit": None,
                        "lot_size": lot,
                        "contract_size": contract,
                        "target_profit_usd": trade.get("profit_target_usd", 0.0),
                        "stop_loss_usd": trade.get("stop_loss_usd", 0.0),
                        "maximum_favorable_excursion_usd": trade.get("max_favorable_excursion_usd", 0.0),
                        "maximum_adverse_excursion_usd": trade.get("max_adverse_excursion_usd", 0.0),
                        "hold_seconds": trade.get("hold_seconds", 0),
                        "realized_profit_usd": None,
                        "exit_reason": "",
                        "fill_type": "PAPER_MARKET_ENTRY",
                        **context,
                    }
                    rows.append(row)

                if is_exit:
                    requested = snapshot.bid if direction == "BUY" else snapshot.ask
                    actual = _safe_float(trade.get("close_price"), requested)
                    slip = _adverse_exit_slippage(direction, requested, actual)
                    row = {
                        "audit_timestamp_utc": now_iso,
                        "event_type": "EXIT",
                        "trade_id": trade_id,
                        "strategy_id": trade.get("strategy_id", scalping_settings.SCALPING_STRATEGY_ID),
                        "symbol": trade.get("symbol", snapshot.symbol),
                        "direction": direction,
                        "paper_only": True,
                        "decision_timestamp_utc": _utc_iso(decision_timestamp),
                        "order_request_timestamp_utc": _utc_iso(request_timestamp),
                        "broker_response_timestamp_utc": _utc_iso(response_timestamp),
                        "decision_to_request_ms": _milliseconds(decision_timestamp, request_timestamp),
                        "request_to_response_ms": _milliseconds(request_timestamp, response_timestamp),
                        "signal_bid": snapshot.bid,
                        "signal_ask": snapshot.ask,
                        "signal_spread": snapshot.spread,
                        "requested_entry_price": _optional_float(trade.get("entry_price")),
                        "actual_entry_fill": _optional_float(trade.get("entry_price")),
                        "entry_slippage_price": 0.0,
                        "entry_slippage_usd": 0.0,
                        "requested_exit_price": requested,
                        "actual_exit_fill": actual,
                        "exit_slippage_price": round(slip, 8),
                        "exit_slippage_usd": round(slip * lot * contract, 6),
                        "spread_at_entry": _optional_float(trade.get("entry_spread")),
                        "spread_at_exit": trade.get("last_spread", snapshot.spread),
                        "lot_size": lot,
                        "contract_size": contract,
                        "target_profit_usd": trade.get("profit_target_usd", 0.0),
                        "stop_loss_usd": trade.get("stop_loss_usd", 0.0),
                        "maximum_favorable_excursion_usd": trade.get("max_favorable_excursion_usd", 0.0),
                        "maximum_adverse_excursion_usd": trade.get("max_adverse_excursion_usd", 0.0),
                        "hold_seconds": trade.get("hold_seconds", 0),
                        "realized_profit_usd": trade.get("final_profit_usd", 0.0),
                        "exit_reason": trade.get("close_reason", ""),
                        "fill_type": trade.get("fill_type", ""),
                        **context,
                    }
                    rows.append(row)

            if not rows:
                return {
                    "enabled": True,
                    "rows_appended": 0,
                    "csv_path": self._csv_path(),
                    "storage": self._writer.status(buffered_only=True),
                }

            normalized_rows = _normalize_audit_rows(rows)
            csv_path = self._append_csv(normalized_rows)
            partition_date = response_timestamp.date().isoformat()
            storage = self._writer.append(
                normalized_rows,
                partition_date=partition_date,
                symbol=snapshot.symbol,
            )
            return {
                "enabled": True,
                "rows_appended": len(rows),
                "entry_events": sum(1 for row in rows if row["event_type"] == "ENTRY"),
                "exit_events": sum(1 for row in rows if row["event_type"] == "EXIT"),
                "csv_path": csv_path,
                "storage": storage,
            }

    def flush(self) -> dict[str, Any]:
        return self._writer.flush()


_AUDIT = PaperExecutionAudit()


def audit_paper_trade_transition(
    before_trades: list[dict[str, Any]],
    after_trades: list[dict[str, Any]],
    *,
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState | None,
    decision_timestamp: datetime,
    request_timestamp: datetime,
    response_timestamp: datetime,
) -> dict[str, Any]:
    return _AUDIT.record_transition(
        before_trades,
        after_trades,
        snapshot=snapshot,
        signal=signal,
        decision_timestamp=decision_timestamp,
        request_timestamp=request_timestamp,
        response_timestamp=response_timestamp,
    )


def flush_execution_audit() -> dict[str, Any]:
    return _AUDIT.flush()
