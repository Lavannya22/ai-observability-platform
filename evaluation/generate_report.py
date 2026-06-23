"""
Phase 3 evaluation orchestrator.

Runs all three evaluations (clustering, anomaly detection, RCA) and writes
evaluation/results.json with the consolidated report.

Usage:
    python -m evaluation.generate_report
"""
import json
from pathlib import Path

from ml.model_utils import load_scenarios, load_ground_truth
from evaluation.evaluate_clustering import run as run_clustering
from evaluation.evaluate_anomalies import run as run_anomalies
from evaluation.evaluate_rca import run as run_rca
from evaluation.compare_models import run as run_comparison, print_comparison

ROOT = Path(__file__).parent.parent


def run(output_path: str | None = None) -> dict:
    if output_path is None:
        output_path = str(ROOT / "evaluation" / "results.json")

    config_path = str(ROOT / "configs" / "settings.yaml")
    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    print(f"Running evaluation over {len(scenarios)} scenarios...\n")

    print("[1/3] Clustering evaluation (baseline vs K-Means)...")
    clustering = run_clustering(scenarios, ground_truth, config_path)

    print("[2/3] Anomaly detection (Isolation Forest)...")
    anomalies = run_anomalies(scenarios, ground_truth, config_path)

    print("[3/3] RCA accuracy (Top-1 / Top-3)...")
    rca = run_rca(scenarios, ground_truth, config_path)

    comparison = run_comparison(clustering)

    report = {
        "clustering": {
            "baseline": clustering["baseline"],
            "ml_kmeans": clustering["ml"],
            "comparison": comparison["improvement"],
        },
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
        "per_scenario_rca": rca["per_scenario"],
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    _print_summary(report)
    print(f"\nFull report written to: {output_path}")
    return report


def _print_summary(report: dict):
    c = report["clustering"]
    a = report["anomaly_detection"]
    r = report["rca"]

    print("\n" + "=" * 55)
    print("PHASE 3 EVALUATION SUMMARY")
    print("=" * 55)

    print("\nClustering (V-Measure / NMI):")
    print(f"  Baseline       : {c['baseline']['v_measure']:.4f} / {c['baseline']['nmi']:.4f}")
    print(f"  K-Means ML     : {c['ml_kmeans']['v_measure']:.4f} / {c['ml_kmeans']['nmi']:.4f}")
    delta = c["comparison"]["v_measure_delta"]
    print(f"  Improvement    : {delta:+.4f} V-Measure")

    print("\nAnomaly Detection (Isolation Forest):")
    print(f"  Precision      : {a['precision']:.4f}")
    print(f"  Recall         : {a['recall']:.4f}")
    print(f"  False Pos Rate : {a['false_positive_rate']:.4f}")

    print("\nRCA Accuracy:")
    print(f"  Top-1          : {r['top1_accuracy']:.1%}")
    print(f"  Top-3          : {r['top3_accuracy']:.1%}")
    print("=" * 55)


if __name__ == "__main__":
    run()
