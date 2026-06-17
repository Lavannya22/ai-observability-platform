# Phase 1 — MVP (Final Execution Instructions)

## Goal
Build a fully deterministic incident intelligence pipeline:

Scenario → Logs → Detection → Clustering → RCA → Explanation → Dashboard

---

## Success Criteria

Run:
```bash
python main.py --scenario S001
```

Must produce:
- deterministic logs
- incident detection
- clustering
- correct root cause
- explanation
- dashboard output

**Achieved results (all 4 scenarios):**

| Scenario | Top-1 RCA | Detection | Noise Reduction |
|---|---|---|---|
| S001 — Database Overload | Correct | Hit | 74.7% |
| S002 — ETL Job Failure | Correct | Hit | 73.3% |
| S003 — Data Quality Issue | Correct | Hit | 75.0% |
| S004 — Analytics Service Crash | Correct | Hit | 73.3% |

---

## Project Structure

```
ai-observability-platform/
├── main.py
├── requirements.txt
│
├── scenarios/
│   ├── scenarios.json
│   └── ground_truth.json
│
├── generator/
│   ├── __init__.py
│   └── log_generator.py
│
├── rca/
│   ├── __init__.py
│   ├── dependency_graph.py
│   ├── detector.py
│   ├── clustering.py
│   ├── engine.py
│   └── explainer.py
│
├── evaluation/
│   ├── __init__.py
│   ├── evaluate.py
│   └── metrics.py
│
├── dashboard/
│   ├── __init__.py
│   └── app.py
│
├── data/
│   ├── raw_logs/
│   ├── processed_logs/
│   └── incidents/
│
├── configs/
│   └── settings.yaml
│
└── docs/
    └── phase1.md
```

> Note: `__init__.py` files are required in each package directory so Python can resolve imports correctly.

---

## Scenarios (S001–S004)

### File: scenarios/scenarios.json

```json
[
  {
    "scenario_id": "S001",
    "name": "Database Overload",
    "failure_type": "resource_exhaustion",
    "root_cause_service": "database",
    "affected_services": ["metadata", "etl", "analytics", "reporting"],
    "log_signatures": [
      "DB connection timeout",
      "query latency high",
      "connection pool exhausted"
    ]
  },
  {
    "scenario_id": "S002",
    "name": "ETL Job Failure",
    "failure_type": "job_failure",
    "root_cause_service": "etl",
    "affected_services": ["analytics", "reporting"],
    "log_signatures": [
      "ETL job crashed",
      "data transformation error",
      "null pointer in pipeline"
    ]
  },
  {
    "scenario_id": "S003",
    "name": "Data Quality Issue",
    "failure_type": "data_corruption",
    "root_cause_service": "metadata",
    "affected_services": ["etl", "analytics", "reporting"],
    "log_signatures": [
      "schema mismatch detected",
      "invalid data format",
      "missing required fields"
    ]
  },
  {
    "scenario_id": "S004",
    "name": "Analytics Service Crash",
    "failure_type": "service_crash",
    "root_cause_service": "analytics",
    "affected_services": ["reporting"],
    "log_signatures": [
      "out of memory error",
      "segmentation fault",
      "analytics service terminated unexpectedly"
    ]
  }
]
```

---

## Ground Truth

### File: scenarios/ground_truth.json

```json
[
  {
    "scenario_id": "S001",
    "root_cause_service": "database",
    "affected_services": ["metadata", "etl", "analytics", "reporting"],
    "expected_rca_rank": 1
  },
  {
    "scenario_id": "S002",
    "root_cause_service": "etl",
    "affected_services": ["analytics", "reporting"],
    "expected_rca_rank": 1
  },
  {
    "scenario_id": "S003",
    "root_cause_service": "metadata",
    "affected_services": ["etl", "analytics", "reporting"],
    "expected_rca_rank": 1
  },
  {
    "scenario_id": "S004",
    "root_cause_service": "analytics",
    "affected_services": ["reporting"],
    "expected_rca_rank": 1
  }
]
```

---

## Dependency Graph

```
database → metadata → etl → analytics → reporting
```

Edge means: "depends on"
So `reporting → analytics` means reporting depends on analytics.

In NetworkX, edges are stored as `dependent → dependency`. Failures propagate in the reverse direction: if `database` fails, `metadata` fails, then `etl`, then `analytics`, then `reporting`.

---

## Log Generator

Deterministic behavior:
- same scenario → same logs (controlled by `seed: 42` in settings.yaml)
- inject root cause errors first
- propagate downstream failures in dependency order
- normal INFO logs generated for all services first as background noise

Log entry structure:
```json
{
  "timestamp": "2025-01-15T09:00:00",
  "service": "database",
  "level": "ERROR",
  "message": "Connection pool exhausted: 0 connections available",
  "scenario_id": "S001"
}
```

---

## Incident Detection

Simple rule-based:
- count ERROR logs per service across all logs
- flag any service exceeding `error_threshold` (default: 5)

> **Important:** Do NOT use a sliding tail window. Errors are injected in root-cause-first order,
> so a tail window will miss the originating service — it fires first and exits the window before
> downstream errors appear. Count across all logs instead.

---

## Clustering

Use:
- TF-IDF (max 500 features)
- cosine similarity threshold (default: 0.3)

Algorithm: **greedy single-pass**
1. Vectorise all ERROR log messages with TF-IDF
2. For each log, compare cosine similarity against all existing cluster centroids
3. If best match >= threshold → assign to that cluster, update centroid
4. Otherwise → start a new cluster

(No embeddings or HDBSCAN in Phase 1)

---

## Root Cause Analysis (CORRECTED)

Rule: Root cause = service with the most downstream incident services it explains

```python
import networkx as nx

def find_root_cause(incident_services, graph):
    # reverse: edges now point in failure propagation direction
    propagation_graph = graph.reverse()
    scores = {}

    for service in incident_services:
        downstream = nx.descendants(propagation_graph, service)
        scores[service] = sum(1 for node in downstream if node in incident_services)

    if not scores:
        return [{"service": incident_services[0], "score": 0, "confidence": 1.0}]

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top3 = ranked[:3]
    max_score = top3[0][1] if top3[0][1] > 0 else 1

    return [
        {"service": svc, "score": score, "confidence": round(score / max_score, 3)}
        for svc, score in top3
    ]
```

> **Bug in original pseudocode:** The original version incremented scores for downstream *victim*
> nodes rather than the *origin* node. This caused the last service in the chain (`reporting`) to
> rank #1 instead of the true root cause. The fix above scores each candidate by how many
> downstream failures it explains.

**S001 score trace:**
```
database  → 4 downstream victims → confidence 1.00  ← correctly identified
metadata  → 3 downstream victims → confidence 0.75
etl       → 2 downstream victims → confidence 0.50
analytics → 1 downstream victim  → confidence 0.25
reporting → 0 downstream victims → confidence 0.00
```

---

## Explanation Layer

Template-based (no LLM in Phase 1).

Input:
- root cause service
- affected services
- sample error logs (up to 5)
- failure type

Output sections:
- Incident summary (root cause, failure type, affected services)
- What happened (narrative sentence)
- Evidence (sample log messages)
- Recommended remediation (3 steps, service-specific)

---

## Dashboard

Streamlit app. Uses session state — results only appear after the button is clicked (not on page load).

```bash
streamlit run dashboard/app.py
```

Shows:
- Scenario info in sidebar before running
- Spinner + success message on pipeline execution
- Summary metric cards (total logs, errors, clusters, affected services)
- Top-3 RCA candidates with confidence
- Ground truth match indicator
- Incident explanation
- Cluster table with noise reduction summary
- Log stream with level filter

---

## Build Order

1. `scenarios/scenarios.json`
2. `scenarios/ground_truth.json`
3. `configs/settings.yaml`
4. `rca/dependency_graph.py`
5. `generator/log_generator.py`
6. `rca/detector.py`
7. `rca/clustering.py`
8. `rca/engine.py`
9. `rca/explainer.py`
10. `evaluation/metrics.py`
11. `evaluation/evaluate.py`
12. `main.py`
13. `dashboard/app.py`
14. `requirements.txt`
15. `__init__.py` in each package directory

---

## Dependencies

```
networkx>=3.0
scikit-learn>=1.3
pyyaml>=6.0
streamlit>=1.35
pandas>=2.0
```

Install:
```bash
pip install -r requirements.txt
```

---

## Constraints

DO NOT use:
- Kafka
- OpenSearch
- HDBSCAN
- Transformers
- AWS
- distributed systems

---

## Mental Model

Phase 1 is NOT production.

It is:
"prove deterministic failure → detection → RCA → explanation"

Complexity is added in Phase 2 and beyond. Every component here has a direct upgrade path:
- TF-IDF → Sentence Transformers
- greedy clustering → HDBSCAN
- template explainer → RAG + LLM
- batch logs → Kafka streaming
