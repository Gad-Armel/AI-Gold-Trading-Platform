from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from config import scalping_settings
from services.bot.v6_shadow_cycle_runner import run_v6_shadow_cycle
from services.microstructure.feature_store import flush_microstructure_features
from services.microstructure.tick_recorder import flush_tick_recorder
from services.research.v6_lane_review import build_v6_session_summary, format_v6_session_summary


def _lane_summary(gate: dict[str, Any]) -> str:
    model_text = ""
    if str(gate.get("lane", "")).upper() == "LEARNED":
        probability = float(gate.get("model_probability_win", 0.0) or 0.0)
        threshold = gate.get("model_probability_threshold")
        model_text = f" pwin={probability:.2f}/{float(threshold or 0.0):.2f}"
    return (
        f"{gate['lane']}={'PASS' if gate['allowed'] else 'WAIT'} "
        f"score={gate['winner_score']:.1f} margin={gate['score_margin']:.1f} "
        f"micro={gate['micro_direction']}/{gate['micro_confidence']:.2f} "
        f"persist={gate['persistence_cycles']}/{gate['required_persistence_cycles']}" + model_text
    )


def run_v6_shadow_loop(symbol: str, *, max_minutes: float = 0.0, mt5_module: Any | None = None) -> None:
    print("\n" + "=" * 78)
    print("V6.3.6 TICK-HORIZON FAST SHADOW RESEARCH — NO BROKER ORDERS")
    print("=" * 78)
    print(f"Symbol: {symbol} | STRICT executable hypothesis spread <= ${scalping_settings.SCALPING_V6_MAX_SPREAD_USD:.2f}")
    print("Research lanes: STRICT, FAST, BALANCED, EXPLORATORY and calibrated LEARNED")
    print(
        f"Adaptive barriers: target=${scalping_settings.SCALPING_V63_TARGET_MIN_USD:.2f}-${scalping_settings.SCALPING_V63_TARGET_MAX_USD:.2f} "
        f"| stop=${scalping_settings.SCALPING_V63_STOP_MIN_USD:.2f}-${scalping_settings.SCALPING_V63_STOP_MAX_USD:.2f} "
        f"| max hold={scalping_settings.SCALPING_V6_MAX_HOLD_SECONDS}s"
    )
    print(f"Learned target: calibrated OOS win rate >= {scalping_settings.SCALPING_V63_TARGET_WIN_RATE*100:.0f}% with positive expectancy.")
    print(f"Chart intelligence: HTF trend + support/resistance + objective order blocks; strict consensus >= {scalping_settings.SCALPING_V6_STRUCTURE_MIN_VOTES}/3")
    print("Frozen quotes pause analysis automatically. No MT5 order_send call is reachable from this runner.")
    print("=" * 78)
    started = time.monotonic()
    session_started_at = datetime.now(timezone.utc)
    cycle = 0
    last_tick_msc = None
    last_stale_log = 0.0
    try:
        while True:
            if max_minutes > 0 and time.monotonic() - started >= max_minutes * 60:
                print("Shadow session time limit reached.")
                break
            result = run_v6_shadow_cycle(symbol, mt5_module=mt5_module)
            cycle += 1
            if bool(result.get("feed_paused", False)):
                now = time.monotonic()
                if now - last_stale_log >= float(scalping_settings.SCALPING_V6_FEED_PAUSE_LOG_INTERVAL_SECONDS):
                    snapshot = result["snapshot"]
                    print(
                        f"Shadow Feed Paused | Bid={snapshot.bid:.5f} Ask={snapshot.ask:.5f} "
                        f"Spread={snapshot.spread:.3f} | {result['reason']}"
                    )
                    last_stale_log = now
                time.sleep(float(scalping_settings.SCALPING_V6_FEED_PAUSE_SLEEP_SECONDS))
                continue

            snapshot = result["snapshot"]
            lane_gates = result["v6_lane_gates"]
            shadow_lanes = result["shadow_lanes"]
            notable = bool(shadow_lanes.get("opened_lanes") or shadow_lanes.get("closed_lanes"))
            if notable or cycle % 20 == 0:
                strict = lane_gates["STRICT"]
                print(
                    f"Shadow Cycle {cycle} | Bid={snapshot.bid:.5f} Ask={snapshot.ask:.5f} Spread={snapshot.spread:.3f} | "
                    f"direction={strict['direction']} structure={strict.get('structure_direction','NEUTRAL')}/"
                    f"{strict.get('structure_votes',0)}/3"
                )
                lane_names = [name for name in ("STRICT", "FAST", "BALANCED", "EXPLORATORY", "LEARNED") if name in lane_gates]
                print("Lanes: " + " | ".join(_lane_summary(lane_gates[name]) for name in lane_names))
                for name in lane_names:
                    gate = lane_gates[name]
                    lane_result = shadow_lanes["lanes"][name]
                    if gate["failed_checks"]:
                        print(f"{name} blocks: " + ", ".join(gate["failed_checks"]))
                    if lane_result["action"] != "NO_ACTION":
                        print(f"{name} shadow: {lane_result['message']}")
                print("Structure: " + str(strict.get("structure_reason", "")))
                market_map = result.get("market_map", {})
                if market_map.get("rendered"):
                    print("Market map: " + str(market_map.get("path")))
                if shadow_lanes.get("closed_lanes"):
                    print(format_v6_session_summary(build_v6_session_summary(session_started_at)))

            tick_msc = int(getattr(snapshot, "tick_time_msc", 0) or 0)
            interval = 0.10 if shadow_lanes.get("any_open_trade") else float(scalping_settings.SCALPING_LOOP_INTERVAL_SECONDS)
            if last_tick_msc == tick_msc:
                interval = max(interval, 0.25)
            last_tick_msc = tick_msc
            time.sleep(interval)
    except KeyboardInterrupt:
        print("V6.3.6 shadow loop stopped with CTRL+C.")
    finally:
        ticks = flush_tick_recorder()
        features = flush_microstructure_features()
        print(f"Research flush: ticks={ticks.get('flushed_rows',0)} features={features.get('flushed_rows',0)}")
        print(format_v6_session_summary(build_v6_session_summary(session_started_at)))
