import json

from services.research.v63_self_learning import build_v63_drift_report, load_v63_champion_status


if __name__ == "__main__":
    drift = build_v63_drift_report()
    status = load_v63_champion_status()
    print(json.dumps({"model": status, "drift": drift}, indent=2, default=str))
