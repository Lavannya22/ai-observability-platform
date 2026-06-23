"""
Clustering evaluation: baseline (TF-IDF greedy) vs ML (TF-IDF + K-Means).

Corpus: ERROR logs emitted by the ROOT CAUSE SERVICE of each scenario.
True label: root_cause service (= same as the emitting service, since we only
take root-cause logs).  Balanced to SAMPLES_PER_CLASS logs per service so
K-Means (which assumes equal-size clusters) is not disadvantaged.

Each scenario is generated with a unique seed_offset (scenario_index × 7)
so log messages vary across scenarios with the same root-cause service.
K-Means benefits from numeric-token normalisation in the vectorizer;
the greedy baseline uses raw messages (no normalisation).
"""
import random
from pathlib import Path

from generator.log_generator import generate_logs
from rca.clustering import cluster_logs
from ml.clustering import cluster, evaluate_clustering
from ml.model_utils import load_scenarios, load_ground_truth

ROOT = Path(__file__).parent.parent
SAMPLES_PER_CLASS = 30   # cap per root-cause service to balance K-Means


def _pool_root_cause_logs(
    scenarios: dict,
    ground_truth: dict,
    config_path: str,
) -> tuple[list[dict], list[str]]:
    """
    For each scenario, take ERROR logs from the ROOT CAUSE SERVICE only.
    Cap to SAMPLES_PER_CLASS logs per service (stratified truncation).

    Returns (pooled_logs, true_labels) where true_label = root_cause service.
    """
    # Accumulate per root-cause service
    by_service: dict[str, list[dict]] = {}

    for idx, sid in enumerate(sorted(scenarios)):
        scenario = scenarios[sid]
        gt = ground_truth[sid]
        root_cause = gt["root_cause"]

        logs = generate_logs(scenario, config_path, seed_offset=idx * 7)

        for log in logs:
            if log["level"] == "ERROR" and log["service"] == root_cause:
                by_service.setdefault(root_cause, []).append(log)

    # Balance: keep at most SAMPLES_PER_CLASS per service (consistent order)
    pooled: list[dict] = []
    true_labels: list[str] = []

    for svc in sorted(by_service):
        logs = by_service[svc][:SAMPLES_PER_CLASS]
        for log in logs:
            augmented = {**log, "_log_id": len(pooled)}
            pooled.append(augmented)
            true_labels.append(svc)

    return pooled, true_labels


def _baseline_pred_labels(pooled_logs: list[dict], config_path: str) -> list[int]:
    """
    Run greedy TF-IDF clustering (rca/clustering.py — no normalisation) on
    the pooled logs.  Returns a cluster_id per log in input order.
    """
    clusters = cluster_logs(pooled_logs, config_path)

    id_to_cluster: dict[int, int] = {}
    for c in clusters:
        for log in c["logs"]:
            id_to_cluster[log["_log_id"]] = c["cluster_id"]

    return [id_to_cluster.get(log["_log_id"], -1) for log in pooled_logs]


def run(
    scenarios: dict,
    ground_truth: dict,
    config_path: str | None = None,
    max_features: int = 500,
) -> dict:
    """
    Evaluate baseline vs K-Means on balanced root-cause ERROR logs.

    k = number of distinct root-cause services (5).

    Returns:
        {
            "baseline": {"v_measure", "nmi", "num_clusters"},
            "ml":       {"v_measure", "nmi", "num_clusters"},
        }
    """
    if config_path is None:
        config_path = str(ROOT / "configs" / "settings.yaml")

    pooled, true_labels = _pool_root_cause_logs(scenarios, ground_truth, config_path)
    messages = [log["message"] for log in pooled]

    k = len(set(true_labels))

    # Baseline — greedy threshold, raw messages (no numeric normalisation)
    baseline_pred = _baseline_pred_labels(pooled, config_path)
    baseline_metrics = evaluate_clustering(true_labels, baseline_pred)
    baseline_metrics["num_clusters"] = len(set(p for p in baseline_pred if p != -1))

    # K-Means ML — TF-IDF with numeric normalisation
    ml_pred, _, _ = cluster(messages, k, max_features)
    ml_pred_list = ml_pred.tolist() if hasattr(ml_pred, "tolist") else list(ml_pred)
    ml_metrics = evaluate_clustering(true_labels, ml_pred_list)
    ml_metrics["num_clusters"] = k

    return {"baseline": baseline_metrics, "ml": ml_metrics}


if __name__ == "__main__":
    import json

    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    results = run(scenarios, ground_truth)
    print(json.dumps(results, indent=2))
