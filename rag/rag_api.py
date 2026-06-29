"""
FastAPI RAG endpoint — optional HTTP interface for the RAG pipeline.

Usage:
    uvicorn rag.rag_api:app --port 8001 --reload

Endpoints:
    POST /ask          — answer a question about an incident
    POST /ask/freeform — answer without a specific incident (uses vector search only)
    GET  /health       — liveness check
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from storage import repository
from search.vector_search import search
from rag.answer_generator import generate_answer

app = FastAPI(title="Incident RAG API", version="1.0")


class AskRequest(BaseModel):
    incident_id: str
    question: str
    top_k: int = 5


class FreeformRequest(BaseModel):
    question: str
    top_k: int = 5


@app.post("/ask")
def ask(req: AskRequest):
    incidents = repository.get_all_incidents()
    incident = next(
        (i for i in incidents if i["incident_id"] == req.incident_id), None
    )
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {req.incident_id} not found")

    query = _build_search_query(req.question, incident)
    retrieved = search(query, top_k=req.top_k)
    result = generate_answer(req.question, incident, retrieved)
    return result


@app.post("/ask/freeform")
def ask_freeform(req: FreeformRequest):
    retrieved = search(req.question, top_k=req.top_k)
    if not retrieved:
        raise HTTPException(status_code=404, detail="No incidents found in knowledge store")

    primary = retrieved[0]
    result = generate_answer(req.question, primary, retrieved[1:])
    return result


@app.get("/health")
def health():
    status = {
        "postgres_connected": False,
        "opensearch_connected": False,
        "kafka_connected": False,
        "last_incident_indexed": None,
    }

    # PostgreSQL
    try:
        from storage.postgres import get_connection
        conn = get_connection()
        conn.close()
        status["postgres_connected"] = True
    except Exception as e:
        status["postgres_error"] = str(e)

    # OpenSearch
    try:
        from search.opensearch_client import get_client
        client = get_client()
        info = client.info()
        status["opensearch_connected"] = True
        status["opensearch_version"] = info["version"]["number"]

        # Last indexed incident
        resp = client.search(
            index="incidents",
            body={
                "size": 1,
                "sort": [{"created_at": {"order": "desc"}}],
                "_source": ["incident_id", "created_at"],
            },
        )
        hits = resp["hits"]["hits"]
        if hits:
            status["last_incident_indexed"] = hits[0]["_source"].get("created_at")
    except Exception as e:
        status["opensearch_error"] = str(e)

    # Kafka (lightweight check via metadata fetch)
    try:
        import yaml
        from pathlib import Path
        from confluent_kafka import Producer
        cfg_path = Path(__file__).parent.parent / "configs" / "settings.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)["kafka"]
        p = Producer({"bootstrap.servers": cfg["bootstrap_servers"],
                      "socket.timeout.ms": 2000})
        meta = p.list_topics(timeout=2)
        status["kafka_connected"] = meta is not None
    except Exception as e:
        status["kafka_error"] = str(e)

    all_ok = status["postgres_connected"] and status["opensearch_connected"]
    status["status"] = "ok" if all_ok else "degraded"
    return status


def _build_search_query(question: str, incident: dict) -> str:
    parts = [question]
    if incident.get("root_cause"):
        parts.append(incident["root_cause"])
    parts.extend(incident.get("affected_services") or [])
    return " ".join(parts)
