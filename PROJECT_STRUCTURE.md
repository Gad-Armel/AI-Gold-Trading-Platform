# V6.3.2 Project Structure

```text
AI Trading Platform/
├── config/
│   └── scalping_settings.py
├── data/
│   ├── research/
│   │   ├── v6_shadow_history.jsonl
│   │   ├── v6_shadow_lanes/
│   │   └── v6_gate_telemetry.jsonl
│   └── models/v63/                 # runtime-created; excluded from release
├── docs/
│   ├── V6_3_0_CALIBRATED_SELF_LEARNING.md
│   ├── V6_3_1_ORDER_FLOW_REGIME_LEARNING.md
│   ├── V6_3_2_CONSERVATIVE_SHADOW_FILLS.md
│   └── research/
│       └── V6_3_RESEARCH_SYNTHESIS.md
├── services/
│   ├── bot/
│   ├── execution/
│   ├── market_data/
│   ├── news/
│   ├── risk/
│   └── research/
│       ├── v63_barrier_policy.py
│       ├── v63_learned_gate.py
│       ├── v63_self_learning.py
│       ├── v6_candidate_gate.py
│       ├── v6_shadow_engine.py
│       └── v6_walk_forward.py
├── run_scalping_shadow_loop.py
├── run_v6_lane_review.py
├── run_v63_self_learning_review.py
├── run_v63_model_status.py
├── run_v6_walk_forward_review.py
└── test_v63_self_learning.py
```

The release contains no trained champion, approval, cursor, open shadow position or broker-order state. These are runtime artifacts.
