"""
RCA evidence generation.

Produces human-readable evidence strings that explain why a root cause was
selected, grounded in observable system behaviour (logs + graph).
"""
from __future__ import annotations

import networkx as nx

from rca.propagation import analyse_propagation


def generate_evidence(
    root_cause: str,
    incident_services: list[str],
    logs: list[dict],
    graph: nx.DiGraph,
) -> dict:
    """
    Generate structured evidence for an RCA decision.

    Returns:
        {
            "root_cause": str,
            "confidence_basis": str,
            "evidence": [str, ...],          # one line per evidence item
            "propagation_match": bool
        }
    """
    evidence: list[str] = []

    # --- Evidence 1: first error ---
    error_logs = [l for l in logs if l.get("level") == "ERROR"]
    if error_logs:
        first_error = error_logs[0]
        if first_error["service"] == root_cause:
            evidence.append(
                f"'{root_cause}' emitted the first ERROR in this incident "
                f"({first_error['message'][:60]}...)"
            )
        else:
            evidence.append(
                f"First ERROR came from '{first_error['service']}'; "
                f"'{root_cause}' scored highest on downstream impact."
            )

    # --- Evidence 2: downstream impact ---
    propagation_graph = graph.reverse()
    reachable = nx.descendants(propagation_graph, root_cause)
    victims_in_incident = [
        s for s in incident_services if s != root_cause and s in reachable
    ]
    if victims_in_incident:
        evidence.append(
            f"{len(victims_in_incident)} downstream service(s) impacted: "
            f"{', '.join(victims_in_incident)}"
        )

    # --- Evidence 3: graph reachability ---
    prop = analyse_propagation(root_cause, incident_services, graph)
    affected = [s for s in incident_services if s != root_cause]
    if prop["match"] and affected:
        evidence.append(
            f"All affected services ({', '.join(affected)}) are reachable "
            f"downstream from '{root_cause}' in the dependency graph."
        )
    elif prop["unmatched_services"]:
        evidence.append(
            f"WARNING: {prop['unmatched_services']} cannot be explained "
            f"by graph traversal from '{root_cause}'."
        )

    # --- Evidence 4: propagation path ---
    path = prop["propagation_path"]
    if len(path) > 1:
        evidence.append(
            f"Dependency chain: {' -> '.join(path)}"
        )

    # --- Evidence 5: no upstream cause ---
    upstream = list(graph.successors(root_cause))  # what root_cause depends on
    upstream_in_incident = [s for s in upstream if s in incident_services]
    if not upstream_in_incident:
        evidence.append(
            f"'{root_cause}' has no upstream dependency failures in this incident, "
            f"consistent with it being the origin."
        )

    return {
        "root_cause": root_cause,
        "evidence": evidence,
        "propagation_match": prop["match"],
        "propagation_path": path,
    }
