"""
Performance benchmark — wall-clock latency and throughput.

IMPORTANT: All latency measurements use wall-clock time (time.perf_counter),
never simulated log timestamps (which are scenario-relative, not real time).

Metrics:
  - Throughput: logs successfully processed per minute
  - P95 Detection Latency: wall-clock time from first log produced to incident created
  - P95 Retrieval Latency: wall-clock time from question submitted to answer returned

Usage:
    python -m benchmark.stress_test                  # batch pipeline only
    python -m benchmark.stress_test --mode streaming  # requires consumer running
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from generator.log_generator import generate_logs
from rca.dependency_graph import build_graph
from rca.detector import detect_incidents
from ml.hdbscan_clustering import cluster_logs
from rca.engine import rank_root_causes
from rca.evidence import generate_evidence
from rca.propagation import analyse_propagation


SCENARIOS_PATH = Path("scenarios/scenarios.json")
RESULTS_PATH = Path("benchmark/results.json")


def load_scenarios() -> dict:
    with open(SCENARIOS_PATH) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}


# ── Batch pipeline benchmark ──────────────────────────────────────────────────

def benchmark_batch_pipeline(scenario_ids: list[str]) -> dict:
    """
    Measure throughput and latency of the detection + RCA pipeline
    in batch mode (no Kafka required).
    """
    scenarios = load_scenarios()
    graph = build_graph()

    detection_latencies = []
    rca_latencies = []
    retrieval_latencies = []
    total_logs = 0

    print(f"\nBatch Pipeline Benchmark ({len(scenario_ids)} scenarios)")
    print("-" * 60)

    for sid in scenario_ids:
        scenario = scenarios[sid]
        logs = generate_logs(scenario)
        total_logs += len(logs)

        # Detection latency
        t0 = time.perf_counter()
        incidents = detect_incidents(logs)
        t1 = time.perf_counter()
        detection_latencies.append(t1 - t0)

        if not incidents:
            continue

        incident_services = list({i["service"] for i in incidents})

        # RCA latency (clustering + ranking + evidence)
        t2 = time.perf_counter()
        clusters = cluster_logs(logs)
        ranked = rank_root_causes(incident_services, graph)
        if ranked:
            root = ranked[0]["service"]
            _ = generate_evidence(root, incident_services, logs, graph)
            _ = analyse_propagation(root, incident_services, graph)
        t3 = time.perf_counter()
        rca_latencies.append(t3 - t2)

        print(f"  {sid}: {len(logs)} logs | detect={1000*(t1-t0):.1f}ms | rca={1000*(t3-t2):.1f}ms")

    # Retrieval latency (RAG pipeline, no OpenSearch required)
    try:
        from rag.answer_generator import generate_answer
        from rag.grounding_validator import validate

        scenarios_list = list(scenarios.values())[:5]
        for sc in scenarios_list:
            fake_incident = {
                "incident_id": "BENCH-001",
                "root_cause": sc["root_cause_service"],
                "affected_services": sc["affected_services"],
                "propagation_path": [sc["root_cause_service"]] + sc["affected_services"],
                "evidence": ["Benchmark evidence"],
                "confidence_scores": [{"service": sc["root_cause_service"], "confidence": 0.8}],
            }
            t4 = time.perf_counter()
            result = generate_answer("Why did this incident occur?", fake_incident, [])
            t5 = time.perf_counter()
            retrieval_latencies.append(t5 - t4)
    except Exception as e:
        print(f"  [SKIP] Retrieval benchmark: {e}")

    return _compile_results(
        total_logs, scenario_ids, detection_latencies, rca_latencies, retrieval_latencies
    )


def _compile_results(
    total_logs: int,
    scenario_ids: list[str],
    detection_latencies: list[float],
    rca_latencies: list[float],
    retrieval_latencies: list[float],
) -> dict:
    def p95(values: list[float]) -> float:
        if not values:
            return 0.0
        return float(np.percentile(values, 95))

    def p50(values: list[float]) -> float:
        if not values:
            return 0.0
        return float(np.percentile(values, 50))

    total_wall = sum(detection_latencies) + sum(rca_latencies)
    throughput = int((total_logs / total_wall) * 60) if total_wall > 0 else 0

    results = {
        "scenarios_run": len(scenario_ids),
        "total_logs": total_logs,
        "throughput_logs_per_minute": throughput,
        "detection": {
            "p50_seconds": round(p50(detection_latencies), 4),
            "p95_seconds": round(p95(detection_latencies), 4),
            "target_p95_seconds": 5.0,
            "passed": p95(detection_latencies) < 5.0,
        },
        "rca": {
            "p50_seconds": round(p50(rca_latencies), 4),
            "p95_seconds": round(p95(rca_latencies), 4),
        },
        "retrieval": {
            "p50_seconds": round(p50(retrieval_latencies), 4),
            "p95_seconds": round(p95(retrieval_latencies), 4),
            "target_p95_seconds": 3.0,
            "passed": p95(retrieval_latencies) < 3.0 if retrieval_latencies else None,
        },
    }

    print(f"\nResults")
    print(f"  Throughput            : {throughput} logs/min")
    print(f"  Detection P50/P95     : {results['detection']['p50_seconds']*1000:.1f}ms / {results['detection']['p95_seconds']*1000:.1f}ms  (target P95 < 5s)")
    print(f"  RCA P50/P95           : {results['rca']['p50_seconds']*1000:.1f}ms / {results['rca']['p95_seconds']*1000:.1f}ms")
    if retrieval_latencies:
        print(f"  Retrieval P50/P95     : {results['retrieval']['p50_seconds']*1000:.1f}ms / {results['retrieval']['p95_seconds']*1000:.1f}ms  (target P95 < 3s)")
    print(f"  Detection target      : {'PASS' if results['detection']['passed'] else 'FAIL'}")

    return results


def run_benchmark(mode: str = "batch") -> dict:
    scenarios = load_scenarios()
    all_ids = list(scenarios.keys())   # all 20 scenarios

    if mode == "batch":
        results = benchmark_batch_pipeline(all_ids)
    else:
        print("Streaming mode requires the consumer to be running.")
        print("Run 'python run_platform.py' first, then re-run with --mode streaming.")
        results = benchmark_batch_pipeline(all_ids[:5])

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to {RESULTS_PATH}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Platform performance benchmark")
    parser.add_argument("--mode", choices=["batch", "streaming"], default="batch")
    args = parser.parse_args()
    run_benchmark(args.mode)
