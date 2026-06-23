import json
from evaluation.metrics import (
    rca_accuracy_at_k,
    detection_hit,
    cluster_noise_reduction,
    throughput,
    message_loss,
    detection_latency,
)


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
        "rca_top1_correct": rca_accuracy_at_k(rca_candidates, gt["root_cause"], k=1),
        "rca_top3_correct": rca_accuracy_at_k(rca_candidates, gt["root_cause"], k=3),
        "detection_hit": detection_hit(incidents, [gt["root_cause"]] + gt["affected_services"]),
        "total_error_logs": total_errors,
        "num_clusters": num_clusters,
        "noise_reduction": cluster_noise_reduction(total_errors, num_clusters),
        "predicted_root_cause": rca_candidates[0]["service"] if rca_candidates else None,
        "expected_root_cause": gt["root_cause"],
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


# ── Streaming evaluation (Phase 2) ────────────────────────────────────────────

def evaluate_streaming(
    logs_generated: int,
    logs_stored: int,
    duration_seconds: float,
    log_created_at: str | None = None,
    incident_detected_at: str | None = None,
) -> dict:
    """
    Evaluate streaming pipeline performance.

    Args:
        logs_generated: total logs sent by producer
        logs_stored:    total logs confirmed in PostgreSQL
        duration_seconds: wall-clock time of the streaming run
        log_created_at:   ISO timestamp of the first triggering log
        incident_detected_at: ISO timestamp when incident was first created
    """
    loss = message_loss(logs_generated, logs_stored)
    tput = throughput(logs_stored, duration_seconds)
    latency = (
        detection_latency(log_created_at, incident_detected_at)
        if log_created_at and incident_detected_at
        else None
    )
    results = {
        "logs_generated": logs_generated,
        "logs_stored": logs_stored,
        "throughput_logs_per_min": tput,
        "message_loss": loss["lost"],
        "message_loss_pct": loss["loss_pct"],
        "detection_latency_seconds": latency,
        "duration_seconds": round(duration_seconds, 2),
    }
    return results


def print_streaming_evaluation(results: dict):
    print("\n--- STREAMING EVALUATION ---")
    print(f"Logs Generated    : {results['logs_generated']}")
    print(f"Logs Stored       : {results['logs_stored']}")
    print(f"Throughput        : {results['throughput_logs_per_min']} logs/min")
    print(f"Message Loss      : {results['message_loss']} ({results['message_loss_pct']}%)")
    if results["detection_latency_seconds"] is not None:
        print(f"Detection Latency : {results['detection_latency_seconds']}s")
    print(f"Duration          : {results['duration_seconds']}s")
