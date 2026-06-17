# AI Observability Platform

An AI-powered log intelligence platform that monitors a simulated enterprise data pipeline — automatically detecting incidents, identifying root causes, and generating natural-language explanations.

---

## What It Does

Enterprise data pipelines generate thousands of logs per minute across interdependent services. When a single service fails, errors cascade downstream, creating noise that's hard to triage manually. This platform automates the full investigation pipeline:

```
Scenario → Log Generation → Incident Detection → Clustering → RCA → Explanation → Dashboard
```

**Phase 1 results across all scenarios:**
- Top-1 RCA accuracy: 100% (4/4 scenarios)
- Alert noise reduction: ~74% (75 error logs → ~15 clusters)
- Incident detection: 100% hit rate

---

## Architecture

### Monitored System

```
database → metadata → etl → analytics → reporting
```

Edge direction: `A → B` means B depends on A. If A fails, B fails too.

### Pipeline Components

| Component | File | Description |
|---|---|---|
| Log Generator | `generator/log_generator.py` | Deterministic log injection — same scenario always produces the same logs |
| Incident Detector | `rca/detector.py` | Rule-based: flags services with ERROR count above threshold |
| Clustering | `rca/clustering.py` | TF-IDF + cosine similarity groups related error logs into clusters |
| Dependency Graph | `rca/dependency_graph.py` | NetworkX graph models service relationships |
| RCA Engine | `rca/engine.py` | Scores each service by how many downstream incident services it caused |
| Explainer | `rca/explainer.py` | Template-based human-readable incident summary + remediation steps |
| Dashboard | `dashboard/app.py` | Streamlit UI showing logs, clusters, RCA, and explanation |
| Evaluation | `evaluation/evaluate.py` | Scores predictions against ground truth |

---

## Scenarios

| ID | Name | Root Cause | Affected Services |
|---|---|---|---|
| S001 | Database Overload | `database` | metadata, etl, analytics, reporting |
| S002 | ETL Job Failure | `etl` | analytics, reporting |
| S003 | Data Quality Issue | `metadata` | etl, analytics, reporting |
| S004 | Analytics Service Crash | `analytics` | reporting |

---

## Quickstart

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the pipeline (CLI)

```bash
python main.py --scenario S001
```

Runs the full pipeline for a scenario and prints detection results, RCA candidates, explanation, and evaluation metrics.

### Launch the dashboard

```bash
streamlit run dashboard/app.py
```

Opens at `http://localhost:8501`. Select a scenario from the sidebar and click **Run Pipeline**.

---

## Project Structure

```
ai-observability-platform/
├── main.py                    # CLI entry point
├── requirements.txt
│
├── scenarios/
│   ├── scenarios.json         # Failure scenario definitions
│   └── ground_truth.json      # Expected RCA outcomes for evaluation
│
├── configs/
│   └── settings.yaml          # Thresholds, paths, pipeline config
│
├── generator/
│   └── log_generator.py       # Deterministic log generation
│
├── rca/
│   ├── dependency_graph.py    # NetworkX service dependency graph
│   ├── detector.py            # Rule-based incident detection
│   ├── clustering.py          # TF-IDF + cosine similarity clustering
│   ├── engine.py              # Graph-based root cause scoring
│   └── explainer.py          # Template-based explanation generator
│
├── evaluation/
│   ├── metrics.py             # RCA accuracy, noise reduction metrics
│   └── evaluate.py            # Scores run against ground truth
│
├── dashboard/
│   └── app.py                 # Streamlit dashboard
│
└── data/
    ├── raw_logs/              # Generated log files (per scenario)
    ├── processed_logs/        # Reserved for future phases
    └── incidents/             # Saved incident reports (JSON)
```

---

## Phase Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 1 — MVP | Done | Deterministic pipeline: log gen → detection → clustering → RCA → explanation → dashboard |
| Phase 2 | Planned | Semantic embeddings (Sentence Transformers), HDBSCAN clustering, OpenSearch |
| Phase 3 | Planned | Kafka streaming, real-time ingestion at 10K+ logs/min |
| Phase 4 | Planned | RAG-powered LLM investigation assistant |
