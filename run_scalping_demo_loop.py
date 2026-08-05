from __future__ import annotations

import argparse

from config import scalping_settings
from services.bot.scalping_config_validator import print_scalping_config_report
from services.bot.scalping_demo_loop_runner import run_scalping_demo_loop
from services.bot.scalping_demo_preflight import build_demo_preflight, print_demo_preflight
from services.bot.scalping_instance_lock import ScalpingInstanceAlreadyRunning, ScalpingInstanceLock
from services.bot.scalping_system_auditor import print_scalping_system_audit
from services.execution.demo_session_guard import arm_demo_session, disarm_demo_session
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.risk.demo_loss_session import prepare_demo_loss_session


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V6 controlled-demo XAUUSD only after a valid shadow walk-forward approval.")
    parser.add_argument("--confirm", required=True, help="Exact demo-risk confirmation token.")
    parser.add_argument("--max-minutes", type=float, default=float(scalping_settings.SCALPING_DEMO_MAX_SESSION_MINUTES))
    parser.add_argument(
        "--reset-loss-session",
        action="store_true",
        help="Explicitly reset the persistent cumulative demo P/L to zero before launch.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    config = print_scalping_config_report()
    if not config["valid"]:
        print("Demo startup blocked because configuration is invalid.")
        return 1
    audit = print_scalping_system_audit()
    if not audit["passed"]:
        print("Demo startup blocked because the system audit failed.")
        return 1

    lock = ScalpingInstanceLock()
    try:
        lock.acquire()
    except ScalpingInstanceAlreadyRunning as error:
        print(f"Demo startup blocked: {error}")
        return 1

    try:
        if not connect_mt5():
            return 1
        try:
            import MetaTrader5 as mt5
            preflight = build_demo_preflight(mt5, scalping_settings.SCALPING_SYMBOL)
            print_demo_preflight(preflight)
            if not preflight["passed"]:
                print("No order was sent.")
                return 1
            loss_session = prepare_demo_loss_session(
                mt5.account_info(), reset=bool(args.reset_loss_session)
            )
            print(
                f"Cumulative loss session: {loss_session.get('reason', '')}"
            )
            state = loss_session.get("state", {}) or {}
            print(
                f"Loss-session start: {state.get('started_at')} | "
                f"limit=-${float(state.get('loss_limit_usd', scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD)):.2f}"
            )
            if not loss_session.get("allowed", False):
                print(
                    "Demo startup blocked. To intentionally begin from zero, rerun the same command with --reset-loss-session."
                )
                return 1
            armed = arm_demo_session(args.confirm, mt5.account_info(), mt5)
            if not armed.get("armed"):
                print(f"Demo startup blocked: {armed.get('reason', '')}")
                return 1
            print(f"Demo session armed for login {armed.get('account_login')} on {armed.get('account_server')}.")
            run_scalping_demo_loop(scalping_settings.SCALPING_SYMBOL, max_minutes=args.max_minutes, mt5_module=mt5)
            return 0
        finally:
            disarm_demo_session()
            disconnect_mt5()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
