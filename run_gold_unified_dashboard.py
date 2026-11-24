"""Launch the unified Gold dashboard command center."""
from __future__ import annotations

import argparse
from pathlib import Path
import webbrowser

from services.dashboard.gold_unified_web import create_unified_server
from services.dashboard.gold_scalp_support import AdvisorSupport
from services.dashboard.gold_scalp_web import default_feed_directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--feed-directory")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-advisor", action="store_true", help="Do not supervise the read-only Advisor 1 report bridge.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    directory = Path(args.feed_directory) if args.feed_directory else default_feed_directory()
    try:
        server = create_unified_server(directory, args.port)
    except (OSError, ValueError) as error:
        print(f"Unified dashboard startup failed: {error}")
        return 1
    support = AdvisorSupport(directory, with_advisor=not args.no_advisor)
    server.advisor_support = support
    support.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Gold Unified Command Center: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("Unified dashboard stopped.")
    finally:
        server.server_close()
        support.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
