"""
Build and index a knowledge document from a resolved incident.

Called automatically by the consumer when an incident transitions ACTIVE -> RESOLVED.
Can also be run manually to backfill existing resolved incidents.

Usage (backfill):
    python -m knowledge.knowledge_builder
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.incident_document import build_document
from knowledge.indexer import index_document


def build_and_index(incident: dict) -> dict:
    """Build a knowledge document from a resolved incident and index it."""
    doc = build_document(incident)
    index_document(doc)
    return doc


def backfill_from_db() -> int:
    """Index all resolved incidents that are not yet in OpenSearch."""
    from storage import repository
    from search.opensearch_client import get_client

    client = get_client()
    incidents = repository.get_all_incidents(limit=1000)
    resolved = [i for i in incidents if i["status"] == "RESOLVED"]

    indexed = 0
    for incident in resolved:
        iid = incident["incident_id"]
        try:
            exists = client.exists(index="incidents", id=iid)
            if exists:
                print(f"[SKIP] {iid} already indexed")
                continue
            build_and_index(incident)
            indexed += 1
        except Exception as e:
            print(f"[ERROR] {iid}: {e}")

    print(f"Backfill complete: {indexed}/{len(resolved)} incidents indexed.")
    return indexed


if __name__ == "__main__":
    backfill_from_db()
