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

---

## Project Structure

ai-observability-platform/
├── main.py

├── scenarios/
│   ├── scenarios.json
│   └── ground_truth.json

├── generator/
│   └── log_generator.py

├── rca/
│   ├── dependency_graph.py
│   ├── detector.py
│   ├── clustering.py
│   ├── engine.py
│   └── explainer.py

├── evaluation/
│   ├── evaluate.py
│   └── metrics.py

├── dashboard/
│   └── app.py

├── data/
│   ├── raw_logs/
│   ├── processed_logs/
│   └── incidents/

├── configs/
│   └── settings.yaml

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

database → metadata → etl → analytics → reporting

Edge means: "depends on"

---

## Log Generator

Deterministic behavior:
- same scenario → same logs
- inject root cause first
- propagate downstream failures

---

## Incident Detection

Simple rule-based:
- spike in ERROR logs
- per-service threshold breach

---

## Clustering

Use:
- TF-IDF
- cosine similarity

(No embeddings in Phase 1)

---

## Root Cause Analysis (FINAL)

Rule:
Root cause = node with MAX upstream influence

```python
import networkx as nx

def find_root_cause(incident_services, graph):
    reversed_graph = graph.reverse()
    scores = {}

    for service in incident_services:
        upstream = nx.descendants(reversed_graph, service)

        for node in upstream:
            if node in incident_services:
                scores[node] = scores.get(node, 0) + 1

    if not scores:
        return incident_services[0]

    return max(scores, key=scores.get)
```

---

## Explanation Layer

Input:
- root cause
- affected services
- logs summary

Output:
Human-readable incident explanation

---

## Dashboard

Streamlit app showing:
- logs
- incidents
- root cause
- explanation

Run:
streamlit run dashboard/app.py

---

## Build Order

1. scenarios.json
2. ground_truth.json
3. configs/settings.yaml
4. dependency_graph.py
5. log_generator.py
6. detector.py
7. clustering.py
8. engine.py
9. explainer.py
10. evaluation/metrics.py
11. evaluation/evaluate.py
12. main.py
13. dashboard

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
