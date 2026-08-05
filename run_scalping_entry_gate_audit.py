from __future__ import annotations

from pathlib import Path

from config import scalping_settings as s


def run_audit() -> dict:
    learner_text = Path("services/research/v63_self_learning.py").read_text(encoding="utf-8")
    micro_text = Path("services/microstructure/feature_engine.py").read_text(encoding="utf-8")
    shadow_text = Path("services/research/v6_shadow_engine.py").read_text(encoding="utf-8")
    gate_text = Path("services/research/v6_candidate_gate.py").read_text(encoding="utf-8")
    checks = {
        "shadow_default": bool(s.SCALPING_V6_SHADOW_MODE_DEFAULT),
        "approval_required": bool(s.SCALPING_V6_DEMO_APPROVAL_REQUIRED),
        "spread_027": abs(float(s.SCALPING_V6_MAX_SPREAD_USD) - 0.27) < 1e-9,
        "vwap_1atr": abs(float(s.SCALPING_V6_MAX_ABS_VWAP_ATR) - 1.0) < 1e-9,
        "score_45": float(s.SCALPING_V6_MIN_WINNER_SCORE) >= 45.0,
        "margin_20": float(s.SCALPING_V6_MIN_SCORE_MARGIN) >= 20.0,
        "micro_055": float(s.SCALPING_V6_MIN_ALIGNED_MICRO_CONFIDENCE) >= 0.55,
        "persistence_5": int(s.SCALPING_V6_MIN_PERSISTENCE_CYCLES) >= 5,
        "persistence_125s": float(s.SCALPING_V6_MIN_PERSISTENCE_SECONDS) >= 1.25,
        "spread_atr_015": float(s.SCALPING_V6_MAX_SPREAD_ATR_RATIO) <= 0.15,
        "relative_volume_floor": float(s.SCALPING_V6_MIN_RELATIVE_VOLUME) >= 0.75,
        "relative_volume_ceiling": float(s.SCALPING_V6_MAX_RELATIVE_VOLUME) <= 1.50,
        "micro_windows": int(s.SCALPING_V6_MIN_DIRECTIONAL_WINDOWS) >= 2,
        "micro_data_quality_gate": float(s.SCALPING_V6_MIN_MICRO_DATA_QUALITY) >= 0.70,
        "quote_flow_alignment_gate": float(s.SCALPING_V6_MIN_ALIGNED_QUOTE_FLOW_IMBALANCE) >= 0.10 and "quote_flow_alignment" in gate_text,
        "spread_expansion_gate": float(s.SCALPING_V6_MAX_SPREAD_EXPANSION_ATR) <= 0.04 and "spread_stability" in gate_text,
        "adverse_micro_regime_gate": {"STALLED", "DISLOCATED"}.issubset(set(s.SCALPING_V6_BLOCKED_MICRO_REGIMES)) and "micro_regime_safe" in gate_text,
        "context_no_trade_gate": "NO_TRADE" in set(s.SCALPING_V6_STRICT_BLOCKED_CONTEXT_REGIMES) and "context_regime_safe" in gate_text,
        "context_direction_alignment": bool(s.SCALPING_V6_STRICT_REQUIRE_CONTEXT_DIRECTION_ALIGNMENT) and "context_regime_alignment" in gate_text,
        "verified_adx_m5_learning_feature": 'verified.get("adx_m5"' in shadow_text,
        "fast_lane_research_only": str(s.SCALPING_V6_FAST_LANE_NAME).upper() == "FAST",
        "fast_1s_5s_alignment": "fast_horizon_alignment" in gate_text and "fast_horizons_aligned" in gate_text,
        "fast_tight_spread": float(s.SCALPING_V6_FAST_MAX_SPREAD_USD) <= 0.20,
        "fast_short_hold": float(s.SCALPING_V6_FAST_MAX_HOLD_SECONDS) <= 15.0,
        "one_position": int(s.SCALPING_V6_MAX_OPEN_POSITIONS) == 1,
        "no_pyramiding": not bool(s.SCALPING_V6_PYRAMID_ENABLED),
        "target_085": abs(float(s.SCALPING_V6_TARGET_USD) - .85) < 1e-9,
        "hard_stop_125": abs(float(s.SCALPING_V6_HARD_STOP_USD) - 1.25) < 1e-9,
        "max_hold_60": int(s.SCALPING_V6_MAX_HOLD_SECONDS) == 60,
        "no_progress_exit": int(s.SCALPING_V6_NO_PROGRESS_CHECK_SECONDS) == 12,
        "walk_forward_200": int(s.SCALPING_V6_PROMOTION_MIN_CLOSED_SHADOW_TRADES) >= 200,
        "walk_forward_folds": int(s.SCALPING_V6_PROMOTION_MIN_WALK_FORWARD_FOLDS) >= 4,
        "structure_consensus_enabled": bool(s.SCALPING_V6_STRUCTURE_CONSENSUS_ENABLED),
        "structure_two_of_three": int(s.SCALPING_V6_STRUCTURE_MIN_VOTES) == 2,
        "structure_location_room": bool(s.SCALPING_V6_REQUIRE_STRUCTURE_LOCATION_ROOM),
        "market_map_enabled": bool(s.SCALPING_V6_CHART_EXPORT_ENABLED),
        "multi_lane_shadow_enabled": bool(s.SCALPING_V6_SHADOW_LANES_ENABLED),
        "balanced_research_only": float(s.SCALPING_V6_BALANCED_MIN_WINNER_SCORE) < float(s.SCALPING_V6_MIN_WINNER_SCORE),
        "exploratory_research_only": float(s.SCALPING_V6_EXPLORATORY_MIN_WINNER_SCORE) < float(s.SCALPING_V6_BALANCED_MIN_WINNER_SCORE),
        "feed_pause_enabled": float(s.SCALPING_V6_FEED_PAUSE_QUOTE_AGE_SECONDS) > float(s.SCALPING_V6_MAX_QUOTE_AGE_SECONDS),
        "gate_telemetry_enabled": float(s.SCALPING_V6_GATE_TELEMETRY_INTERVAL_SECONDS) > 0.0,
        "episode_rearm_enabled": bool(s.SCALPING_V6_EPISODE_REARM_ENABLED),
        "failed_thesis_direction_reset": bool(s.SCALPING_V6_FAILED_THESIS_DIRECTION_RESET_REQUIRED),
        "hard_stop_structure_reset": bool(s.SCALPING_V6_HARD_STOP_STRUCTURE_RESET_REQUIRED),
        "self_learning_enabled": bool(s.SCALPING_V63_SELF_LEARNING_ENABLED),
        "learned_lane_shadow_only": bool(s.SCALPING_V63_LEARNED_LANE_ENABLED),
        "target_win_rate_59": float(s.SCALPING_V63_TARGET_WIN_RATE) >= 0.59,
        "chronological_min_folds": int(s.SCALPING_V63_MIN_WALK_FORWARD_FOLDS) >= 4,
        "model_min_training_rows": int(s.SCALPING_V63_MIN_CLOSED_TRADES_TO_TRAIN) >= 80,
        "model_positive_expectancy": float(s.SCALPING_V63_MIN_OOS_EXPECTANCY_USD) > 0.0,
        "model_profit_factor": float(s.SCALPING_V63_MIN_OOS_PROFIT_FACTOR) >= 1.15,
        "model_calibration_guard": float(s.SCALPING_V63_MAX_OOS_BRIER_SCORE) <= 0.25,
        "model_drift_guard": float(s.SCALPING_V63_DRIFT_PSI_BLOCK) <= 0.30,
        "dynamic_barriers": bool(s.SCALPING_V63_DYNAMIC_BARRIERS_ENABLED),
        "target_stop_ratio_080": float(s.SCALPING_V63_MIN_TARGET_STOP_RATIO) >= 0.80,
        "profit_lock_stages": float(s.SCALPING_V63_PROFIT_LOCK_STAGE2_PEAK_RATIO) > float(s.SCALPING_V63_PROFIT_LOCK_STAGE1_PEAK_RATIO),
        "learned_feedback_excluded": 'if lane == "LEARNED"' in learner_text,
        "cross_lane_episode_decorrelation": 'drop_duplicates(subset=["episode_key"]' in learner_text,
        "purged_overlapping_folds": 'train["closed_at"] < first_test_open' in learner_text,
        "quote_flow_proxy_feature": "quote_flow_imbalance_proxy" in micro_text,
        "micro_regime_feature": 'micro_regime = "IMPULSE"' in micro_text,
        "gradient_boosting_challenger": 'name == "GRADIENT_BOOSTING"' in learner_text,
        "win_rate_confidence_bound": "_wilson_lower_bound" in learner_text and float(s.SCALPING_V632_MIN_OOS_WIN_RATE_LOWER_BOUND) >= 0.50,
        "selected_fold_stability": "fold_stability_passed" in learner_text and int(s.SCALPING_V632_MIN_SELECTED_FOLDS) >= 3,
        "untouched_final_holdout": (
            bool(s.SCALPING_V632_UNTOUCHED_HOLDOUT_ENABLED)
            and int(s.SCALPING_V632_MIN_HOLDOUT_SELECTED_TRADES) >= 5
            and "untouched_holdout" in learner_text
            and "development_end" in learner_text
        ),
        "permutation_importance_oos": "_permutation_brier_importance" in learner_text,
        "champion_schema_compatibility": "feature_schema_compatible" in learner_text and "strategy_compatible" in learner_text,
        "conservative_target_fill": (
            str(s.SCALPING_V632_SHADOW_TARGET_FILL_MODE).upper() == "PLANNED_BARRIER"
            and "PLANNED_TARGET_BARRIER" in shadow_text
            and "barrier_overshoot_usd" in shadow_text
        ),
        "adverse_stop_observed_quote": (
            str(s.SCALPING_V632_SHADOW_STOP_FILL_MODE).upper() == "OBSERVED_EXECUTABLE_QUOTE"
            and "observed_market_profit_usd" in shadow_text
        ),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "failures": [name for name, ok in checks.items() if not ok]}


if __name__ == "__main__":
    result = run_audit()
    print("V6.3.6 ENTRY / LEARNING / TICK-HORIZON AUDIT")
    for name, ok in result["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} — {name}")
    print(f"Entry-gate audit failures: {len(result['failures'])}/{len(result['checks'])}")
    raise SystemExit(0 if result["passed"] else 1)
