from __future__ import annotations

import time
from datetime import datetime, timezone

from config import scalping_settings
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.research.candle_follow_shadow import candle_follow_metrics, update_candle_follow_shadow


def _summary(label: str, metrics: dict) -> str:
    return (
        f"{label}: trades={metrics['trades']} wins={metrics['wins']} losses={metrics['losses']} "
        f"WR={metrics['win_rate']*100:.1f}% net=${metrics['net_profit']:+.2f} "
        f"expectancy=${metrics['expectancy']:+.3f} PF={metrics['profit_factor']:.2f}"
    )


def run_candle_follow_shadow_loop(symbol: str, *, max_minutes: float = 0.0) -> None:
    print("\n" + "=" * 78)
    print("M1 CANDLE-FOLLOW BENCHMARK — SHADOW ONLY / NO BROKER ORDERS")
    print("Rule: live M1 candle green=SELL, red=BUY, doji=WAIT; re-entry allowed after every close")
    print(
        f"Target=${scalping_settings.SCALPING_CANDLE_FOLLOW_TARGET_USD:.2f} "
        f"Stop=${scalping_settings.SCALPING_CANDLE_FOLLOW_STOP_USD:.2f} "
        f"Max hold={scalping_settings.SCALPING_CANDLE_FOLLOW_MAX_HOLD_SECONDS:.0f}s"
    )
    print("=" * 78)
    started = time.monotonic()
    session_started = datetime.now(timezone.utc)
    last_action = ""
    try:
        while True:
            if max_minutes > 0 and time.monotonic() - started >= max_minutes * 60:
                break
            snapshot = get_scalping_snapshot(symbol)
            if snapshot.quote_age_seconds > float(scalping_settings.SCALPING_CANDLE_FOLLOW_MAX_QUOTE_AGE_SECONDS):
                time.sleep(1.0)
                continue
            result = update_candle_follow_shadow(snapshot)
            action = str(result["action"])
            if action in {"OPEN", "CLOSE", "DOJI"} or (action == "MONITOR" and action != last_action):
                print(result["message"])
            if action == "CLOSE":
                print(_summary("Session", candle_follow_metrics(since=session_started)))
            last_action = action
            time.sleep(float(scalping_settings.SCALPING_CANDLE_FOLLOW_LOOP_SECONDS))
    except KeyboardInterrupt:
        print("Candle-follow benchmark stopped with CTRL+C.")
    finally:
        print(_summary("Session", candle_follow_metrics(since=session_started)))
        print(_summary("Cumulative", candle_follow_metrics()))
