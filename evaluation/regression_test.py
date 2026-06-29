"""
Phase 6 regression validation — re-runs all previous evaluations and
confirms that integration has not degraded any previously achieved target.

Usage:
    python -m evaluation.regression_test

Checks:
  - RCA Top-1 = 100%, Top-3 = 100%
  - HDBSCAN V-Measure >= Greedy baseline (0.6186)
  - Hallucination Rate = 0%
  - MRR = 1.0
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_regression() -> dict:
    results = {}
    passed = []
    failed = []

    from ml.model_utils import load_scenarios, load_ground_truth
    ROOT = Path(__file__).parent.parent
    config_path = str(ROOT / "configs" / "settings.yaml")
    scenarios = load_scenarios(str(ROOT / "scenarios" / "scenarios.json"))
    ground_truth = load_ground_truth(str(ROOT / "scenarios" / "ground_truth.json"))

    print("=" * 60)
    print("Phase 6 Regression Validation")
    print("=" * 60)

    # ── RCA accuracy ──────────────────────────────────────────────
    print("\n[1/4] RCA Accuracy")
    try:
        from evaluation.evaluate_rca import run
        rca = run(scenarios, ground_truth, config_path)
        top1 = rca.get("top1_accuracy", 0)
        top3 = rca.get("top3_accuracy", 0)
        results["rca"] = rca
        _check("RCA Top-1 = 100%", top1 >= 1.0, passed, failed)
        _check("RCA Top-3 = 100%", top3 >= 1.0, passed, failed)
    except Exception as e:
        print(f"  ERROR: {e}")
        failed.append("RCA evaluation failed")

    # ── Clustering (three-way) ────────────────────────────────────
    print("\n[2/4] Clustering — HDBSCAN vs Greedy Baseline")
    try:
        from evaluation.evaluate_hdbscan import run
        clustering = run(scenarios, ground_truth, config_path)
        hdb_vm = clustering.get("hdbscan", {}).get("v_measure", 0)
        greedy_vm = clustering.get("greedy", {}).get("v_measure", 0)
        results["clustering"] = clustering
        _check(
            f"HDBSCAN ({hdb_vm:.4f}) >= Greedy baseline ({greedy_vm:.4f})",
            hdb_vm >= greedy_vm,
            passed, failed,
        )
    except Exception as e:
        print(f"  ERROR: {e}")
        failed.append("Clustering evaluation failed")

    # ── MRR ──────────────────────────────────────────────────────
    print("\n[3/4] Root Cause Ranking — MRR")
    try:
        from evaluation.evaluate_ranking import run
        ranking = run(scenarios, ground_truth, config_path)
        mrr = ranking.get("mrr", 0)
        results["ranking"] = ranking
        _check(f"MRR >= 0.90 (got {mrr:.4f})", mrr >= 0.90, passed, failed)
    except Exception as e:
        print(f"  ERROR: {e}")
        failed.append("MRR evaluation failed")

    # ── Grounding / hallucination ─────────────────────────────────
    print("\n[4/4] Grounding — Hallucination Rate")
    try:
        from evaluation.evaluate_grounding import run_grounding_evaluation
        grounding = run_grounding_evaluation()
        rate = grounding.get("hallucination_rate", 1.0)
        results["grounding"] = grounding
        _check(f"Hallucination Rate <= 5% (got {rate:.1%})", rate <= 0.05, passed, failed)
    except Exception as e:
        print(f"  ERROR: {e}")
        failed.append("Grounding evaluation failed")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Regression Summary: {len(passed)} passed, {len(failed)} failed")
    print("=" * 60)
    for p in passed:
        print(f"  PASS  {p}")
    for f in failed:
        print(f"  FAIL  {f}")

    results["regression_passed"] = len(failed) == 0
    results["passed_checks"] = passed
    results["failed_checks"] = failed
    return results


def _check(label: str, condition: bool, passed: list, failed: list) -> None:
    if condition:
        passed.append(label)
        print(f"  PASS  {label}")
    else:
        failed.append(label)
        print(f"  FAIL  {label}")


if __name__ == "__main__":
    results = run_regression()
    sys.exit(0 if results["regression_passed"] else 1)
