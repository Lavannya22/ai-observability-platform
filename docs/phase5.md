# Phase 5 — RAG-Powered Incident Investigation Assistant

## What Changed in Phase 5?

Phases 1–4 built a system that could detect incidents, identify root causes, explain how failures propagated, and rank candidates with calibrated confidence. All of that information exists in the system — but it's locked inside a database. An on-call engineer still has to navigate to the right tab, interpret the propagation path, and manually connect the dots between a current incident and a similar one from three weeks ago.

Phase 5 asks a different question:

> **Can an engineer just ask what happened — and get a grounded, evidence-backed answer in plain language?**

The answer is the AI Assistant: a RAG (Retrieval-Augmented Generation) pipeline that lets engineers investigate incidents by asking natural-language questions and receiving answers grounded in the incident's own evidence, the dependency graph, and similar historical incidents retrieved from a vector store.

---

## The Problem with Static Analysis

Phase 4 made the RCA decision explainable. It produces evidence bullets like:

```
database emitted the first ERROR log at 10:23:41
4 downstream services impacted: metadata, etl, analytics, reporting
All affected services are reachable from database in the dependency graph
```

This is accurate — but it's generic. Every database incident produces roughly the same five bullets. And it doesn't answer the questions engineers actually ask during an incident:

- *Why did reporting fail specifically?*
- *Is this the same pattern we saw last month?*
- *What do I do first?*

Answering those questions requires connecting the current incident to historical context and rephrasing the structured data as a direct response to the question being asked. That's what RAG is for.

---

## What Was Built

### 1. Incident Knowledge Store

When an incident resolves, it is immediately converted into a searchable knowledge document and indexed in OpenSearch. The document schema captures everything Phase 4 produced:

```json
{
  "incident_id": "INC-A1B2C3",
  "root_cause": "database",
  "affected_services": ["metadata", "etl", "analytics", "reporting"],
  "propagation_path": ["database", "metadata", "etl", "analytics", "reporting"],
  "confidence_ranking": {"database": 0.40, "metadata": 0.30, "etl": 0.20},
  "evidence": ["database emitted the first ERROR log", "4 downstream services impacted"],
  "summary": "Database failure caused cascading errors across metadata, etl, analytics, reporting."
}
```

The `summary` field is a template-generated human-readable sentence built from the root cause, affected services, propagation path, and first evidence bullet. This is what gets embedded for vector search.

The real-time trigger is wired directly into the Kafka consumer. The moment an incident transitions from `ACTIVE` to `RESOLVED`, `build_and_index()` fires automatically. No batch jobs. No manual steps.

```
Incident resolved
       ↓
build_document()   — convert to knowledge doc
       ↓
embed(summary)     — 384-dim Sentence Transformer vector
       ↓
OpenSearch index   — immediately searchable
```

A `backfill_from_db()` function is also provided to index any existing resolved incidents that predate Phase 5.

### 2. Vector Search

At investigation time, the engineer's question is embedded using the same Sentence Transformer model from Phase 4 (`all-MiniLM-L6-v2`). OpenSearch performs approximate nearest-neighbour search using HNSW with cosine similarity to return the top-5 most semantically similar historical incidents.

This means a question like *"Why did reporting fail?"* retrieves past incidents involving reporting failures — even if the exact wording doesn't match any stored document. Semantic similarity, not keyword overlap.

Reusing the Phase 4 embedding model is a deliberate choice: it keeps the vector space consistent between what was indexed and what is being queried. If different models were used, similar incidents might not surface because their vectors would be in different spaces.

### 3. Grounding Validator — Deterministic Hallucination Detection

The grounding validator is the most important component in Phase 5. Its job is to catch hallucinations before they reach the engineer.

A hallucination in this context means the LLM asserted something that isn't in the incident data — for example:

```
❌  "Database CPU reached 99%."
     → No CPU metrics exist in this system. Hallucination.

✓   "Database emitted 43 ERROR logs."
     → Exists in evidence. Grounded.
```

The validator is entirely deterministic — no second LLM call, no probabilistic scoring. It works in two passes:

**Pass 1 — Blocklist check.** Every sentence is scanned for patterns that indicate metrics or concepts that don't exist in this system: CPU usage, memory pressure, disk I/O, network latency, P99, percentiles, traffic spikes, deployments, DNS, load balancers. Any sentence matching these patterns is flagged as unsupported.

**Pass 2 — Identifier check.** Service names and incident IDs mentioned in the answer are verified against the known fact set built from the current incident and retrieved history. An answer that invents a service name or cites a non-existent incident ID is flagged.

Common English connector words ("which", "however", "therefore") are explicitly excluded from the check — the validator targets domain-specific identifiers, not grammar.

### 4. Question-Aware Answer Generation

The answer generator handles two modes:

**LLM mode** — when `ANTHROPIC_API_KEY` is set, the pipeline sends a structured prompt to `claude-haiku-4-5-20251001`. The prompt includes the current incident, its confidence ranking and evidence, and the top-5 retrieved similar incidents. The model is instructed to answer only from the provided data.

**Rule-based fallback** — when no API key is set, the system generates a grounded answer from the incident data directly, tailored to the type of question:

| Question type | Example | Answer focus |
|---|---|---|
| Why / root cause | "Why did this occur?" | Root cause + first 2 evidence bullets + cascade |
| Propagation | "What is the propagation path?" | Full dependency chain with explanation |
| Historical | "Have we seen this before?" | Retrieved similar incidents with incident IDs |
| Action | "What should I do?" | 3-step resolution: investigate root, verify chain, restore |
| Confidence | "How confident are you?" | Full probability-normalised ranking with explanation |
| Default | Any other question | Full incident summary |

This means the assistant gives a different, relevant answer for each question type even without an LLM — the right information surfaces without requiring the engineer to read the entire incident record.

Every generated answer — whether from the LLM or the rule-based fallback — is passed through the grounding validator before being returned.

### 5. RAG API

A FastAPI service wraps the full pipeline for programmatic access:

```
POST /ask           — answer a question about a specific incident
POST /ask/freeform  — answer a free-form question using vector search only
GET  /health        — liveness check
```

### 6. Dashboard Tab 4 — AI Assistant

The Streamlit dashboard gains a fourth tab with:

- **Incident selector** — any incident in the database (active or resolved)
- **Question input** — free text, with suggested questions pre-populated
- **Answer** — grounded response from the RAG pipeline
- **Grounding badge** — green (fully grounded) or amber (hallucination rate %)
- **Source incidents** — which historical incidents were cited
- **Similar incidents expander** — ranked table of retrieved incidents with similarity scores
- **Hallucination detail** — expandable list of unsupported claims (when present)

The tab degrades gracefully: if OpenSearch is unavailable, vector search is skipped and answers use only the current incident data. If no API key is set, the question-aware rule-based fallback runs instead of the LLM.

---

## Results

| Metric | Target | Result |
|---|---|---|
| Hallucination Rate | ≤ 5% | **0.0000%** ✅ |
| Fully Grounded Queries | 10/10 | **10/10** ✅ |
| Real-time indexing on resolve | Yes | **Yes** ✅ |
| Question-aware answers | Yes | **Yes — 6 question types** ✅ |
| Retrieval (Precision@5, MRR) | ≥ 90% / ≥ 0.80 | Requires indexed incidents |

The grounding evaluation runs on 10 synthetic incidents covering all root cause types. Each incident is fed through the full answer generator and grounding validator. Zero hallucinations detected across all 10 queries.

---

## Engineering Decisions Worth Noting

**Why deterministic grounding instead of a second LLM call?**
LLM-as-judge approaches introduce their own hallucination surface and add cost and latency on every request. A blocklist of metrics that provably don't exist in this system (CPU, memory, disk I/O) catches the most common and dangerous hallucinations without any of those downsides. The validator is fast, free, and always gives the same result for the same input — it's testable.

**Why a blocklist rather than an allowlist?**
An allowlist approach requires enumerating every valid English word and phrase — an impossible target. The set of things that *don't exist* in this system is much smaller and better defined: there are no CPU metrics, no network latency measurements, no deployment events. Blocking the specific things that are wrong is more robust than trying to allow everything that is right.

**Why reuse the Phase 4 Sentence Transformer for both indexing and querying?**
Vector search only works when the indexed vectors and the query vectors live in the same embedding space. Using the same model for both guarantees this. It also means no additional model download or memory footprint — the Sentence Transformer was already a dependency.

**Why question-aware answers in the fallback rather than one generic template?**
A generic template always answers "what happened" regardless of whether the engineer asked "what should I do?" or "have we seen this before?". The wrong information delivered confidently is worse than no answer. Tailoring by question type ensures the engineer gets the relevant information immediately rather than having to scan a paragraph to find it.

**Why wrap the OpenSearch trigger in `try/except` in the consumer?**
The consumer is the critical real-time path. If OpenSearch is down for maintenance or misconfigured, the consumer must continue processing logs and running RCA — it cannot crash because of an indexing failure. The try/except makes Phase 5 entirely optional infrastructure: the platform works with or without OpenSearch.

**Why `backfill_from_db()` as a separate function?**
The real-time trigger only fires on future resolutions. Incidents that resolved before Phase 5 was deployed are not automatically indexed. The backfill function checks each resolved incident's ID against the OpenSearch index and skips anything already present — it's idempotent and can be run repeatedly without creating duplicates.

---

## The Honest Summary

| Question | Answer |
|---|---|
| Does the RAG pipeline produce grounded answers? | **Yes — 0% hallucination rate across all evaluation queries** |
| Does it answer different questions differently? | **Yes — 6 question types produce distinct, relevant answers** |
| Does it use real historical incidents? | **Yes — when incidents are indexed in OpenSearch** |
| Does it require an LLM API key to function? | **No — rule-based fallback works without one** |
| Can the system crash if OpenSearch goes down? | **No — OpenSearch failure is caught and logged, not propagated** |

---

## Skills Demonstrated

### Retrieval-Augmented Generation
- Built a complete **RAG pipeline** from scratch: knowledge store → embedding → vector retrieval → prompt construction → answer generation → grounding validation
- Designed **retrieval ground truth** with a subset/superset relevance rule (not exact set matching) to reflect real-world incident variability
- Computed **Precision@5, Recall@5, MRR** as retrieval quality metrics

### Hallucination Detection
- Built a **deterministic grounding validator** using a domain-specific blocklist — no second LLM call, no probabilistic thresholds
- Distinguished between unknown vocabulary (not always a hallucination) and domain-invalid claims (always a hallucination)
- Achieved **0% hallucination rate** on the evaluation set

### LLM Integration
- Integrated **Anthropic Claude Haiku** via the `anthropic` Python SDK with graceful API key handling
- Designed prompts that constrain the LLM to the provided context and prevent metric hallucinations
- Implemented a **question-aware rule-based fallback** that activates when no API key is present

### Knowledge Engineering
- Designed an **OpenSearch index schema** with `knn_vector` (dim=384, HNSW, cosine similarity) for semantic retrieval
- Built a **real-time knowledge indexing pipeline** triggered by incident lifecycle transitions
- Managed **idempotent backfill** to handle incidents that predate the knowledge store

### System Design
- Made Phase 5 **entirely optional infrastructure** — the consumer continues working if OpenSearch is unavailable
- **Reused the Phase 4 Sentence Transformer** for both indexing and querying to guarantee vector space consistency
- Dashboard degrades gracefully across three states: LLM + OpenSearch, OpenSearch only, fallback only

---

## Technology Stack (Phase 5 Additions)

| Tool | Purpose |
|---|---|
| OpenSearch 2.11 | Vector store for incident knowledge documents |
| `opensearch-py` | Python client for indexing and knn search |
| `anthropic` SDK | Claude Haiku API for LLM answer generation |
| FastAPI + Uvicorn | Optional HTTP API wrapping the RAG pipeline |
| Sentence Transformer (reused) | Embeds both summaries (indexing) and questions (querying) |
| Docker Compose | Orchestrates OpenSearch + Kafka + Zookeeper |

---

## How to Run

```bash
# Start OpenSearch + Kafka (PostgreSQL runs locally)
docker-compose up -d

# Create the OpenSearch index (once)
python -m search.create_index

# Generate and resolve incidents (they auto-index on resolution)
python ingestion/producer.py --scenario S001   # Terminal 1
python ingestion/consumer.py                   # Terminal 2

# Backfill any existing resolved incidents
python -m knowledge.knowledge_builder

# (Optional) Enable Claude Haiku
export ANTHROPIC_API_KEY=your_key_here

# Run the dashboard — Tab 4: AI Assistant
streamlit run dashboard/app.py

# Run evaluations
python -m evaluation.evaluate_grounding    # 0% hallucination target
python -m evaluation.evaluate_retrieval    # Precision@5, Recall@5, MRR
```

---

## Phase 1 → Phase 5 Progression

| | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|---|---|---|---|---|---|
| Incident detection | Rule-based | Rule-based | Rule-based | Rule-based | Rule-based |
| Log clustering | TF-IDF greedy | TF-IDF greedy | K-Means | HDBSCAN | HDBSCAN |
| RCA | Graph scoring | Graph scoring | Graph scoring | Probability-ranked | Probability-ranked |
| Explainability | None | None | None | Evidence bullets + propagation | Evidence bullets + NL answers |
| Historical context | None | None | None | None | Vector search over resolved incidents |
| Engineer interface | Code / scripts | Streamlit (3 tabs) | Streamlit (3 tabs) | Streamlit (3 tabs) | Streamlit (4 tabs) + RAG API |
| NL question answering | None | None | None | None | Yes — 6 question types |
| Hallucination guard | N/A | N/A | N/A | N/A | Deterministic validator, 0% rate |
| Knowledge persistence | PostgreSQL | PostgreSQL | PostgreSQL | PostgreSQL + Phase 4 JSON | PostgreSQL + OpenSearch |
