from __future__ import annotations

import argparse
import json

from config import scalping_settings
from services.research.medium_forward_dataset import forward_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Show sealed forward-cohort coverage without inspecting outcomes.")
    parser.add_argument("--symbol", default=scalping_settings.SCALPING_SYMBOL)
    parser.add_argument("--root", default="data/research/medium_horizon/forward")
    args = parser.parse_args()
    print(json.dumps(forward_readiness(args.root, args.symbol), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
