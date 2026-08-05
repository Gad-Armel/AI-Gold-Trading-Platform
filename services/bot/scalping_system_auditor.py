from __future__ import annotations

import ast
import os
from datetime import datetime
from pathlib import Path

from config import scalping_settings
from config import settings as core_settings
from services.bot.scalping_config_validator import validate_scalping_config
from services.risk.scalping_risk_guard import get_scalping_log_folder

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_FILES = [
    "config/scalping_settings.py",
    "config/free_data_settings.py",
    "models/scalping_state.py",
    "services/market_data/scalping_snapshot.py",
    "services/analysis/scalp_signal_engine.py",
    "services/analysis/unified_scalping_intelligence.py",
    "services/analysis/v6_market_structure.py",
    "services/microstructure/tick_recorder.py",
    "services/microstructure/feature_engine.py",
    "services/microstructure/feature_store.py",
    "services/agents/scalping_agents.py",
    "services/agents/meta_controller.py",
    "services/news/unified_news_intelligence.py",
    "services/news/free_macro_context.py",
    "services/decision/demo_signal_persistence.py",
    "services/research/v6_candidate_gate.py",
    "services/research/v6_shadow_engine.py",
    "services/research/v6_feed_guard.py",
    "services/research/v6_gate_telemetry.py",
    "services/research/v6_lane_review.py",
    "services/research/candle_follow_shadow.py",
    "services/research/v6_walk_forward.py",
    "services/research/v6_approval.py",
    "services/research/v63_barrier_policy.py",
    "services/research/v63_self_learning.py",
    "services/research/v63_learned_gate.py",
    "run_v63_self_learning_review.py",
    "run_v63_model_status.py",
    "test_v63_self_learning.py",
    "test_v632_order_flow_regime.py",
    "docs/V6_3_0_CALIBRATED_SELF_LEARNING.md",
    "docs/V6_3_1_ORDER_FLOW_REGIME_LEARNING.md",
    "docs/V6_3_2_CONSERVATIVE_SHADOW_FILLS.md",
    "docs/V6_3_4_COST_AWARE_MICRO_GATE.md",
    "docs/V6_3_5_REGIME_CONSISTENCY.md",
    "docs/V6_3_6_TICK_HORIZON_RESEARCH.md",
    "services/bot/v6_shadow_cycle_runner.py",
    "services/bot/v6_shadow_loop_runner.py",
    "services/bot/candle_follow_shadow_loop.py",
    "services/bot/scalping_demo_preflight.py",
    "services/bot/scalping_demo_cycle_runner.py",
    "services/bot/scalping_demo_loop_runner.py",
    "services/execution/scalp_demo_execution_gate.py",
    "services/execution/scalp_demo_executor.py",
    "services/execution/scalp_demo_position_manager.py",
    "services/risk/scalping_demo_risk_guard.py",
    "services/risk/demo_loss_session.py",
    "services/utils/atomic_json.py",
    "run_scalping_shadow_loop.py",
    "run_candle_follow_shadow_loop.py",
    "run_v6_walk_forward_review.py",
    "run_v6_lane_review.py",
    "run_scalping_demo_loop.py",
    "run_scalping_all_tests.py",
    "run_scalping_audit.py",
    "run_unified_news_update.py",
    "run_free_data_health_check.py",
    "docs/research/FORENSIC_59_TRADE_REVIEW.md",
    "docs/research/EXTERNAL_AI_PROPOSAL_REVIEW_V632.md",
    "docs/research/RESEARCH_REVIEW_60_SOURCES.md",
    "docs/research/V6_2_FIRST_EPISODE_REVIEW.md",
    "docs/V6_2_0_GRAPHICAL_STRUCTURE_CONSENSUS.md",
    "docs/V6_2_0_MULTI_LANE_SHADOW_CALIBRATION.md",
    "docs/V6_2_1_EPISODE_REARM_EXIT_INTEGRITY.md",
    ".env.example",
    "test_v6_candidate_gate.py",
    "test_v6_market_structure.py",
    "test_v6_shadow_engine.py",
    "test_v6_approval_walk_forward.py",
    "test_v6_safety_and_free_data.py",
    "test_v6_2_multi_lane_shadow.py",
    "test_candle_follow_shadow.py",
]

SHADOW_FILES = [
    "run_scalping_shadow_loop.py",
    "services/bot/v6_shadow_loop_runner.py",
    "services/bot/v6_shadow_cycle_runner.py",
    "services/research/v6_shadow_engine.py",
    "services/research/v6_feed_guard.py",
    "services/research/v6_gate_telemetry.py",
    "services/research/v6_lane_review.py",
    "run_candle_follow_shadow_loop.py",
    "services/bot/candle_follow_shadow_loop.py",
    "services/research/candle_follow_shadow.py",
]

PROHIBITED_SHADOW_CALLS = {"order_send", "execute_demo_scalp", "buy_market", "sell_market"}
PROHIBITED_SHADOW_IMPORTS = {"scalp_demo_executor", "scalping_demo_cycle_runner", "scalping_demo_loop_runner"}


def _audit_shadow_file(relative_path: str) -> list[str]:
    path = PROJECT_ROOT / relative_path
    failures: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        return [f"Could not parse {relative_path}: {exc}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            if any(blocked in module for blocked in PROHIBITED_SHADOW_IMPORTS):
                failures.append(f"{relative_path} imports broker-order module {module}.")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name in PROHIBITED_SHADOW_CALLS:
                failures.append(f"{relative_path} calls prohibited broker function {name}.")
    return failures



def _resolve_local_module(module: str) -> Path | None:
    if not module:
        return None
    candidate = PROJECT_ROOT / (module.replace(".", "/") + ".py")
    if candidate.exists():
        return candidate
    package = PROJECT_ROOT / module.replace(".", "/") / "__init__.py"
    return package if package.exists() else None


def _reachable_shadow_files() -> set[Path]:
    queue = [PROJECT_ROOT / item for item in SHADOW_FILES if (PROJECT_ROOT / item).exists()]
    seen: set[Path] = set()
    while queue:
        path = queue.pop()
        if path in seen or not path.exists() or path.suffix != ".py":
            continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            for module in modules:
                resolved = _resolve_local_module(module)
                if resolved is not None and resolved not in seen:
                    queue.append(resolved)
    return seen


def _audit_shadow_graph() -> tuple[list[str], int]:
    failures: list[str] = []
    reachable = _reachable_shadow_files()
    for path in reachable:
        relative = str(path.relative_to(PROJECT_ROOT))
        failures.extend(_audit_shadow_file(relative))
    return failures, len(reachable)


def run_scalping_system_audit() -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    missing = [item for item in REQUIRED_FILES if not (PROJECT_ROOT / item).exists()]
    failures.extend(f"Missing required file: {item}" for item in missing)

    config = validate_scalping_config()
    failures.extend(config.get("errors", []))
    warnings.extend(config.get("warnings", []))

    checks = {
        "v6_strategy": str(scalping_settings.SCALPING_STRATEGY_ID).startswith("XAUUSD_SCALP_V6_"),
        "shadow_default": bool(scalping_settings.SCALPING_V6_SHADOW_MODE_DEFAULT),
        "approval_required": bool(scalping_settings.SCALPING_V6_DEMO_APPROVAL_REQUIRED),
        "real_execution_disabled": not bool(scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED),
        "core_live_disabled": not bool(getattr(core_settings, "ENABLE_LIVE_TRADING", False)),
        "one_position": int(scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS) == 1,
        "pyramid_disabled": not bool(scalping_settings.SCALPING_V6_PYRAMID_ENABLED),
        "no_trade_count_limit": not bool(scalping_settings.SCALPING_DEMO_TRADE_LIMIT_ENABLED),
        "persistent_loss_stop_100": abs(float(scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD) - 100.0) < 1e-9,
        "strict_spread": float(scalping_settings.SCALPING_V6_MAX_SPREAD_USD) <= 0.27 + 1e-9,
        "three_loss_breaker": int(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES) == 3,
        "five_minute_breaker": int(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS) == 300,
        "structure_consensus": bool(scalping_settings.SCALPING_V6_STRUCTURE_CONSENSUS_ENABLED),
        "structure_two_of_three": int(scalping_settings.SCALPING_V6_STRUCTURE_MIN_VOTES) == 2,
        "structure_location_room": bool(scalping_settings.SCALPING_V6_REQUIRE_STRUCTURE_LOCATION_ROOM),
        "multi_lane_shadow": bool(scalping_settings.SCALPING_V6_SHADOW_LANES_ENABLED),
        "feed_pause": float(scalping_settings.SCALPING_V6_FEED_PAUSE_QUOTE_AGE_SECONDS) > float(scalping_settings.SCALPING_V6_MAX_QUOTE_AGE_SECONDS),
        "episode_rearm": bool(scalping_settings.SCALPING_V6_EPISODE_REARM_ENABLED),
        "hard_stop_structure_reset": bool(scalping_settings.SCALPING_V6_HARD_STOP_STRUCTURE_RESET_REQUIRED),
        "self_learning_enabled": bool(scalping_settings.SCALPING_V63_SELF_LEARNING_ENABLED),
        "learned_lane_enabled": bool(scalping_settings.SCALPING_V63_LEARNED_LANE_ENABLED),
        "target_win_rate_59": float(scalping_settings.SCALPING_V63_TARGET_WIN_RATE) >= 0.59,
        "approved_model_required": bool(scalping_settings.SCALPING_V63_DEMO_REQUIRES_APPROVED_MODEL),
        "dynamic_barrier_ratio": float(scalping_settings.SCALPING_V63_MIN_TARGET_STOP_RATIO) >= 0.80,
        "conservative_target_fill": str(scalping_settings.SCALPING_V632_SHADOW_TARGET_FILL_MODE).upper() == "PLANNED_BARRIER",
        "adverse_stop_uses_observed_quote": str(scalping_settings.SCALPING_V632_SHADOW_STOP_FILL_MODE).upper() == "OBSERVED_EXECUTABLE_QUOTE",
        "drift_guard": float(scalping_settings.SCALPING_V63_DRIFT_PSI_BLOCK) <= 0.30,
    }
    failures.extend(f"V6 safety check failed: {name}." for name, passed in checks.items() if not passed)

    shadow_graph_failures, shadow_reachable_files = _audit_shadow_graph()
    failures.extend(shadow_graph_failures)

    execution_gate = (PROJECT_ROOT / "services/execution/scalp_demo_execution_gate.py").read_text(encoding="utf-8")
    preflight = (PROJECT_ROOT / "services/bot/scalping_demo_preflight.py").read_text(encoding="utf-8")
    for name, source in (("demo execution gate", execution_gate), ("demo preflight", preflight)):
        if "load_v6_approval" not in source:
            failures.append(f"{name} does not verify the V6 approval artifact.")
        if "load_v63_champion_status" not in source:
            failures.append(f"{name} does not verify the V6.3 calibrated champion model.")
    demo_cycle = (PROJECT_ROOT / "services/bot/scalping_demo_cycle_runner.py").read_text(encoding="utf-8")
    for token in ("build_v6_market_structure", "evaluate_v6_candidate_gate", "apply_v6_candidate_gate"):
        if token not in demo_cycle:
            failures.append(f"Controlled demo cycle does not use exact V6 strategy component: {token}.")
    for token in ("evaluate_demo_entry_policy", "apply_demo_entry_policy"):
        if token in demo_cycle:
            failures.append(f"Controlled demo cycle still uses legacy policy: {token}.")

    demo_runner = (PROJECT_ROOT / "run_scalping_demo_loop.py").read_text(encoding="utf-8")
    for token in ("--confirm", "build_demo_preflight", "arm_demo_session", "prepare_demo_loss_session"):
        if token not in demo_runner:
            failures.append(f"Demo runner lacks safeguard: {token}.")

    runtime_artifacts = []
    for pattern in ("**/*cursor*.json", "**/*.lock", "**/*.tmp"):
        runtime_artifacts.extend(str(path.relative_to(PROJECT_ROOT)) for path in PROJECT_ROOT.glob(pattern) if "__pycache__" not in str(path))
    if runtime_artifacts:
        warnings.append("Runtime artifacts exist in the working tree and must be excluded from release: " + ", ".join(runtime_artifacts[:10]))

    return {
        "passed": not failures,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "required_files": len(REQUIRED_FILES),
        "shadow_reachable_files": shadow_reachable_files,
        "missing_files": missing,
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
        "strategy_id": scalping_settings.SCALPING_STRATEGY_ID,
        "shadow_default": scalping_settings.SCALPING_V6_SHADOW_MODE_DEFAULT,
        "demo_execution_enabled": scalping_settings.SCALPING_DEMO_EXECUTION_ENABLED,
        "demo_approval_required": scalping_settings.SCALPING_V6_DEMO_APPROVAL_REQUIRED,
        "real_execution_enabled": scalping_settings.SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED,
        "max_positions": scalping_settings.SCALPING_DEMO_MAX_OPEN_POSITIONS,
        "cumulative_demo_loss_limit": float(scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD),
    }


def print_scalping_system_audit() -> dict:
    result = run_scalping_system_audit()
    print("\n" + "=" * 78)
    print("V6.3.6 TICK-HORIZON FAST RESEARCH SYSTEM AUDIT")
    print("=" * 78)
    print(f"Audit Status: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Strategy: {result['strategy_id']}")
    print(f"Required Files Checked: {result['required_files']}")
    print(f"Shadow Default: {'YES' if result['shadow_default'] else 'NO'}")
    print(f"Shadow Reachable Python Files Audited: {result['shadow_reachable_files']}")
    print(f"Controlled Demo Code Present: {'YES' if result['demo_execution_enabled'] else 'NO'}")
    print(f"Walk-Forward Approval Required: {'YES' if result['demo_approval_required'] else 'NO'}")
    print(f"Real Execution Enabled: {'YES' if result['real_execution_enabled'] else 'NO'}")
    print(f"Maximum Positions: {result['max_positions']}")
    print(f"Persistent Demo Loss Stop: -${result['cumulative_demo_loss_limit']:.2f}")
    if result["failures"]:
        print("Failures:")
        for item in result["failures"]:
            print(f"  - {item}")
    else:
        print("Failures: None")
    if result["warnings"]:
        print("Warnings:")
        for item in result["warnings"]:
            print(f"  - {item}")
    else:
        print("Warnings: None")
    print("=" * 78)

    folder = Path(get_scalping_log_folder())
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / scalping_settings.SCALPING_AUDIT_FILENAME
    path.write_text("\n".join(f"{key}: {value}" for key, value in result.items()) + "\n", encoding="utf-8")
    print(f"Audit report saved: {path}\n")
    return result
