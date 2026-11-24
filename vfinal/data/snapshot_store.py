from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import SNAPSHOTS, ensure_dirs
from ..schema import Snapshot


def append_snapshot(snapshot: Snapshot, path: str | Path | None = None) -> Path:
    ensure_dirs()
    target = Path(path) if path else SNAPSHOTS / "market_snapshots.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot.to_dict(), ensure_ascii=False, default=str) + "\n")
    return target


def load_snapshots(path: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(path) if path else SNAPSHOTS / "market_snapshots.jsonl"
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except json.JSONDecodeError:
            continue
    return rows
