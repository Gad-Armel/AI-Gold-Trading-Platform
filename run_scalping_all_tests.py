from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = [
    "test_v6_candidate_gate.py",
    "test_v6_market_structure.py",
    "test_v6_shadow_engine.py",
    "test_v6_approval_walk_forward.py",
    "test_v6_safety_and_free_data.py",
    "test_v6_2_multi_lane_shadow.py",
    "test_v63_self_learning.py",
    "test_v632_order_flow_regime.py",
    "test_candle_follow_shadow.py",
    "test_gold_advisory.py",
    "test_kimi_signal_features.py",
    "test_medium_horizon_shadow.py",
    "run_scalping_entry_gate_audit.py",
    "run_scalping_demo_gate_audit.py",
    "run_scalping_audit.py",
]


def main() -> int:
    failures: list[str] = []
    print("=" * 78)
    print("V6.3.6 TICK-HORIZON FAST RESEARCH VALIDATION")
    print("=" * 78)
    for index, script in enumerate(SCRIPTS, start=1):
        print(f"\n[{index}/{len(SCRIPTS)}] {script}", flush=True)
        env = dict(os.environ)
        env["SCALPING_FAST_TEST_MODE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(ROOT / script)],
            cwd=str(ROOT),
            check=False,
            env=env,
        )
        if completed.returncode != 0:
            failures.append(script)
    print("\n" + "=" * 78)
    print(f"Validation scripts failed: {len(failures)}/{len(SCRIPTS)}")
    if failures:
        for script in failures:
            print(f"  - {script}")
    else:
        print("All V6 validation scripts passed.")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
