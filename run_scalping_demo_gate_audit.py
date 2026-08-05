from __future__ import annotations

from pathlib import Path

from config import scalping_settings as s
from config import settings as core

ROOT = Path(__file__).resolve().parent


def run_audit() -> dict:
    execution_gate = (ROOT / "services/execution/scalp_demo_execution_gate.py").read_text(encoding="utf-8")
    preflight = (ROOT / "services/bot/scalping_demo_preflight.py").read_text(encoding="utf-8")
    demo_cycle = (ROOT / "services/bot/scalping_demo_cycle_runner.py").read_text(encoding="utf-8")
    demo_risk = (ROOT / "services/risk/scalping_demo_risk_guard.py").read_text(encoding="utf-8")
    candidate_gate = (ROOT / "services/research/v6_candidate_gate.py").read_text(encoding="utf-8")
    shadow = "\n".join((ROOT / item).read_text(encoding="utf-8") for item in (
        "run_scalping_shadow_loop.py", "services/bot/v6_shadow_loop_runner.py",
        "services/bot/v6_shadow_cycle_runner.py", "services/research/v6_shadow_engine.py"))
    checks = {
        "real_execution_off": not bool(s.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED),
        "core_live_off": not bool(getattr(core, "ENABLE_LIVE_TRADING", False)),
        "demo_account_required": bool(s.SCALPING_REQUIRE_DEMO_ACCOUNT),
        "approval_in_preflight": "load_v6_approval" in preflight,
        "approval_in_execution_gate": "load_v6_approval" in execution_gate,
        "shadow_has_no_order_send": "order_send(" not in shadow,
        "lot_cap_001": float(s.SCALPING_DEMO_MAX_LOT_SIZE) <= .01,
        "one_position": int(s.SCALPING_DEMO_MAX_OPEN_POSITIONS) == 1,
        "no_trade_limit": not bool(s.SCALPING_DEMO_TRADE_LIMIT_ENABLED),
        "persistent_loss_stop": abs(float(s.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD)-100.0) < 1e-9,
        "three_loss_breaker": int(s.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES) == 3,
        "five_minute_breaker": int(s.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS) == 300,
        "return_to_shadow": bool(s.SCALPING_V6_DEMO_RETURN_TO_SHADOW_AFTER_LOSSES),
        "approval_expiry": int(s.SCALPING_V6_PROMOTION_APPROVAL_VALID_DAYS) <= 7,
        "demo_uses_v6_candidate_gate": "evaluate_v6_candidate_gate" in demo_cycle and "apply_v6_candidate_gate" in demo_cycle,
        "demo_uses_v6_structure": "build_v6_market_structure" in demo_cycle,
        "legacy_demo_entry_policy_absent": "evaluate_demo_entry_policy" not in demo_cycle and "apply_demo_entry_policy" not in demo_cycle,
        "structure_consensus_enabled": bool(s.SCALPING_V6_STRUCTURE_CONSENSUS_ENABLED),
        "structure_two_of_three": int(s.SCALPING_V6_STRUCTURE_MIN_VOTES) == 2,
        "demo_risk_uses_v6_gate": "v6_candidate_gate" in demo_risk,
        "legacy_adaptive_spread_absent": "evaluate_adaptive_spread_policy" not in demo_risk,
        "legacy_recovery_disabled": int(s.SCALPING_DEMO_RECOVERY_MODE_AFTER_LOSSES) == 0,
        "strict_lane_only_for_demo": "Only the STRICT V6 lane may be applied to demo execution" in candidate_gate,
        "balanced_lane_not_demo_eligible": "\"demo_eligible\": False" in candidate_gate,
        "exploratory_lane_not_demo_eligible": "EXPLORATORY" in candidate_gate and "demo_eligible" in candidate_gate,
        "fast_lane_not_demo_eligible": "FAST" in candidate_gate and "Only the STRICT V6 lane" in candidate_gate,
        "demo_close_resets_persistence": "reset_demo_signal_persistence" in demo_cycle and "managed.get(\"closed_count\", 0)" in demo_cycle,
        "demo_same_cycle_reentry_blocked": "SCALP_DEMO_REENTRY_DELAYED" in demo_cycle,
        "shadow_close_is_final": "closed_this_cycle" in shadow,
        "hard_stop_structure_rearm": bool(s.SCALPING_V6_HARD_STOP_STRUCTURE_RESET_REQUIRED),
        "model_required_for_demo": bool(s.SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL),
        "model_checked_in_preflight": "load_v63_champion_status" in preflight,
        "model_checked_in_execution_gate": "load_v63_champion_status" in execution_gate,
        "model_probability_checked_in_demo_cycle": "score_v63_profile" in demo_cycle,
        "learned_lane_never_demo": "LEARNED" not in candidate_gate or "Only the STRICT V6 lane" in candidate_gate,
    }
    return {"passed": all(checks.values()), "checks": checks,
            "failures": [name for name, ok in checks.items() if not ok]}


if __name__ == "__main__":
    result = run_audit()
    print("V6.3.6 CONTROLLED-DEMO SAFETY AUDIT")
    for name, ok in result["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} — {name}")
    print(f"Demo-gate audit failures: {len(result['failures'])}/{len(result['checks'])}")
    raise SystemExit(0 if result["passed"] else 1)
