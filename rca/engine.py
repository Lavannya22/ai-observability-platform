import networkx as nx


def find_root_cause(incident_services: list[str], graph: nx.DiGraph) -> list[dict]:
    """
    Score each incident service by how many other incident services are
    downstream of it (i.e., would fail if it failed).

    The service with the highest score is the most likely root cause.

    Returns top-3 candidates sorted by score descending, each with a
    confidence value normalised to [0, 1].

    NOTE: The original instruction's scoring loop was inverted — it
    incremented downstream victims' scores rather than the origin's score,
    causing reporting (the last victim) to rank #1. This implementation
    fixes that.
    """
    # reversed graph: edge A→B means "A fails → B fails" (propagation direction)
    propagation_graph = graph.reverse()

    scores: dict[str, int] = {}
    for service in incident_services:
        downstream = nx.descendants(propagation_graph, service)
        scores[service] = sum(1 for node in downstream if node in incident_services)

    if not scores:
        return [{"service": incident_services[0], "score": 0, "confidence": 1.0}]

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top3 = ranked[:3]

    max_score = top3[0][1] if top3[0][1] > 0 else 1
    candidates = [
        {
            "service": svc,
            "score": score,
            "confidence": round(score / max_score, 3),
        }
        for svc, score in top3
    ]

    return candidates
