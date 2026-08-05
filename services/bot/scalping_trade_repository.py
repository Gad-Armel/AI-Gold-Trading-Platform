from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Iterable

from config import scalping_settings


_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_trade_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    for date_format in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def get_scalping_log_root() -> str:
    return str(getattr(scalping_settings, "SCALPING_LOG_ROOT", "logs/scalping"))


def find_scalping_trade_files() -> list[str]:
    """Return every scalping JSON trade journal under the configured log tree."""

    root = get_scalping_log_root()
    file_name = str(
        getattr(
            scalping_settings,
            "SCALPING_TRADES_FILENAME",
            "scalp_paper_trades.json",
        )
    )

    matches: list[str] = []
    if not os.path.exists(root):
        return matches

    direct_path = os.path.join(root, file_name)
    if os.path.isfile(direct_path):
        matches.append(direct_path)

    for current_root, _, files in os.walk(root):
        if file_name in files:
            path = os.path.join(current_root, file_name)
            if path not in matches:
                matches.append(path)

    return sorted(matches)


def load_trade_file(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    trades: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        trade = dict(item)
        trade.setdefault("source_file", path)
        trades.append(trade)
    return trades


def trade_identity(trade: dict[str, Any]) -> str:
    explicit_id = str(trade.get("id", "")).strip()
    if explicit_id:
        return explicit_id

    return "|".join(
        [
            str(trade.get("strategy_id", "")),
            str(trade.get("symbol", "")),
            str(trade.get("direction", "")),
            str(trade.get("opened_at", "")),
            str(trade.get("entry_price", "")),
        ]
    )


def load_all_scalping_trades() -> list[dict[str, Any]]:
    """Load and deduplicate paper scalps across every dated log folder."""

    deduplicated: dict[str, dict[str, Any]] = {}
    for file_path in find_scalping_trade_files():
        for trade in load_trade_file(file_path):
            identity = trade_identity(trade)
            if not identity:
                continue

            existing = deduplicated.get(identity)
            if existing is None:
                deduplicated[identity] = trade
                continue

            # Prefer the record with a close timestamp and the most complete data.
            existing_score = sum(value not in (None, "", []) for value in existing.values())
            candidate_score = sum(value not in (None, "", []) for value in trade.values())
            existing_closed = bool(str(existing.get("closed_at", "")).strip())
            candidate_closed = bool(str(trade.get("closed_at", "")).strip())

            if candidate_closed and not existing_closed:
                deduplicated[identity] = trade
            elif candidate_closed == existing_closed and candidate_score > existing_score:
                deduplicated[identity] = trade

    return sorted(
        deduplicated.values(),
        key=lambda item: (
            parse_trade_time(item.get("opened_at")) or datetime.min,
            trade_identity(item),
        ),
    )


def filter_strategy_trades(
    trades: Iterable[dict[str, Any]],
    strategy_id: str | None = None,
) -> list[dict[str, Any]]:
    expected = str(
        strategy_id
        or getattr(scalping_settings, "SCALPING_STRATEGY_ID", "XAUUSD_SCALP_V1")
    )
    return [
        dict(trade)
        for trade in trades
        if str(trade.get("strategy_id", expected)) == expected
    ]


def split_trade_statuses(
    trades: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    closed: list[dict[str, Any]] = []
    opened: list[dict[str, Any]] = []

    for trade in trades:
        status = str(trade.get("status", "")).upper()
        if status == "CLOSED":
            closed.append(dict(trade))
        elif status == "OPEN":
            opened.append(dict(trade))

    return closed, opened


def trade_profit(trade: dict[str, Any]) -> float:
    return _safe_float(trade.get("final_profit_usd"), 0.0)
