import argparse
import json
import sys
from pathlib import Path

from generator.log_generator import generate_logs, save_logs
from rca.dependency_graph import build_graph
from rca.detector import detect_incidents
from rca.clustering import cluster_logs
from rca.engine import find_root_cause
from rca.explainer import explain_incident
from evaluation.evaluate import evaluate, print_evaluation


def load_scenarios(path: str = "scenarios/scenarios.json") -> dict:
    with open(path) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}


def save_incident_report(scenario_id: str, report: dict, output_dir: str = "data/incidents"):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = Path(output_dir) / f"{scenario_id}.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return str(path)


def run_pipeline(scenario_id: str):
    print(f"\n=== AI Observability Platform — Scenario {scenario_id} ===\n")

    # Load scenario
    scenarios = load_scenarios()
    if scenario_id not in scenarios:
        print(f"ERROR: Scenario '{scenario_id}' not found. Available: {list(scenarios.keys())}")
        sys.exit(1)
    scenario = scenarios[scenario_id]
    print(f"Scenario  : {scenario['name']}")
    print(f"Root Cause: {scenario['root_cause_service']}")
    print(f"Affected  : {scenario['affected_services']}")

    # Step 1: Generate logs
    print("\n[1/6] Generating logs...")
    logs = generate_logs(scenario)
    log_path = save_logs(logs, scenario_id)
    error_count = sum(1 for l in logs if l["level"] == "ERROR")
    print(f"      {len(logs)} logs generated ({error_count} errors) -> {log_path}")

    # Step 2: Detect incidents
    print("\n[2/6] Detecting incidents...")
    incidents = detect_incidents(logs)
    incident_services = [i["service"] for i in incidents]
    print(f"      Incident services detected: {incident_services}")

    if not incidents:
        print("      No incidents detected. Exiting.")
        sys.exit(0)

    # Step 3: Cluster error logs
    print("\n[3/6] Clustering error logs...")
    clusters = cluster_logs(logs)
    print(f"      {error_count} error logs -> {len(clusters)} clusters")
    for c in clusters:
        print(f"      Cluster {c['cluster_id']}: {c['size']} logs | services: {c['services']}")

    # Step 4: Root cause analysis
    print("\n[4/6] Running root cause analysis...")
    graph = build_graph()
    rca_candidates = find_root_cause(incident_services, graph)
    root_cause = rca_candidates[0]["service"]
    print(f"      Top-3 RCA candidates:")
    for rank, candidate in enumerate(rca_candidates, 1):
        print(f"        #{rank} {candidate['service']} (confidence: {candidate['confidence']:.2f})")

    # Step 5: Generate explanation
    print("\n[5/6] Generating explanation...")
    sample_error_logs = [l for l in logs if l["level"] == "ERROR"][:10]
    downstream_affected = [i["service"] for i in incidents if i["service"] != root_cause]
    explanation = explain_incident(
        root_cause=root_cause,
        affected_services=downstream_affected,
        sample_logs=sample_error_logs,
        failure_type=scenario["failure_type"],
    )
    print("\n" + explanation)

    # Step 6: Evaluate
    print("\n[6/6] Evaluating results...")
    eval_results = evaluate(
        scenario_id=scenario_id,
        incidents=incidents,
        clusters=clusters,
        rca_candidates=rca_candidates,
        logs=logs,
    )
    print_evaluation(eval_results)

    # Save incident report
    report = {
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "logs_generated": len(logs),
        "incidents": incidents,
        "clusters": [{"cluster_id": c["cluster_id"], "size": c["size"], "services": c["services"], "summary": c["summary"]} for c in clusters],
        "rca_candidates": rca_candidates,
        "root_cause": root_cause,
        "explanation": explanation,
        "evaluation": eval_results,
    }
    report_path = save_incident_report(scenario_id, report)
    print(f"\nIncident report saved -> {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Observability Platform — Phase 1")
    parser.add_argument("--scenario", required=True, help="Scenario ID (e.g. S001)")
    args = parser.parse_args()
    run_pipeline(args.scenario)
