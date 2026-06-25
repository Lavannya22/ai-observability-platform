from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from search.opensearch_client import get_client
from ml.embeddings import embed

INDEX_NAME = "incidents"


def index_document(doc: dict, index: str = INDEX_NAME) -> str:
    """Embed the summary and index the document to OpenSearch."""
    client = get_client()

    summary = doc.get("summary", "")
    embedding = embed([summary])[0].tolist()

    body = {**doc, "embedding": embedding}

    response = client.index(
        index=index,
        id=doc["incident_id"],
        body=body,
        refresh=True,
    )
    print(f"[INDEX] {doc['incident_id']} -> {index} ({response['result']})")
    return response["result"]


def bulk_index(docs: list[dict], index: str = INDEX_NAME) -> int:
    """Index multiple documents. Returns count of indexed documents."""
    indexed = 0
    for doc in docs:
        try:
            index_document(doc, index)
            indexed += 1
        except Exception as e:
            print(f"[INDEX ERROR] {doc.get('incident_id', '?')}: {e}")
    return indexed
