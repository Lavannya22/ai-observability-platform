"""
Failure propagation analysis.

Given a set of observed incident services and the dependency graph, determines:
  - the propagation path from root cause to all reachable downstream services
  - whether observed affected services are explainable by graph traversal

Match rules (from Phase 4 spec):
  Rule 1 — Reachability: every affected service must be reachable downstream
            from the predicted root cause.
  Rule 2 — Exact path equality is NOT required: intermediate nodes may be
            missing from observations and still count as a match.
  Rule 3 — Mismatch: any affected service not reachable from root cause = NO MATCH.
"""
from __future__ import annotations

import networkx as nx


def get_propagation_path(
    root_cause: str,
    graph: nx.DiGraph,
) -> list[str]:
    """
    Return the ordered propagation path starting from root_cause.

    Direction: root_cause → services that fail because of it.

    The graph stores edges as dependent → dependency (A depends on B).
    Failure propagates in reverse: if B fails, A fails too.
    We follow the reversed graph to discover downstream victims.
    """
    propagation_graph = graph.reverse()

    # BFS from root_cause following propagation direction
    path = [root_cause]
    visited = {root_cause}
    queue = list(propagation_graph.successors(root_cause))

    # Build an ordered traversal respecting dependency depth
    # Use topological sort on the subgraph of reachable nodes
    reachable = nx.descendants(propagation_graph, root_cause)
    reachable.add(root_cause)

    subgraph = propagation_graph.subgraph(reachable)
    try:
        ordered = list(nx.topological_sort(subgraph))
    except nx.NetworkXUnfeasible:
        ordered = [root_cause] + list(reachable - {root_cause})

    return ordered


def analyse_propagation(
    root_cause: str,
    affected_services: list[str],
    graph: nx.DiGraph,
) -> dict:
    """
    Analyse whether the observed failure propagation matches the dependency graph.

    Returns:
        {
            "root_cause": str,
            "propagation_path": [str, ...],      # full graph path from root
            "observed_services": [str, ...],      # affected_services (excluding root)
            "match": bool,                         # Rules 1-3 satisfied
            "unmatched_services": [str, ...]       # services violating Rule 3
        }
    """
    propagation_graph = graph.reverse()
    reachable = nx.descendants(propagation_graph, root_cause)

    unmatched = [
        svc for svc in affected_services
        if svc != root_cause and svc not in reachable
    ]

    match = len(unmatched) == 0

    return {
        "root_cause": root_cause,
        "propagation_path": get_propagation_path(root_cause, graph),
        "observed_services": [s for s in affected_services if s != root_cause],
        "match": match,
        "unmatched_services": unmatched,
    }
