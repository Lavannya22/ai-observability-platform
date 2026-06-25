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
    return {"status": "ok"}


def _build_search_query(question: str, incident: dict) -> str:
    parts = [question]
    if incident.get("root_cause"):
        parts.append(incident["root_cause"])
    parts.extend(incident.get("affected_services") or [])
    return " ".join(parts)
