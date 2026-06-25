from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from search.opensearch_client import get_client
from ml.embeddings import embed

INDEX_NAME = "incidents"


def search(query: str, top_k: int = 5, index: str = INDEX_NAME) -> list[dict]:
    """Embed a natural-language query and retrieve the top-k most similar incidents."""
    client = get_client()
    query_vector = embed([query])[0].tolist()

    response = client.search(
        index=index,
        body={
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_vector,
                        "k": top_k,
                    }
                }
            },
            "_source": {"excludes": ["embedding"]},
        },
    )
    return [
        {**hit["_source"], "_score": hit["_score"]}
        for hit in response["hits"]["hits"]
    ]


def search_by_root_cause(root_cause: str, top_k: int = 5, index: str = INDEX_NAME) -> list[dict]:
    """Retrieve incidents with the same root cause (keyword filter)."""
    client = get_client()
    response = client.search(
        index=index,
        body={
            "size": top_k,
            "query": {"term": {"root_cause": root_cause}},
            "_source": {"excludes": ["embedding"]},
        },
    )
    return [hit["_source"] for hit in response["hits"]["hits"]]
