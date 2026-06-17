import json
from evaluation.metrics import rca_accuracy_at_k, detection_hit, cluster_noise_reduction


def load_ground_truth(path: str = "scenarios/ground_truth.json") -> dict:
    with open(path) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}


def evaluate(
    scenario_id: str,
    incidents: list[dict],
    clusters: list[dict],
    rca_candidates: list[dict],
    logs: list[dict],
    ground_truth_path: str = "scenarios/ground_truth.json",
) -> dict:
    ground_truth = load_ground_truth(ground_truth_path)
    gt = ground_truth[scenario_id]

    error_logs = [l for l in logs if l["level"] == "ERROR"]
    total_errors = len(error_logs)
    num_clusters = len(clusters)

    results = {
        "scenario_id": scenario_id,
        "rca_top1_correct": rca_accuracy_at_k(rca_candidates, gt["root_cause_service"], k=1),
        "rca_top3_correct": rca_accuracy_at_k(rca_candidates, gt["root_cause_service"], k=3),
        "detection_hit": detection_hit(incidents, [gt["root_cause_service"]] + gt["affected_services"]),
        "total_error_logs": total_errors,
        "num_clusters": num_clusters,
        "noise_reduction": cluster_noise_reduction(total_errors, num_clusters),
        "predicted_root_cause": rca_candidates[0]["service"] if rca_candidates else None,
        "expected_root_cause": gt["root_cause_service"],
    }
    return results


def print_evaluation(results: dict):
    print("\n--- EVALUATION RESULTS ---")
    print(f"Scenario          : {results['scenario_id']}")
    print(f"Expected RCA      : {results['expected_root_cause']}")
    print(f"Predicted RCA     : {results['predicted_root_cause']}")
    print(f"Top-1 Correct     : {results['rca_top1_correct']}")
    print(f"Top-3 Correct     : {results['rca_top3_correct']}")
    print(f"Detection Hit     : {results['detection_hit']}")
    print(f"Error Logs        : {results['total_error_logs']}")
    print(f"Clusters          : {results['num_clusters']}")
    print(f"Noise Reduction   : {results['noise_reduction']:.1%}")
