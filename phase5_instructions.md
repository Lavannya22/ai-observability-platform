# Phase 5: RAG-Powered Incident Investigation Assistant

---

## Goal

Transform the platform from:

> "The system knows the answer"

to

> "The engineer can ask questions and receive grounded explanations."

Phase 5 introduces:

* OpenSearch
* Incident Knowledge Store
* Vector Search
* Retrieval-Augmented Generation (RAG)
* Grounded Natural Language Explanations
* Hallucination Validation

This phase does **not** introduce:

* Agents
* LangGraph
* Multi-step reasoning workflows
* Autonomous actions

The objective is a simple, reliable RAG assistant.

---

## Phase 5 Architecture

```text
User Question
       |
       v
RAG API
       |
       v
OpenSearch Retrieval
       |
       v
Relevant Historical Incidents
       |
       v
Current Incident Data
       |
       v
Prompt Builder
       |
       v
LLM
       |
       v
Grounding Validator
       |
       v
Answer
```

---

## Step 0 — Add OpenSearch

### Create Docker Container

```yaml
opensearch:
  image: opensearchproject/opensearch:latest
```

Run alongside:

```text
Kafka
PostgreSQL
FastAPI
OpenSearch
```

---

## Step 1 — Create Incident Knowledge Store

Create:

```text
knowledge/
├── knowledge_builder.py
├── incident_document.py
└── indexer.py
```

Purpose: convert resolved incidents into searchable documents.

### Knowledge Document Schema

```json
{
  "incident_id": "INC-001",

  "root_cause": "database",

  "affected_services": [
    "metadata",
    "etl",
    "analytics",
    "reporting"
  ],

  "propagation_path": [
    "database",
    "metadata",
    "etl",
    "analytics",
    "reporting"
  ],

  "confidence_ranking": {
    "database": 0.91,
    "metadata": 0.05,
    "etl": 0.03,
    "analytics": 0.01
  },

  "evidence": [
    "Database emitted 43 ERROR logs",
    "4 downstream services affected",
    "Propagation matched dependency graph"
  ],

  "summary": "Database overload caused cascading failures across downstream services."
}
```

---

## Step 2 — Real-Time Indexing Trigger

Knowledge documents must be created automatically.

Trigger:

```text
ACTIVE
   |
   v
RESOLVED
```

inside:

```text
consumer.py
```

When incident status changes:

```python
ACTIVE -> RESOLVED
```

execute:

```python
knowledge_builder.build_document()
```

then:

```python
indexer.index_document()
```

This ensures:

```text
Incident resolved
       |
       v
Immediately searchable
```

No batch jobs. No manual indexing.

---

## Step 3 — OpenSearch Index Schema

Create:

```text
search/
├── opensearch_client.py
├── create_index.py
└── vector_search.py
```

Index:

```json
{
  "incident_id": "keyword",
  "root_cause": "keyword",
  "affected_services": "keyword",
  "summary": "text",
  "evidence": "text",
  "embedding": "dense_vector"
}
```

---

## Step 4 — Define Retrieval Ground Truth

Create:

```text
evaluation/retrieval_queries.json
```

Example:

```json
{
  "query": "database timeout incident",
  "expected_root_cause": "database",
  "expected_services": [
    "metadata",
    "etl"
  ]
}
```

### Relevance Definition

A retrieved incident is considered relevant if:

**Rule 1 — Same root cause.**

```text
database == database
```

**AND**

**Rule 2 — Affected services overlap significantly.**

Allow:

```text
Query:     [metadata, etl]
Candidate: [metadata, etl, analytics]
```

→ MATCH

Allow (reverse direction):

```text
Query:     [metadata, etl, analytics]
Candidate: [metadata, etl]
```

→ MATCH

Reject:

```text
Query:     [metadata, etl]
Candidate: [reporting]
```

→ NOT RELEVANT

### Interpretation

Affected-service matching is **subset OR superset tolerant**, NOT exact set
equality. This allows incidents with different cascade depth to still be
considered historically relevant — e.g. a fully-cascaded database failure
and a database failure caught earlier in its propagation should still match
each other, since they share the same root cause and underlying pattern.

---

## Step 5 — Build Vector Retrieval

Create:

```text
search/vector_search.py
```

Reuse the Sentence Transformer from Phase 4.

```python
embedding = model.encode(summary)
```

Store in OpenSearch. Retrieve using vector similarity:

```python
top_k = 5
```

---

## Step 6 — Build Grounding Validator

Create:

```text
rag/grounding_validator.py
```

Purpose: detect hallucinations deterministically — not via a second LLM
call, not via manual review.

### Controlled Vocabulary

Services:

```text
database
metadata
etl
analytics
reporting
```

Root causes: same five services.

Allowed evidence types:

```text
error counts
affected services
propagation paths
confidence scores
```

### Validation Rule

Every statement in the answer must exist in:

```text
Current Incident
OR
Retrieved Incidents
OR
Evidence
```

### Hallucination Examples

**Valid:**

```text
Database generated 43 ERROR logs.
```

Exists in evidence → valid.

**Invalid:**

```text
Database CPU reached 99%.
```

No such metric exists in any source document → hallucination.

---

## Step 7 — Build RAG API

Create:

```text
rag/
├── prompt_builder.py
├── answer_generator.py
└── rag_api.py
```

### Example Question

```text
Why did reporting fail?
```

Retrieve:

```text
Current Incident
Historical Incidents
Evidence
```

Build prompt:

```text
Question:
Why did reporting fail?

Current Incident:
...

Historical Incidents:
...

Evidence:
...
```

Send to LLM. Return answer.

---

## Step 8 — Explanation Quality Rubric

Score 1 point each:

1. **Root Cause Identified** — e.g. "Database overload caused the failure."
2. **Evidence Referenced** — e.g. "43 ERROR logs observed."
3. **Failure Propagation Explained** — e.g. "Database → Metadata → ETL → Reporting."
4. **Historical Context Used** — e.g. "This resembles Incident INC-014."
5. **Actionable Recommendation** — e.g. "Investigate database resource utilization."

Maximum score: `5/5`. Target: average ≥ `4.0`.

---

## Step 9 — Retrieval Evaluation

Create:

```text
evaluation/evaluate_retrieval.py
```

Metrics:

| Metric        | Target |
| ------------- | ------ |
| Precision@5   | ≥ 90%  |
| Recall@5      | ≥ 80%  |
| MRR           | ≥ 0.80 |

---

## Step 10 — Hallucination Evaluation

Create:

```text
evaluation/evaluate_grounding.py
```

For every generated answer, run the grounding validator and compute:

```text
Hallucination Rate = Unsupported Claims / Total Claims
```

Target: `≤ 5%`

---

## Step 11 — Dashboard Integration

Add new tab: **AI Assistant**

Example:

```text
Q: Why did reporting fail?

A: Reporting failed because the database experienced overload,
   which propagated through metadata and ETL services.
   Similar behavior was observed in Incident INC-014.
   Evidence included 43 database ERROR logs and four affected
   downstream services.
   Recommended action: investigate database resource usage.
```

---

## Build Order

1. Step 0 — OpenSearch Docker container added to `docker-compose.yml`
2. `search/opensearch_client.py`
3. `search/create_index.py` — index schema from Step 3
4. `knowledge/incident_document.py` — schema definition
5. `knowledge/knowledge_builder.py`
6. `knowledge/indexer.py`
7. `ingestion/consumer.py` — wire in the `ACTIVE → RESOLVED` real-time trigger
8. `search/vector_search.py` — embed + retrieve top-k
9. `evaluation/retrieval_queries.json` — labeled ground truth using the subset/superset relevance rule
10. `rag/grounding_validator.py` — controlled vocabulary + validation rule
11. `rag/prompt_builder.py`
12. `rag/answer_generator.py`
13. `rag/rag_api.py`
14. `evaluation/evaluate_retrieval.py` — Precision@5 / Recall@5 / MRR
15. `evaluation/evaluate_grounding.py` — hallucination rate
16. Dashboard — AI Assistant tab

> OpenSearch and the index must exist before the knowledge builder or
> indexer can run. The real-time trigger in `consumer.py` should be wired
> and tested with a single resolved incident before building the retrieval
> and generation layers on top of it.

---

## Phase 5 Success Criteria

### Retrieval

* Precision@5 ≥ 90%
* Recall@5 ≥ 80%
* MRR ≥ 0.80

### Explanation Quality

* Average Rubric Score ≥ 4.0 / 5

### Grounding

* Hallucination Rate ≤ 5%

### Real-Time Knowledge Store

* Every resolved incident automatically indexed

### RAG

* Natural language questions answered using current incident, historical
  incidents, and RCA evidence

---

## Deliverables

```text
knowledge/
├── knowledge_builder.py
├── incident_document.py
└── indexer.py

search/
├── opensearch_client.py
├── create_index.py
└── vector_search.py

rag/
├── prompt_builder.py
├── answer_generator.py
├── grounding_validator.py
└── rag_api.py

evaluation/
├── retrieval_queries.json
├── evaluate_retrieval.py
└── evaluate_grounding.py
```

---

## What NOT to Build in Phase 5

Do NOT add:

* Agents
* LangGraph
* Multi-step reasoning workflows
* Autonomous actions
* Fine-tuning
* Kubernetes
* AWS deployment

Phase 5 is strictly: **Retrieve → Generate → Validate → Answer**, with
measurable retrieval quality, grounding quality, and explanation quality.

---

## Mental Model

**Phase 1 proved:**

> Can we detect incidents?

**Phase 2 proved:**

> Can we process incidents in real time?

**Phase 3 proved:**

> Can we objectively evaluate ML methods?

**Phase 4 proved:**

> Can we explain why a root cause was selected?

**Phase 5 proves:**

> Can engineers investigate incidents using natural language and receive
> accurate, evidence-backed answers grounded in historical incidents and
> RCA results?
