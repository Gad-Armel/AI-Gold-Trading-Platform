from __future__ import annotations

"""Report local Python modules reachable from supported project entry points."""

import ast
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = (
    "run_gold_ai.py",
    "run_gold_source_advisor.py",
    "run_gold_advisor.py",
    "run_gold_consensus_bot.py",
    "run_gold_consensus_health_check.py",
    "run_gold_economic_advisor_v5.py",
    "run_gold_unified_dashboard.py",
    "run_vfinal.py",
    "run_vfinal_demo.py",
)


def module_index() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", "__pycache__", "integration_patch"} for part in path.parts):
            continue
        relative = path.relative_to(ROOT)
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        result[".".join(parts)] = path
    return result


def imports(path: Path, index: dict[str, Path]) -> set[Path]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, SyntaxError):
        return set()
    found: set[Path] = set()
    current = list(path.relative_to(ROOT).with_suffix("").parts[:-1])
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = current[:max(0, len(current) - max(0, node.level - 1))] if node.level else []
            prefix = ".".join(base + ([node.module] if node.module else []))
            names.append(prefix)
            names.extend(f"{prefix}.{alias.name}".strip(".") for alias in node.names)
        for name in names:
            probe = name
            while probe:
                if probe in index:
                    found.add(index[probe])
                    break
                probe = probe.rpartition(".")[0]
    return found


def main() -> int:
    index = module_index()
    queue = deque(ROOT / item for item in ENTRYPOINTS if (ROOT / item).exists())
    reachable: set[Path] = set(queue)
    while queue:
        for dependency in imports(queue.popleft(), index):
            if dependency not in reachable:
                reachable.add(dependency)
                queue.append(dependency)
    all_sources = {path for path in index.values() if not any(part == "tests" for part in path.parts)
                   and not path.name.startswith("test_")}
    print("REACHABLE")
    for path in sorted(reachable):
        print(path.relative_to(ROOT).as_posix())
    print("\nUNREACHABLE")
    for path in sorted(all_sources - reachable):
        print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
