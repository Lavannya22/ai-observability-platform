"""
Create the OpenSearch incidents index.

Usage:
    python -m search.create_index
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from search.opensearch_client import get_client

INDEX_NAME = "incidents"

INDEX_BODY = {
    "settings": {
        "index": {"knn": True}
    },
    "mappings": {
        "properties": {
            "incident_id":        {"type": "keyword"},
            "root_cause":         {"type": "keyword"},
            "affected_services":  {"type": "keyword"},
            "propagation_path":   {"type": "keyword"},
            "confidence_ranking": {"type": "object", "enabled": False},
            "evidence":           {"type": "text"},
            "summary":            {"type": "text"},
            "created_at":         {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 384,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                },
            },
        }
    },
}


def create_index(index: str = INDEX_NAME) -> None:
    client = get_client()
    if client.indices.exists(index=index):
        print(f"Index '{index}' already exists.")
        return
    client.indices.create(index=index, body=INDEX_BODY)
    print(f"Index '{index}' created.")


def delete_and_recreate(index: str = INDEX_NAME) -> None:
    client = get_client()
    if client.indices.exists(index=index):
        client.indices.delete(index=index)
        print(f"Index '{index}' deleted.")
    create_index(index)


if __name__ == "__main__":
    create_index()
