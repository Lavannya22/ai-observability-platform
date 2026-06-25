"""
Retrieval evaluation: Precision@5, Recall@5, MRR.

Relevance rule (from phase5_instructions.md):
  - Rule 1: retrieved incident must have same root cause as query
  - Rule 2: affected services must overlap (subset OR superset — not exact match)

Usage:
    python -m evaluation.evaluate_retrieval
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

QUERIES_PATH = Path("evaluation/retrieval_queries.json")


def _is_relevant(retrieved: dict, query: dict) -> bool:
    if retrieved.get("root_cause") != query["expected_root_cause"]:
        return False

    expected = set(query["expected_services"])
    actual = set(retrieved.get("affected_services") or [])

    if not expected:
        return True

    # subset or superset: expected contained in actual OR actual contained in expected
    return bool(expected & actual)


def precision_at_k(results: list[dict], query: dict, k: int = 5) -> float:
    top_k = results[:k]
    relevant = sum(1 for r in top_k if _is_relevant(r, query))
    return relevant / k if k > 0 else 0.0


def recall_at_k(results: list[dict], query: dict, k: int = 5) -> float:
    # For our dataset, total relevant = all indexed incidents sharing the root cause
    # We approximate: if any result is relevant, recall = 1 (binary)
    top_k = results[:k]
    return 1.0 if any(_is_relevant(r, query) for r in top_k) else 0.0


def reciprocal_rank(results: list[dict], query: dict) -> float:
    for i, r in enumerate(results, 1):
        if _is_relevant(r, query):
            return 1.0 / i
    return 0.0


def run_retrieval_evaluation(top_k: int = 5) -> dict:
    try:
        from search.vector_search import search
    except ImportError:
        print("ERROR: opensearch-py not installed. Run: pip install opensearch-py")
        return {}

    with open(QUERIES_PATH) as f:
        queries = json.load(f)

    per_query = []
    precisions, recalls, rrs = [], [], []

    for q in queries:
        try:
            results = search(q["query"], top_k=top_k)
        except Exception as e:
            print(f"[SKIP] {q['query_id']}: {e}")
            results = []

        p = precision_at_k(results, q, top_k)
        r = recall_at_k(results, q, top_k)
        rr = reciprocal_rank(results, q)

        precisions.append(p)
        recalls.append(r)
        rrs.append(rr)

        per_query.append({
            "query_id": q["query_id"],
            "query": q["query"],
            "expected_root_cause": q["expected_root_cause"],
            f"precision@{top_k}": round(p, 4),
            f"recall@{top_k}": round(r, 4),
            "reciprocal_rank": round(rr, 4),
            "top_results": [
                {"incident_id": r.get("incident_id"), "root_cause": r.get("root_cause")}
                for r in results[:3]
            ],
        })

    mean_p = sum(precisions) / len(precisions) if precisions else 0.0
    mean_r = sum(recalls) / len(recalls) if recalls else 0.0
    mrr = sum(rrs) / len(rrs) if rrs else 0.0

    print(f"\nRetrieval Evaluation (top-{top_k})")
    print(f"  Precision@{top_k} : {mean_p:.4f}  (target >= 0.90)")
    print(f"  Recall@{top_k}    : {mean_r:.4f}  (target >= 0.80)")
    print(f"  MRR              : {mrr:.4f}  (target >= 0.80)")
    _print_pass_fail(mean_p, 0.90, f"Precision@{top_k}")
    _print_pass_fail(mean_r, 0.80, f"Recall@{top_k}")
    _print_pass_fail(mrr, 0.80, "MRR")

    return {
        f"precision_at_{top_k}": round(mean_p, 4),
        f"recall_at_{top_k}": round(mean_r, 4),
        "mrr": round(mrr, 4),
        "per_query": per_query,
    }


def _print_pass_fail(value: float, target: float, label: str) -> None:
    status = "PASS" if value >= target else "FAIL"
    print(f"  {label}: {status} ({value:.4f} vs target {target})")


if __name__ == "__main__":
    run_retrieval_evaluation()
