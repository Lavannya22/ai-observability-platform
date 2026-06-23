"""
Anomaly detection evaluation: Isolation Forest on per-service error-phase features.

Feature matrix: one row per (scenario, service) — 20 × 5 = 100 rows.
Features: error_count, warning_count, avg_latency_ms, retry_count.
Ground truth: service is anomalous if it is the root_cause or an affected_service.

The IF is fit-and-predicted on the error-phase features with contamination
computed dynamically from the ground truth labels.
"""
from pathlib import Path

from generator.log_generator import generate_logs
from ml.model_utils import extract_service_features, load_scenarios, load_ground_truth
from ml.anomaly_detector import train_and_predict, evaluate_anomaly_detection

ROOT = Path(__file__).parent.parent
SERVICES = ["database", "metadata", "etl", "analytics", "reporting"]


def _build_matrices(scenarios: dict, ground_truth: dict, config_path: str):
    """
    Build feature matrix from the ERROR-phase logs of every scenario.

    Returns (X, gt_labels):
        X         — list of feature vectors (one per service per scenario)
        gt_labels — 'anomaly' or 'normal' for each row
    """
    X: list[list[float]] = []
    gt_labels: list[str] = []

    for sid in sorted(scenarios):
        scenario = scenarios[sid]
        gt = ground_truth[sid]
        logs = generate_logs(scenario, config_path)

        error_logs = [l for l in logs if l["level"] == "ERROR"]
        features = extract_service_features(error_logs, SERVICES)

        anomalous = set([gt["root_cause"]] + gt["affected_services"])
        for svc in SERVICES:
            X.append(features[svc])
            gt_labels.append("anomaly" if svc in anomalous else "normal")

    return X, gt_labels


def run(
    scenarios: dict,
    ground_truth: dict,
    config_path: str | None = None,
) -> dict:
    """
    Run Isolation Forest evaluation.

    Returns:
        {"precision", "recall", "false_positive_rate", "tp", "fp", "fn", "tn",
         "contamination_used", "total_samples"}
    """
    if config_path is None:
        config_path = str(ROOT / "configs" / "settings.yaml")

    X, gt_labels = _build_matrices(scenarios, ground_truth, config_path)

    anomaly_count = sum(1 for l in gt_labels if l == "anomaly")
    # sklearn IsolationForest requires contamination in (0.0, 0.5]
    contamination = max(0.05, min(0.5, anomaly_count / len(gt_labels)))

    predictions = train_and_predict(X, contamination=contamination)
    metrics = evaluate_anomaly_detection(predictions, gt_labels)
    metrics["contamination_used"] = round(contamination, 4)
    metrics["total_samples"] = len(gt_labels)
    return metrics


if __name__ == "__main__":
    import json

    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    results = run(scenarios, ground_truth)
    print(json.dumps(results, indent=2))
