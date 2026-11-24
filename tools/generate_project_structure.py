from __future__ import annotations

"""Generate a compact, shareable map of the repository.

Large datasets, secrets, Git internals and generated caches are summarized or
excluded so the output can safely be given to another coding assistant.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_DIRS = {".git", ".agents", ".codex", ".claude", ".mt5-validation", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SUMMARIZED_DIRS = {"data", "logs", "research_outputs"}
SECRET_FILES = {".env"}
EXCLUDED_SUFFIXES = {".zip"}


def _tree(folder: Path, prefix: str = "") -> list[str]:
    lines: list[str] = []
    entries = sorted((item for item in folder.iterdir()
                      if item.name not in EXCLUDED_DIRS and item.suffix.lower() not in EXCLUDED_SUFFIXES),
                     key=lambda item: (not item.is_dir(), item.name.lower()))
    for index, item in enumerate(entries):
        branch = "`-- " if index == len(entries) - 1 else "|-- "
        if item.name in SECRET_FILES:
            lines.append(f"{prefix}{branch}{item.name} [SECRET - contents excluded]")
            continue
        if item.is_dir() and item.name in SUMMARIZED_DIRS:
            files = [entry for entry in item.rglob("*") if entry.is_file()]
            size = sum(entry.stat().st_size for entry in files)
            extensions = Counter(entry.suffix.lower() or "[none]" for entry in files)
            summary = ", ".join(f"{ext}:{count}" for ext, count in extensions.most_common(5))
            lines.append(f"{prefix}{branch}{item.name}/ [summarized: {len(files)} files, {size / 1048576:.1f} MB; {summary}]")
            continue
        lines.append(f"{prefix}{branch}{item.name}{'/' if item.is_dir() else ''}")
        if item.is_dir():
            extension = "    " if index == len(entries) - 1 else "|   "
            lines.extend(_tree(item, prefix + extension))
    return lines


def generate(root: Path, output: Path) -> None:
    root = root.resolve()
    entrypoints = sorted(path.name for path in root.glob("run_*.py"))
    tests = sorted(str(path.relative_to(root)).replace("\\", "/") for path in root.rglob("test_*.py")
                   if not any(part in EXCLUDED_DIRS for part in path.parts))
    content = [
        "# Project structure (generated)", "",
        f"Updated UTC: {datetime.now(timezone.utc).isoformat()}", "",
        "Regenerate with: `python tools/generate_project_structure.py`", "",
        "Safety: `.env` contents, Git internals, caches, release archives, and individual large data files are excluded.", "",
        "## Active entry points", "", *[f"- `{name}`" for name in entrypoints], "",
        "## Tests", "", *[f"- `{name}`" for name in tests], "",
        "## Folder tree", "", "```text", f"{root.name}/", *_tree(root), "```", "",
    ]
    output.write_text("\n".join(content), encoding="utf-8")


def refresh_project_structure(root: Path | None = None) -> Path:
    """Refresh the map without exposing secrets; safe to call at app startup."""
    project_root = (root or Path(__file__).resolve().parents[1]).resolve()
    output = project_root / "PROJECT_STRUCTURE.md"
    generate(project_root, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate the shareable project structure map.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="PROJECT_STRUCTURE.md")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    generate(root, output)
    print(f"Updated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
