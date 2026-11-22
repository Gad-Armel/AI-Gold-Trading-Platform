from __future__ import annotations

import argparse
import sys


CONFIRMATION = "I_ACCEPT_DEMO_SCALPING_RISK"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V-FINAL demo launcher: Gold Advisor consensus execution + automatic dashboard."
    )
    parser.add_argument("--confirm", default="", help=f"Required for demo execution: {CONFIRMATION}")
    parser.add_argument("--interval", type=float, default=2.0, help="Gold bot loop interval in seconds.")
    parser.add_argument("--max-minutes", type=float, default=0.0)
    parser.add_argument("--dashboard-port", type=int, default=8777)
    parser.add_argument("--api-refresh-seconds", type=float, default=60.0)
    parser.add_argument("--all-horizons", action="store_true", help="Also run INTRADAY and SWING; default is SCALP only.")
    parser.add_argument("--no-dashboard", action="store_true")
    args = parser.parse_args()

    if args.confirm != CONFIRMATION:
        print("DEMO START BLOCKED: explicit confirmation is required.")
        print(f'Run: python run_vfinal_demo.py --confirm "{CONFIRMATION}"')
        return 2

    # The old V-FINAL demo executor is intentionally not used.  The production
    # demo path is the existing Gold Advisor consensus engine, which already
    # has the account guard, news protection, execution audit and live dashboard.
    from config import gold_consensus_settings as settings
    from run_gold_consensus_bot import main as gold_consensus_main

    settings.LOOP_INTERVAL_SECONDS = max(0.5, float(args.interval))
    settings.MAX_SPREAD_USD = min(float(getattr(settings, "MAX_SPREAD_USD", 0.27)), 0.27)
    settings.MAX_SESSION_LOSS_USD = min(float(getattr(settings, "MAX_SESSION_LOSS_USD", 25.0)), 25.0)
    settings.MAX_POSITION_SLOTS = 1

    if not args.all_horizons:
        settings.HORIZON_LANES = {"SCALP": dict(settings.HORIZON_LANES["SCALP"], max_positions=1)}
    else:
        settings.HORIZON_LANES = {
            name: dict(value, max_positions=1)
            for name, value in settings.HORIZON_LANES.items()
        }

    forwarded = [
        "run_gold_consensus_bot.py", "--mode", "demo",
        "--confirm", args.confirm,
        "--max-minutes", str(args.max_minutes),
        "--api-refresh-seconds", str(args.api_refresh_seconds),
        "--dashboard-port", str(args.dashboard_port),
    ]
    if args.no_dashboard:
        forwarded.append("--no-dashboard")
    sys.argv = forwarded
    return int(gold_consensus_main())


if __name__ == "__main__":
    raise SystemExit(main())
