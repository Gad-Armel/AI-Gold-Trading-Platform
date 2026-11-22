# Project structure (generated)

Updated UTC: 2026-09-25T10:03:44.367905+00:00

Regenerate with: `python tools/generate_project_structure.py`

Safety: `.env` contents, Git internals, caches, release archives, and individual large data files are excluded.

## Active entry points

- `run_gold_advisor.py`
- `run_gold_ai.py`
- `run_gold_consensus_bot.py`
- `run_gold_consensus_health_check.py`
- `run_gold_economic_advisor_v5.py`
- `run_gold_source_advisor.py`
- `run_gold_unified_dashboard.py`
- `run_vfinal.py`
- `run_vfinal_demo.py`

## Tests

- `test_background_refresh.py`
- `test_free_macro_context.py`
- `test_gold_adaptive_exit.py`
- `test_gold_advisory.py`
- `test_gold_advisory_consensus.py`
- `test_gold_advisory_v2.py`
- `test_gold_advisory_v3.py`
- `test_gold_ai_integration.py`
- `test_gold_broker_clock.py`
- `test_gold_consensus_dashboard.py`
- `test_gold_consensus_demo_broker.py`
- `test_gold_continuous_scalp.py`
- `test_gold_economic_advisor_v5.py`
- `test_gold_exit_state.py`
- `test_gold_feed_reliability.py`
- `test_gold_flow_exit.py`
- `test_gold_horizon_policy.py`
- `test_gold_institutional_context.py`
- `test_gold_institutional_context_tool.py`
- `test_gold_position_conscience.py`
- `test_gold_proposal_features.py`
- `test_gold_source_intelligence.py`
- `test_official_release_monitor.py`
- `test_unified_news_intelligence.py`
- `tests/test_core.py`
- `tests/test_training_promotion.py`
- `tests/test_walk_forward_integrity.py`

## Folder tree

```text
AI Trading Platform/
|-- config/
|   |-- free_data_settings.py
|   |-- gold_consensus_settings.py
|   |-- scalping_settings.py
|   `-- settings.py
|-- data/ [summarized: 110 files, 640.4 MB; .json:55, .jsonl:26, .csv:12, .lock:5, .joblib:5]
|-- docs/
|   |-- research/
|   |   |-- AI_PROPOSAL_01_REVIEW.md
|   |   |-- AI_PROPOSAL_02_REVIEW.md
|   |   |-- GOLD_AI_BUILD_AND_RUN.md
|   |   |-- GOLD_SOURCE_FUSION_RESEARCH.md
|   |   |-- report-source.md
|   |   `-- XAUUSD_PERFORMANCE_AND_ADAPTIVE_RESEARCH.md
|   |-- ARCHITECTURE_AND_SAFETY.md
|   |-- CONTINUOUS_SCALP_REVIEW.md
|   |-- DEMO_RUNBOOK.md
|   |-- EXIT_AND_CONSCIENCE.md
|   |-- FINAL_PLAN.md
|   |-- FIX_1.2.1.md
|   |-- GOLD_SCALP_NATIVE_FR.md
|   |-- INSTALL_AND_TEST.md
|   |-- MARKET_DESIGN_RATIONALE.md
|   |-- RUNBOOK.md
|   |-- SCALP_CONTINUOUS_FLOW_WIP.md
|   `-- SCALP_FEED_RELIABILITY.md
|-- logs/ [summarized: 1110 files, 86.0 MB; .png:1098, .txt:11, .md:1]
|-- models/
|   |-- market_state.py
|   `-- scalping_state.py
|-- mql5/
|   |-- Experts/
|   |   `-- GoldScalpAI/
|   |       |-- GoldScalpAI.ex5
|   |       |-- GoldScalpAI.mq5
|   |       |-- GoldScalpExit.mqh
|   |       |-- GoldScalpFlow.mqh
|   |       |-- GoldScalpLearning.mqh
|   |       |-- GoldScalpMath.mqh
|   |       |-- GoldScalpSelfTest.ex5
|   |       `-- GoldScalpSelfTest.mq5
|   `-- validation/
|       |-- compilation-summary.txt
|       |-- GoldScalpAI.compile.log
|       |-- GoldScalpSelfTest.compile.log
|       |-- historical-test-blocker.txt
|       |-- native-selftest.txt
|       `-- results.json
|-- services/
|   |-- analysis/
|   |   |-- v6_market_structure.py
|   |   `-- verified_market_context.py
|   |-- bot/
|   |   |-- emergency_stop.py
|   |   `-- scalping_instance_lock.py
|   |-- dashboard/
|   |   |-- gold_consensus_web.py
|   |   |-- gold_horizon_history.py
|   |   `-- gold_loss_reset.py
|   |-- execution/
|   |   |-- demo_session_guard.py
|   |   |-- gold_consensus_demo_broker.py
|   |   |-- gold_paper_portfolio.py
|   |   |-- mt5_connector.py
|   |   `-- scalp_profit_calculator.py
|   |-- market_data/
|   |   |-- candle_service.py
|   |   |-- free_macro_context.py
|   |   |-- gold_broker_clock.py
|   |   |-- gold_institutional_context.py
|   |   |-- oanda_gold.py
|   |   |-- price_service.py
|   |   |-- scalping_snapshot.py
|   |   |-- session_service.py
|   |   |-- spread_utils.py
|   |   |-- timeframe_service.py
|   |   `-- twelve_data_gold.py
|   |-- news/
|   |   |-- __init__.py
|   |   |-- official_release_monitor.py
|   |   `-- unified_news_intelligence.py
|   |-- research/
|   |   |-- __init__.py
|   |   |-- background_refresh.py
|   |   |-- gold_adaptive_exit.py
|   |   |-- gold_advisory.py
|   |   |-- gold_advisory_consensus.py
|   |   |-- gold_advisory_dashboard.py
|   |   |-- gold_advisory_v2.py
|   |   |-- gold_advisory_v3.py
|   |   |-- gold_cross_market.py
|   |   |-- gold_economic_advisor_v5.py
|   |   |-- gold_exit_state.py
|   |   |-- gold_fast_protection.py
|   |   |-- gold_flow_exit.py
|   |   |-- gold_horizon_policy.py
|   |   |-- gold_learned_policy.py
|   |   |-- gold_micro_flow.py
|   |   |-- gold_position_conscience.py
|   |   |-- gold_research_recorder.py
|   |   |-- gold_runtime_health.py
|   |   |-- gold_scalp_guard.py
|   |   |-- gold_source_intelligence.py
|   |   `-- gold_tick_history.py
|   |-- risk/
|   |   |-- automatic_economic_calendar.py
|   |   |-- economic_event_manager.py
|   |   `-- news_event_filter.py
|   `-- utils/
|       |-- __init__.py
|       `-- atomic_json.py
|-- tests/
|   |-- test_core.py
|   |-- test_training_promotion.py
|   `-- test_walk_forward_integrity.py
|-- tools/
|   |-- __init__.py
|   |-- audit_continuous_scalp.py
|   |-- audit_gold_performance.py
|   |-- audit_project_assets.py
|   |-- audit_python_reachability.py
|   |-- compile_gold_scalp.ps1
|   |-- diagnose_gold_feed.py
|   |-- generate_project_structure.py
|   |-- report_gold_ai.py
|   |-- research_gold_adaptive.py
|   |-- research_gold_sources.py
|   |-- stress_gold_candidate.py
|   |-- test_gold_scalp.ps1
|   |-- train_gold_ai.py
|   |-- update_gold_institutional_context.py
|   `-- validate_gold_changes.py
|-- vfinal/
|   |-- cli/
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- data/ [summarized: 5 files, 0.0 MB; .py:5]
|   |-- execution/
|   |   |-- __init__.py
|   |   |-- decision.py
|   |   `-- vfinal_meta_engine.py
|   |-- features/
|   |   |-- __init__.py
|   |   |-- core.py
|   |   `-- market_state.py
|   |-- model/
|   |   |-- __init__.py
|   |   |-- calibration.py
|   |   |-- metrics.py
|   |   |-- monitor.py
|   |   |-- train.py
|   |   `-- walk_forward.py
|   |-- providers/
|   |   |-- __init__.py
|   |   |-- bls.py
|   |   |-- cftc.py
|   |   |-- fred.py
|   |   |-- health.py
|   |   `-- mt5_ticks.py
|   |-- __init__.py
|   |-- config.py
|   |-- dashboard.py
|   |-- integration.py
|   `-- schema.py
|-- .env [SECRET - contents excluded]
|-- .env.example
|-- .gitignore
|-- CLAUDE.md
|-- DATA_SOURCES.md
|-- OPERATING_GUIDE.md
|-- PROJECT_CONSTRAINTS.md
|-- PROJECT_STRUCTURE.md
|-- README.md
|-- requirements.txt
|-- run_gold_advisor.py
|-- run_gold_ai.py
|-- run_gold_consensus_bot.py
|-- run_gold_consensus_health_check.py
|-- run_gold_economic_advisor_v5.py
|-- run_gold_source_advisor.py
|-- run_vfinal.py
|-- run_vfinal_demo.py
|-- test_background_refresh.py
|-- test_free_macro_context.py
|-- test_gold_adaptive_exit.py
|-- test_gold_advisory.py
|-- test_gold_advisory_consensus.py
|-- test_gold_advisory_v2.py
|-- test_gold_advisory_v3.py
|-- test_gold_ai_integration.py
|-- test_gold_broker_clock.py
|-- test_gold_consensus_dashboard.py
|-- test_gold_consensus_demo_broker.py
|-- test_gold_continuous_scalp.py
|-- test_gold_economic_advisor_v5.py
|-- test_gold_exit_state.py
|-- test_gold_feed_reliability.py
|-- test_gold_flow_exit.py
|-- test_gold_horizon_policy.py
|-- test_gold_institutional_context.py
|-- test_gold_institutional_context_tool.py
|-- test_gold_position_conscience.py
|-- test_gold_proposal_features.py
|-- test_gold_source_intelligence.py
|-- test_official_release_monitor.py
`-- test_unified_news_intelligence.py
```
