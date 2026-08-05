from __future__ import annotations

import time
from datetime import datetime, timezone

from config import scalping_settings
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.analysis.cross_market_context import build_cross_market_context
from services.research.medium_horizon_shadow import medium_horizon_metrics, update_medium_horizon_shadow
from services.risk.news_event_filter import assess_news_event_risk


def _metrics_line(label: str, values: dict) -> str:
    return (
        f"{label}: trades={values['trades']} wins={values['wins']} losses={values['losses']} "
        f"WR={values['win_rate']:.1%} net=${values['net_profit']:+.2f} "
        f"expectancy=${values['expectancy']:+.3f} PF={values['profit_factor']:.2f}"
    )


def run_medium_horizon_shadow_loop(symbol: str, *, max_minutes: float = 0.0) -> None:
    started = datetime.now(timezone.utc)
    deadline = time.monotonic() + max_minutes * 60.0 if max_minutes > 0 else None
    cycle = 0
    print("=" * 78)
    print("MEDIUM-HORIZON MTF MODEL — SHADOW ONLY / NO BROKER ORDERS")
    print("Views: closed M45 + H1 + H2 + H4; entry requires 3-of-4 agreement")
    print(
        f"Target=${scalping_settings.SCALPING_MEDIUM_TARGET_USD:.2f} "
        f"Hard stop=${scalping_settings.SCALPING_MEDIUM_HARD_STOP_USD:.2f} "
        f"Max positions={scalping_settings.SCALPING_MEDIUM_MAX_OPEN_POSITIONS} "
        "Daily entry cap=NONE"
    )
    print(
        "Entry approval: "
        f"{'ENABLED' if scalping_settings.SCALPING_MEDIUM_ENTRY_ENABLED else 'BLOCKED — failed historical validation'}"
    )
    print("=" * 78)
    try:
        while deadline is None or time.monotonic() < deadline:
            cycle += 1
            try:
                snapshot = get_scalping_snapshot(symbol)
                news_risk = assess_news_event_risk(
                    symbol=symbol,
                    current_time=snapshot.timestamp.replace(tzinfo=None),
                )
                cross_market = build_cross_market_context()
                result = update_medium_horizon_shadow(
                    snapshot,
                    news_risk=news_risk,
                    cross_market=cross_market,
                )
                if result["action"] in {"OPEN", "CLOSE"} or cycle == 1 or cycle % 30 == 0:
                    analysis = result["analysis"]
                    directions = ", ".join(
                        f"{name}={view['direction']}" for name, view in analysis["views"].items()
                    )
                    print(
                        f"Cycle {cycle} | Bid={snapshot.bid:.5f} Ask={snapshot.ask:.5f} "
                        f"Spread={snapshot.spread:.3f} | {directions} | "
                        f"consensus={analysis['direction']} | open={len(result['positions'])}"
                    )
                    if result["opened"]:
                        trade = result["opened"]
                        print(f"Opened {trade['direction']} shadow at {trade['entry_price']:.5f}.")
                    for trade in result["closed"]:
                        print(
                            f"Closed {trade['direction']} ${trade['final_profit_usd']:+.2f}: "
                            f"{trade['close_reason']}."
                        )
                    if result["action"] == "WAIT":
                        print("Blocked: " + "; ".join(result["block_reasons"]))
                    print(_metrics_line("Session", medium_horizon_metrics(since=started)))
            except Exception as error:
                print(f"Medium-horizon cycle error: {type(error).__name__}: {error}")
            time.sleep(float(scalping_settings.SCALPING_MEDIUM_LOOP_INTERVAL_SECONDS))
    except KeyboardInterrupt:
        print("Medium-horizon shadow model stopped with CTRL+C.")
    finally:
        print(_metrics_line("Session", medium_horizon_metrics(since=started)))
        print(_metrics_line("Cumulative", medium_horizon_metrics()))
