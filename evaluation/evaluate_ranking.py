"""
Root cause ranking evaluation: Mean Reciprocal Rank (MRR).

For each scenario, find_root_cause() returns a ranked list of candidates.
MRR = mean of (1 / rank_of_correct_answer) across all scenarios.

True cause ranked #1 → contributes 1.0
True cause ranked #2 → contributes 0.5
True cause ranked #3 → contributes 0.33
True cause not in top-k → contributes 0.0

Target: MRR >= 0.90
"""
from pathlib import Path

from generator.log_generator import generate_logs
from rca.detector import detect_incidents
from rca.dependency_graph import build_graph
from rca.engine import rank_root_causes
from ml.model_utils import load_scenarios, load_ground_truth

ROOT = Path(__file__).parent.parent


def run(
    scenarios: dict,
    ground_truth: dict,
    config_path: str | None = None,
) -> dict:
    """
    Evaluate Mean Reciprocal Rank of root cause predictions over all scenarios.

    Returns:
        {
            "mrr": float,
            "per_scenario": [{"scenario_id", "expected", "rank", "reciprocal_rank"}, ...]
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
                "rank": None,
                "reciprocal_rank": 0.0,
            })
            continue

        incident_services = list({i["service"] for i in incidents})
        ranked = rank_root_causes(incident_services, graph)

        rank = None
        for i, candidate in enumerate(ranked, start=1):
            if candidate["service"] == expected:
                rank = i
                break

        rr = (1.0 / rank) if rank is not None else 0.0

        per_scenario.append({
            "scenario_id": sid,
            "expected": expected,
            "predicted": ranked[0]["service"] if ranked else None,
            "rank": rank,
            "reciprocal_rank": round(rr, 4),
            "confidence_distribution": {
                c["service"]: c["confidence"] for c in ranked
            },
        })

    mrr = sum(r["reciprocal_rank"] for r in per_scenario) / len(per_scenario) if per_scenario else 0.0

    return {
        "mrr": round(mrr, 4),
        "per_scenario": per_scenario,
    }


if __name__ == "__main__":
    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    results = run(scenarios, ground_truth)

    print("\nRoot Cause Ranking — MRR Evaluation")
    print("-" * 55)
    for row in results["per_scenario"]:
        rank_str = f"rank={row['rank']}" if row["rank"] else "not found"
        print(f"  {row['scenario_id']}  expected={row['expected']:<12} {rank_str}  RR={row['reciprocal_rank']:.4f}")

    print(f"\nMean Reciprocal Rank: {results['mrr']:.4f}")
    target = "PASS" if results["mrr"] >= 0.90 else "FAIL"
    print(f"Target (>= 0.90):     {target}")
