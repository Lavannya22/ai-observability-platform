"""
RCA evaluation: Top-1 and Top-3 accuracy across all 20 scenarios.

For each scenario, the pipeline runs:
  1. generate_logs  — produce scenario logs
  2. detect_incidents — rule-based error-count detector
  3. find_root_cause  — graph-based scoring

The predicted root cause is compared to the ground truth root_cause.
"""
from pathlib import Path

from generator.log_generator import generate_logs
from rca.detector import detect_incidents
from rca.dependency_graph import build_graph
from rca.engine import find_root_cause
from ml.model_utils import load_scenarios, load_ground_truth

ROOT = Path(__file__).parent.parent


def run(
    scenarios: dict,
    ground_truth: dict,
    config_path: str | None = None,
) -> dict:
    """
    Evaluate RCA Top-1 / Top-3 accuracy over all scenarios.

    Returns:
        {
            "top1_accuracy": float,
            "top3_accuracy": float,
            "per_scenario": [{"scenario_id", "expected", "predicted", "top1", "top3"}, ...]
        }
    """
    if config_path is None:
        config_path = str(ROOT / "configs" / "settings.yaml")

    graph = build_graph(config_path)
    per_scenario: list[dict] = []

    for sid in sorted(scenarios):
        scenario = scenarios[sid]
        gt = ground_truth[sid]
        expected = gt["root_cause"]

        logs = generate_logs(scenario, config_path)
        incidents = detect_incidents(logs, config_path)

        if not incidents:
            per_scenario.append({
                "scenario_id": sid,
                "expected": expected,
                "predicted": None,
                "top1": False,
                "top3": False,
            })
            continue

        incident_services = list({i["service"] for i in incidents})
        candidates = find_root_cause(incident_services, graph)

        top1 = bool(candidates) and candidates[0]["service"] == expected
        top3 = any(c["service"] == expected for c in candidates[:3])

        per_scenario.append({
            "scenario_id": sid,
            "expected": expected,
            "predicted": candidates[0]["service"] if candidates else None,
            "top1": top1,
            "top3": top3,
        })

    n = len(per_scenario)
    top1_accuracy = sum(1 for r in per_scenario if r["top1"]) / n if n > 0 else 0.0
    top3_accuracy = sum(1 for r in per_scenario if r["top3"]) / n if n > 0 else 0.0

    return {
        "top1_accuracy": round(top1_accuracy, 4),
        "top3_accuracy": round(top3_accuracy, 4),
        "per_scenario": per_scenario,
    }


if __name__ == "__main__":
    import json

    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    results = run(scenarios, ground_truth)
    for row in results["per_scenario"]:
        mark = "OK" if row["top1"] else "FAIL"
        print(f"  {row['scenario_id']} {mark}  expected={row['expected']:<10} predicted={row['predicted']}")
    print(f"\nTop-1 accuracy: {results['top1_accuracy']:.1%}")
    print(f"Top-3 accuracy: {results['top3_accuracy']:.1%}")
