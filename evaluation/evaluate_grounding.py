"""
Grounding / hallucination evaluation.

For each retrieval query, generates a RAG answer and runs the grounding validator.
Computes the average hallucination rate across all queries.

Usage:
    python -m evaluation.evaluate_grounding
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

QUERIES_PATH = Path("evaluation/retrieval_queries.json")


def _make_synthetic_incident(query: dict) -> dict:
    """Build a minimal incident dict matching the query's expected data."""
    root = query["expected_root_cause"]
    affected = [root] + query["expected_services"]
    propagation = [root] + query["expected_services"]
    evidence = [
        f"{root} emitted the first ERROR in this incident",
        f"{len(query['expected_services'])} downstream service(s) impacted: "
        + ", ".join(query["expected_services"]),
        f"All affected services are reachable from {root} in the dependency graph",
        f"Dependency chain: {' -> '.join(propagation)}",
        f"'{root}' has no upstream dependency failures in this incident",
    ]
    return {
        "incident_id": f"EVAL-{query['query_id']}",
        "root_cause": root,
        "affected_services": affected,
        "propagation_path": propagation,
        "evidence": evidence,
        "status": "RESOLVED",
        "confidence_scores": [{"service": root, "confidence": 0.80}],
    }


def run_grounding_evaluation() -> dict:
    from rag.answer_generator import generate_answer

    with open(QUERIES_PATH) as f:
        queries = json.load(f)

    per_query = []
    hallucination_rates = []

    try:
        from search.vector_search import search
        opensearch_available = True
    except ImportError:
        opensearch_available = False

    for q in queries:
        incident = _make_synthetic_incident(q)

        retrieved = []
        if opensearch_available:
            try:
                retrieved = search(q["query"], top_k=3)
            except Exception:
                retrieved = []

        result = generate_answer(q["query"], incident, retrieved)
        rate = result["grounding"]["hallucination_rate"]
        hallucination_rates.append(rate)

        per_query.append({
            "query_id": q["query_id"],
            "query": q["query"],
            "hallucination_rate": rate,
            "grounded": result["grounding"]["grounded"],
            "unsupported_claims": result["grounding"]["unsupported_claims"],
            "llm_used": result.get("llm_used", False),
        })

    avg_rate = sum(hallucination_rates) / len(hallucination_rates) if hallucination_rates else 0.0
    grounded_count = sum(1 for r in per_query if r["grounded"])

    print(f"\nGrounding Evaluation")
    print(f"  Queries evaluated   : {len(queries)}")
    print(f"  Fully grounded      : {grounded_count}/{len(queries)}")
    print(f"  Avg hallucination   : {avg_rate:.4f}  (target <= 0.05)")
    status = "PASS" if avg_rate <= 0.05 else "FAIL"
    print(f"  Hallucination Rate  : {status} ({avg_rate:.4f} vs target 0.05)")

    return {
        "hallucination_rate": round(avg_rate, 4),
        "grounded_queries": grounded_count,
        "total_queries": len(queries),
        "per_query": per_query,
    }


if __name__ == "__main__":
    run_grounding_evaluation()
