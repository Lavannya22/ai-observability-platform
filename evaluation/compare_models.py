"""
Side-by-side comparison of baseline vs ML clustering performance.
"""


def run(clustering_results: dict) -> dict:
    """
    Compare baseline (greedy TF-IDF) against ML (K-Means) clustering.

    Args:
        clustering_results — output of evaluate_clustering.run()

    Returns:
        {
            "baseline": {...},
            "ml":       {...},
            "improvement": {
                "v_measure_delta": float,
                "nmi_delta":       float,
                "better_clustering": bool,
            }
        }
    """
    baseline = clustering_results["baseline"]
    ml = clustering_results["ml"]

    delta_vm = round(ml["v_measure"] - baseline["v_measure"], 4)
    delta_nmi = round(ml["nmi"] - baseline["nmi"], 4)

    return {
        "baseline": baseline,
        "ml": ml,
        "improvement": {
            "v_measure_delta": delta_vm,
            "nmi_delta": delta_nmi,
            "better_clustering": delta_vm > 0,
        },
    }


def print_comparison(comparison: dict):
    b = comparison["baseline"]
    m = comparison["ml"]
    imp = comparison["improvement"]

    print("\n--- CLUSTERING MODEL COMPARISON ---")
    print(f"{'Metric':<20} {'Baseline':>10} {'K-Means ML':>12} {'Delta':>8}")
    print("-" * 52)
    print(f"{'V-Measure':<20} {b['v_measure']:>10.4f} {m['v_measure']:>12.4f} {imp['v_measure_delta']:>+8.4f}")
    print(f"{'NMI':<20} {b['nmi']:>10.4f} {m['nmi']:>12.4f} {imp['nmi_delta']:>+8.4f}")
    print(f"{'# Clusters':<20} {b['num_clusters']:>10} {m['num_clusters']:>12}")
    print("-" * 52)
    winner = "K-Means ML" if imp["better_clustering"] else "Baseline"
    print(f"Better clustering: {winner}")
