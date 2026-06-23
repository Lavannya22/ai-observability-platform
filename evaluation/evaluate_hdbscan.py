"""
Three-way clustering comparison: Greedy baseline / K-Means / HDBSCAN.

All three methods run on the EXACT same evaluation corpus used in Phase 3:
ERROR logs from root-cause services only, balanced to SAMPLES_PER_CLASS per
service.  This preserves comparability with Phase 3 results.

Cluster count is always reported alongside V-Measure and NMI to prevent
score inflation through over-fragmentation.
"""
from pathlib import Path

from ml.model_utils import load_scenarios, load_ground_truth
from ml.clustering import cluster as kmeans_cluster, evaluate_clustering
from ml.hdbscan_clustering import cluster as hdbscan_cluster, evaluate_hdbscan
from evaluation.evaluate_clustering import _pool_root_cause_logs, _baseline_pred_labels

ROOT = Path(__file__).parent.parent


def run(
    scenarios: dict,
    ground_truth: dict,
    config_path: str | None = None,
    min_cluster_size: int = 5,
    min_samples: int = 3,
    max_features: int = 500,
) -> dict:
    """
    Run Greedy / K-Means / HDBSCAN on the same balanced root-cause corpus.

    Returns:
        {
            "greedy":   {"v_measure", "nmi", "num_clusters"},
            "kmeans":   {"v_measure", "nmi", "num_clusters"},
            "hdbscan":  {"v_measure", "nmi", "num_clusters", "noise_points", "noise_rate"},
        }
    """
    if config_path is None:
        config_path = str(ROOT / "configs" / "settings.yaml")

    pooled, true_labels = _pool_root_cause_logs(scenarios, ground_truth, config_path)
    messages = [log["message"] for log in pooled]
    k = len(set(true_labels))

    # --- Greedy baseline ---
    greedy_pred = _baseline_pred_labels(pooled, config_path)
    greedy_metrics = evaluate_clustering(true_labels, greedy_pred)
    greedy_metrics["num_clusters"] = len(set(p for p in greedy_pred if p != -1))

    # --- K-Means ---
    km_pred, _, _ = kmeans_cluster(messages, k, max_features)
    km_pred_list = km_pred.tolist() if hasattr(km_pred, "tolist") else list(km_pred)
    km_metrics = evaluate_clustering(true_labels, km_pred_list)
    km_metrics["num_clusters"] = k

    # --- HDBSCAN ---
    hdb_pred, _ = hdbscan_cluster(messages, min_cluster_size, min_samples)
    hdb_metrics = evaluate_hdbscan(true_labels, hdb_pred)

    return {
        "greedy": greedy_metrics,
        "kmeans": km_metrics,
        "hdbscan": hdb_metrics,
    }


if __name__ == "__main__":
    import json

    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    results = run(scenarios, ground_truth)

    print("\nClustering Comparison (same corpus, three methods)")
    print("-" * 60)
    header = f"{'Method':<12} {'V-Measure':>10} {'NMI':>8} {'Clusters':>10} {'Noise':>8}"
    print(header)
    print("-" * 60)

    for method, m in results.items():
        noise = f"{m.get('noise_rate', 0.0):.1%}" if method == "hdbscan" else "N/A"
        print(
            f"{method:<12} {m['v_measure']:>10.4f} {m['nmi']:>8.4f} "
            f"{m['num_clusters']:>10} {noise:>8}"
        )

    print()
    print(json.dumps(results, indent=2))
