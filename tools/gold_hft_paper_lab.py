"""Command-line entry point for the paper-only quote replay lab."""
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from services.hft.paper_replay import (
    OpenPaperPosition,
    PaperTrade,
    PendingEntry,
    Quote,
    load_quotes,
    main,
    replay,
)

__all__ = [
    "OpenPaperPosition",
    "PaperTrade",
    "PendingEntry",
    "Quote",
    "load_quotes",
    "replay",
]


if __name__ == "__main__":
    raise SystemExit(main())
