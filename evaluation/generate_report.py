"""
Evaluation orchestrator — Phase 3 + Phase 4.

Runs all evaluations and writes evaluation/results.json.

Usage:
    python -m evaluation.generate_report
"""
import json
from pathlib import Path

from ml.model_utils import load_scenarios, load_ground_truth
from evaluation.evaluate_clustering import run as run_clustering
from evaluation.evaluate_anomalies import run as run_anomalies
from evaluation.evaluate_rca import run as run_rca
from evaluation.evaluate_hdbscan import run as run_hdbscan
from evaluation.evaluate_ranking import run as run_ranking
from evaluation.compare_models import run as run_comparison

ROOT = Path(__file__).parent.parent


def run(output_path: str | None = None) -> dict:
    if output_path is None:
        output_path = str(ROOT / "evaluation" / "results.json")

    config_path = str(ROOT / "configs" / "settings.yaml")
    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    print(f"Running evaluation over {len(scenarios)} scenarios...\n")

    print("[1/5] Clustering evaluation (baseline vs K-Means)...")
    clustering = run_clustering(scenarios, ground_truth, config_path)

    print("[2/5] Anomaly detection (Isolation Forest)...")
    anomalies = run_anomalies(scenarios, ground_truth, config_path)

    print("[3/5] RCA accuracy (Top-1 / Top-3) — regression test...")
    rca = run_rca(scenarios, ground_truth, config_path)

    print("[4/5] HDBSCAN three-way clustering comparison...")
    hdbscan_results = run_hdbscan(scenarios, ground_truth, config_path)

    print("[5/5] Root cause ranking (MRR)...")
    ranking = run_ranking(scenarios, ground_truth, config_path)

    comparison = run_comparison(clustering)

    report = {
        "clustering": {
            "baseline": clustering["baseline"],
            "ml_kmeans": clustering["ml"],
            "comparison": comparison["improvement"],
        },
        "clustering_three_way": hdbscan_results,
        "anomaly_detection": {
            k: v for k, v in anomalies.items()
            if k not in ("tp", "fp", "fn", "tn")
        },
        "anomaly_detection_detail": {
            k: anomalies[k] for k in ("tp", "fp", "fn", "tn")
        },
        "rca": {
            "top1_accuracy": rca["top1_accuracy"],
            "top3_accuracy": rca["top3_accuracy"],
        },
        "ranking": {
            "mrr": ranking["mrr"],
        },
        "per_scenario_rca": rca["per_scenario"],
        "per_scenario_ranking": ranking["per_scenario"],
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    _print_summary(report)
    print(f"\nFull report written to: {output_path}")
    return report


def _print_summary(report: dict):
    c = report["clustering"]
    h = report["clustering_three_way"]
    a = report["anomaly_detection"]
    r = report["rca"]
    rk = report["ranking"]

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY (Phase 3 + Phase 4)")
    print("=" * 60)

    print("\nClustering — Three-Way Comparison (V-Measure / clusters):")
    print(f"  Greedy baseline: {h['greedy']['v_measure']:.4f}  ({h['greedy']['num_clusters']} clusters)")
    print(f"  K-Means        : {h['kmeans']['v_measure']:.4f}  ({h['kmeans']['num_clusters']} clusters)")
    noise_pct = h['hdbscan'].get('noise_rate', 0) * 100
    print(f"  HDBSCAN        : {h['hdbscan']['v_measure']:.4f}  ({h['hdbscan']['num_clusters']} clusters, {noise_pct:.1f}% noise)")

    print("\nAnomaly Detection (Isolation Forest):")
    print(f"  Precision      : {a['precision']:.4f}")
    print(f"  Recall         : {a['recall']:.4f}")
    print(f"  False Pos Rate : {a['false_positive_rate']:.4f}")

    print("\nRCA (regression — must stay at 100%):")
    print(f"  Top-1          : {r['top1_accuracy']:.1%}")
    print(f"  Top-3          : {r['top3_accuracy']:.1%}")

    mrr_status = "PASS" if rk["mrr"] >= 0.90 else "FAIL"
    print(f"\nRoot Cause Ranking:")
    print(f"  MRR            : {rk['mrr']:.4f}  [{mrr_status} — target >= 0.90]")
    print("=" * 60)


if __name__ == "__main__":
    run()
