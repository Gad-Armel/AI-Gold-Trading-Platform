from __future__ import annotations

import csv
import json
import os
from glob import glob
from datetime import datetime
from typing import Any

from config import scalping_settings
from services.risk.scalping_risk_guard import get_scalping_log_folder
from services.utils.atomic_json import atomic_write_json


def get_demo_history_path() -> str:
    return os.path.join(get_scalping_log_folder(), str(scalping_settings.SCALPING_DEMO_HISTORY_FILENAME))


def get_demo_audit_csv_path() -> str:
    return os.path.join(get_scalping_log_folder(), str(scalping_settings.SCALPING_DEMO_AUDIT_CSV_FILENAME))


def load_demo_history() -> list[dict[str, Any]]:
    path = get_demo_history_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []



def load_all_demo_history() -> list[dict[str, Any]]:
    """Load controlled-demo journal rows across every date folder.

    V5.1.1 uses this for a cumulative loss session that must survive midnight
    and normal process restarts. Rows remain version-isolated by SCALPING_LOG_ROOT.
    """
    root = str(scalping_settings.SCALPING_LOG_ROOT)
    filename = str(scalping_settings.SCALPING_DEMO_HISTORY_FILENAME)
    candidates = {os.path.join(root, filename)}
    candidates.update(glob(os.path.join(root, "**", filename), recursive=True))
    rows: list[dict[str, Any]] = []
    for path in sorted(candidates):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            rows.extend(dict(item) for item in payload if isinstance(item, dict))
    return rows


def load_cumulative_demo_history() -> list[dict[str, Any]]:
    """Load demo history across versioned scalping log roots.

    Strategy performance remains version-isolated, but the user's cumulative
    -$100 safety session must not silently reset when code is upgraded. Keeping
    the existing ``logs`` directory therefore preserves all demo P/L since the
    session start, even when SCALPING_LOG_ROOT changes for a new release.
    """

    current_root = str(scalping_settings.SCALPING_LOG_ROOT)
    parent = os.path.dirname(current_root.rstrip("/\\")) or "logs"
    filename = str(scalping_settings.SCALPING_DEMO_HISTORY_FILENAME)
    candidates = {os.path.join(current_root, filename)}
    candidates.update(glob(os.path.join(current_root, "**", filename), recursive=True))
    candidates.update(glob(os.path.join(parent, "scalping_v*", "**", filename), recursive=True))

    deduplicated: dict[str, dict[str, Any]] = {}
    for path in sorted(candidates):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue
        for row_index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            stable_ticket = (
                row.get("position_ticket")
                or row.get("deal_ticket")
                or row.get("order_ticket")
            )
            key = (
                str(stable_ticket)
                if stable_ticket
                else "|".join(
                    [
                        str(path),
                        str(row_index),
                        str(row.get("opened_at", "")),
                        str(row.get("closed_at", "")),
                        str(row.get("direction", "")),
                        str(row.get("entry_price", "")),
                        str(row.get("final_profit_usd", "")),
                    ]
                )
            )
            existing = deduplicated.get(key)
            if existing is None or (
                str(row.get("status", "")).upper() == "CLOSED"
                and str(existing.get("status", "")).upper() != "CLOSED"
            ):
                deduplicated[key] = row
    return list(deduplicated.values())

def save_demo_history(history: list[dict[str, Any]]) -> str:
    return atomic_write_json(get_demo_history_path(), history, indent=2)


def _append_audit_csv(record: dict[str, Any]) -> str:
    path = get_demo_audit_csv_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    flat = {}
    for key, value in record.items():
        flat[key] = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list, tuple)) else value
    fields = [
        "recorded_at", "record_type", "status", "strategy_id", "symbol", "direction",
        "opened_at", "closed_at", "position_ticket", "order_ticket", "deal_ticket",
        "entry_price", "actual_entry_fill", "entry_slippage_price", "entry_slippage_usd",
        "entry_slippage_warning", "target_price", "stop_price", "volume",
        "signal_score", "signal_pattern", "entry_quality_index", "entry_profile",
        "spread_policy", "signal_persistence", "execution_preflight", "order_check",
        "decision_to_request_ms", "request_to_response_ms", "retcode", "broker_comment",
        "final_profit_usd", "close_reason", "hold_seconds", "request",
    ]
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: flat.get(field, "") for field in fields})
    return path


def append_demo_record(record: dict[str, Any]) -> str:
    history = load_demo_history()
    item = dict(record)
    item.setdefault("recorded_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    history.append(item)
    path = save_demo_history(history)
    _append_audit_csv(item)
    return path


def upsert_demo_position(position_ticket: int, updates: dict[str, Any]) -> str:
    history = load_demo_history()
    ticket_text = str(position_ticket)
    matched = False
    updated_item: dict[str, Any] = {}
    for item in history:
        if str(item.get("position_ticket", "")) == ticket_text:
            item.update(updates)
            updated_item = dict(item)
            matched = True
            break
    if not matched:
        updated_item = {"position_ticket": position_ticket, **updates}
        history.append(updated_item)
    path = save_demo_history(history)
    _append_audit_csv(updated_item)
    return path
