"""
Kafka consumer — reads logs, persists to PostgreSQL, manages incident lifecycle.

Incident lifecycle:
    OPEN       → error arrived, not yet at threshold
    DETECTING  → threshold crossed, accumulating logs
    ACTIVE     → RCA computed and stored
    RESOLVED   → no activity for timeout_seconds

Usage:
    python ingestion/consumer.py
"""

import json
import sys
import threading
import time
import uuid
import yaml
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import networkx as nx
from confluent_kafka import Consumer, KafkaError

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.postgres import create_tables
from storage import repository
from rca.dependency_graph import build_graph
from ml.hdbscan_clustering import cluster_logs   # Phase 6: promoted from greedy TF-IDF
from rca.engine import rank_root_causes
from rca.explainer import explain_incident
from rca.evidence import generate_evidence
from rca.propagation import analyse_propagation

# Phase 5: knowledge indexing (optional — requires OpenSearch)
try:
    from knowledge.knowledge_builder import build_and_index as _index_incident
    _KNOWLEDGE_STORE_AVAILABLE = True
except ImportError:
    _KNOWLEDGE_STORE_AVAILABLE = False


ROOT = Path(__file__).parent.parent


def load_config(path: str = "configs/settings.yaml") -> dict:
    with open(ROOT / path) as f:
        return yaml.safe_load(f)


# ── Incident assignment helpers ───────────────────────────────────────────────

def graph_related(service: str, incident_services: list[str], graph: nx.DiGraph) -> bool:
    """True if service is graph-connected (ancestor or descendant) to any incident service.

    Checks both directions so out-of-order log arrival still merges correctly.
    """
    for inc_service in incident_services:
        try:
            if nx.has_path(graph, service, inc_service):
                return True
            if nx.has_path(graph, inc_service, service):
                return True
        except nx.NodeNotFound:
            pass
    return False


def within_merge_window(log_time: datetime, incident: dict, window_minutes: int) -> bool:
    last_log = incident["last_log_at"]
    if last_log is None:
        return True
    if not isinstance(last_log, datetime):
        last_log = datetime.fromisoformat(str(last_log))
    return (log_time - last_log) <= timedelta(minutes=window_minutes)


def assign_incident(
    log: dict,
    active_incidents: list[dict],
    graph: nx.DiGraph,
    merge_window_minutes: int,
) -> str | None:
    """Return the ID of an existing incident to join, or None to create a new one."""
    log_time = datetime.utcnow()  # use wall-clock time, not the log's simulation timestamp
    for incident in active_incidents:
        if within_merge_window(log_time, incident, merge_window_minutes):
            if graph_related(log["service"], incident["affected_services"], graph):
                return incident["incident_id"]
    return None


# ── RCA trigger ───────────────────────────────────────────────────────────────

def run_rca_for_incident(incident_id: str, graph: nx.DiGraph, error_threshold: int):
    """Pull incident logs, run RCA + Phase 4 evidence, update incident record."""
    logs = repository.get_logs_for_incident(incident_id)

    error_counts: dict[str, int] = defaultdict(int)
    for log in logs:
        if log["level"] == "ERROR":
            error_counts[log["service"]] += 1

    incident_services = [
        svc for svc, count in error_counts.items() if count >= error_threshold
    ]
    if not incident_services:
        return

    repository.update_incident(incident_id, status="DETECTING")

    clusters = cluster_logs(logs)

    # Phase 4: probability-normalised ranking
    ranked = rank_root_causes(incident_services, graph)
    if not ranked:
        return

    root_cause = ranked[0]["service"]
    downstream = [s for s in incident_services if s != root_cause]

    explanation = explain_incident(
        root_cause=root_cause,
        affected_services=downstream,
        sample_logs=[l for l in logs if l["level"] == "ERROR"][:10],
        failure_type="cascade_failure",
    )

    # Phase 4: evidence + propagation
    ev = generate_evidence(root_cause, incident_services, logs, graph)
    prop = analyse_propagation(root_cause, incident_services, graph)

    import json as _json
    repository.update_incident(
        incident_id,
        root_cause=root_cause,
        explanation=explanation,
        status="ACTIVE",
        evidence=_json.dumps(ev["evidence"]),
        propagation_path=_json.dumps(prop["propagation_path"]),
        confidence_scores=_json.dumps([
            {"service": c["service"], "confidence": c["confidence"]} for c in ranked
        ]),
    )

    print(
        f"[RCA] {incident_id}: root_cause={root_cause} | "
        f"services={incident_services} | clusters={len(clusters)} | "
        f"propagation={'MATCH' if prop['match'] else 'MISMATCH'}"
    )


# ── Background resolver ───────────────────────────────────────────────────────

def resolve_stale_incidents(config_path: str, graph: nx.DiGraph):
    """Background thread: auto-resolve incidents with no recent log activity.
    Reads timeout from config on every cycle so changes take effect without restart.
    """
    while True:
        time.sleep(10)
        try:
            timeout_seconds = load_config(config_path)["incident"]["timeout_seconds"]
            active = repository.get_active_incidents()
            now = datetime.utcnow()
            for incident in active:
                last_log = incident["last_log_at"]
                if last_log is None:
                    continue
                if not isinstance(last_log, datetime):
                    last_log = datetime.fromisoformat(str(last_log))
                age = (now - last_log).total_seconds()
                if age >= timeout_seconds:
                    repository.update_incident(
                        incident["incident_id"],
                        status="RESOLVED",
                        resolved_at=now.isoformat(),
                    )
                    print(
                        f"[RESOLVED] {incident['incident_id']} "
                        f"auto-closed after {age:.0f}s inactivity"
                    )
                    # Phase 5: index resolved incident into knowledge store
                    if _KNOWLEDGE_STORE_AVAILABLE:
                        try:
                            incidents = repository.get_all_incidents()
                            resolved = next(
                                (i for i in incidents
                                 if i["incident_id"] == incident["incident_id"]),
                                None,
                            )
                            if resolved:
                                _index_incident(resolved)
                        except Exception as e:
                            print(f"[KNOWLEDGE] Index failed for {incident['incident_id']}: {e}")
        except Exception as e:
            print(f"[RESOLVER ERROR] {e}")


# ── Main consumer loop ────────────────────────────────────────────────────────

def consume(config_path: str = str(ROOT / "configs/settings.yaml")):
    config = load_config(config_path)
    kafka_cfg = config["kafka"]
    incident_cfg = config["incident"]
    error_threshold = config["detection"]["error_threshold"]

    graph = build_graph(config_path)

    try:
        create_tables(config_path)
    except Exception as e:
        print(f"\nERROR: Cannot connect to PostgreSQL — {e}")
        print("Run PostgreSQL first, then: python storage/setup_db.py")
        sys.exit(1)

    resolver = threading.Thread(
        target=resolve_stale_incidents,
        args=(config_path, graph),
        daemon=True,
    )
    resolver.start()

    consumer = Consumer({
        "bootstrap.servers": kafka_cfg["bootstrap_servers"],
        "group.id": "observability-consumer",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([kafka_cfg["topic"]])

    print(f"Consumer listening on topic '{kafka_cfg['topic']}' ...")

    incident_error_counts: dict[str, int] = defaultdict(int)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"[KAFKA ERROR] {msg.error()}")
                continue

            log = json.loads(msg.value().decode("utf-8"))

            if log["level"] == "ERROR":
                active_incidents = repository.get_active_incidents()

                incident_id = assign_incident(
                    log, active_incidents, graph, incident_cfg["merge_window_minutes"]
                )

                if incident_id is None:
                    incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
                    repository.create_incident(incident_id, log["service"])
                    print(f"[NEW] {incident_id} — triggered by {log['service']}")
                else:
                    for inc in active_incidents:
                        if inc["incident_id"] == incident_id:
                            if log["service"] not in inc["affected_services"]:
                                updated = inc["affected_services"] + [log["service"]]
                                repository.update_incident(
                                    incident_id, affected_services=updated
                                )
                            break

                received_at = datetime.utcnow()
                repository.update_incident(
                    incident_id, last_log_at=received_at.isoformat()
                )
                repository.insert_log(log, incident_id)

                incident_error_counts[incident_id] += 1
                count = incident_error_counts[incident_id]
                if count >= error_threshold and count % 5 == 0:
                    run_rca_for_incident(incident_id, graph, error_threshold)

            else:
                repository.insert_log(log, None)

            print(f"[LOG] {log['level']:7s} {log['service']:12s} {log['message'][:60]}")

    except KeyboardInterrupt:
        print("\nShutting down consumer...")
    finally:
        consumer.close()


if __name__ == "__main__":
    consume()
