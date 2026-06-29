# AI Observability Platform

An end-to-end AI-powered log intelligence platform that ingests streaming logs from a simulated enterprise data pipeline, automatically detects incidents, identifies root causes with explainable confidence scores, stores operational knowledge, and answers engineer questions through a grounded RAG assistant.

---

## Architecture

```
Kafka Producer
      |
      v
Kafka Topic (logs)
      |
      v
Kafka Consumer
      |
      v
Incident Detection  ──→  PostgreSQL (incidents, logs)
      |
      v
HDBSCAN Clustering (Sentence Transformer embeddings)
      |
      v
RCA Engine (graph-based, probability-normalised confidence)
      |
      v
Evidence Generation + Propagation Analysis
      |
      v
Incident Resolution
      |
      v
Knowledge Document  ──→  OpenSearch (vector index)
      |
      v
RAG Assistant (Claude Haiku / rule-based fallback)
      |
      v
Streamlit Dashboard (4 tabs)
```

### Monitored System

```
database → metadata → etl → analytics → reporting
```

Edge direction: `A → B` means B depends on A. A failure at `database` cascades through all downstream services.

---

## Phases

| Phase | What Was Built | Key Result |
|---|---|---|
| **Phase 1** | Log generation, incident detection, TF-IDF clustering, graph RCA, Streamlit dashboard | RCA Top-1: 100% (4 scenarios) |
| **Phase 2** | Kafka streaming pipeline, PostgreSQL persistence, real-time incident lifecycle | Live incidents at streaming scale |
| **Phase 3** | Isolation Forest anomaly detection, K-Means clustering, 20-scenario evaluation framework | Honest finding: K-Means underperformed greedy baseline |
| **Phase 4** | Sentence Transformer embeddings, HDBSCAN, failure propagation, probability-ranked RCA, MRR evaluation | HDBSCAN V-Measure 0.7211 > baseline 0.6186; MRR 1.0 |
| **Phase 5** | OpenSearch knowledge store, vector retrieval, grounding validator, RAG pipeline, AI Assistant tab | 0% hallucination rate |
| **Phase 6** | HDBSCAN promoted to production, platform runner, health endpoint, benchmark, regression validation | Full integration validated |

---

## Evaluation Results

| Metric | Target | Result |
|---|---|---|
| RCA Top-1 Accuracy | ≥ 80% | **100%** (20/20) |
| RCA Top-3 Accuracy | ≥ 90% | **100%** (20/20) |
| MRR | ≥ 0.90 | **1.0000** |
| HDBSCAN V-Measure | > Greedy (0.6186) | **0.7211** |
| K-Means V-Measure | — | 0.3135 (below baseline) |
| Anomaly Precision | ≥ 0.80 | **1.00** |
| Anomaly Recall | ≥ 0.80 | 0.44 (documented) |
| Anomaly FPR | ≤ 10% | **0.00** |
| Hallucination Rate | ≤ 5% | **0.00%** |

---

## Quickstart

### Prerequisites

- Python 3.11+
- Docker Desktop
- PostgreSQL on localhost:5432 (database: `observability`, user: `trading`, password: `trading`)
- (Optional) `ANTHROPIC_API_KEY` for Claude Haiku answers in Tab 4

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start infrastructure

```bash
docker compose up -d       # Kafka + Zookeeper + OpenSearch
python storage/setup_db.py # PostgreSQL tables
python -m search.create_index  # OpenSearch index
```

### 3. Run the platform

```bash
# Terminal 1 — consumer + RAG API
python run_platform.py

# Terminal 2 — stream a scenario
python ingestion/producer.py --scenario S001

# Terminal 3 — dashboard
streamlit run dashboard/app.py
```

### 4. Deterministic evaluation (no Kafka required)

```bash
python -m evaluation.generate_report    # full Phase 3+4 evaluation → results.json
python -m evaluation.regression_test    # Phase 6 regression validation
python -m benchmark.stress_test         # performance benchmark
```

---

## Dashboard

Four tabs, one platform:

| Tab | What it shows |
|---|---|
| **Deterministic Analysis** | Run any of the 20 scenarios offline; see confidence ranking, propagation path, evidence, clusters |
| **Live Incidents** | Real-time incidents from PostgreSQL; auto-refresh; log search; incident history |
| **ML Evaluation** | Three-way clustering comparison, anomaly detection metrics, RCA accuracy, MRR |
| **AI Assistant** | Ask natural-language questions about any incident; grounded answers with hallucination validation |

---

## Project Structure

```
ai-observability-platform/
│
├── ingestion/
│   ├── producer.py          # Kafka log producer
│   └── consumer.py          # Kafka consumer: detection → RCA → evidence → DB
│
├── generator/
│   └── log_generator.py     # Deterministic scenario log generation (seed=42)
│
├── scenarios/
│   ├── scenarios.json        # 20 failure scenario definitions
│   └── ground_truth.json     # Ground truth labels + anomaly windows
│
├── rca/
│   ├── dependency_graph.py   # NetworkX service dependency graph
│   ├── detector.py           # Rule-based incident detection
│   ├── engine.py             # Graph-based RCA + probability-normalised ranking
│   ├── evidence.py           # Grounded evidence bullet generation
│   ├── propagation.py        # Failure propagation path analysis
│   ├── explainer.py          # Template-based explanation
│   └── clustering.py         # TF-IDF greedy baseline (kept for comparison)
│
├── ml/
│   ├── embeddings.py         # Sentence Transformer wrapper (all-MiniLM-L6-v2)
│   ├── hdbscan_clustering.py # HDBSCAN pipeline (production clustering engine)
│   ├── clustering.py         # K-Means (Phase 3 baseline)
│   ├── anomaly_detector.py   # Isolation Forest
│   └── vectorizer.py         # TF-IDF vectoriser
│
├── knowledge/
│   ├── incident_document.py  # Convert incident → knowledge document
│   ├── knowledge_builder.py  # build_and_index() + backfill_from_db()
│   └── indexer.py            # Embed summary + index to OpenSearch
│
├── search/
│   ├── opensearch_client.py  # Singleton OpenSearch client
│   ├── create_index.py       # Create incidents index (knn_vector, dim=384)
│   └── vector_search.py      # Embed query + knn retrieval
│
├── rag/
│   ├── prompt_builder.py     # Structured prompt with incident + history
│   ├── answer_generator.py   # LLM call (Claude Haiku) + question-aware fallback
│   ├── grounding_validator.py# Deterministic hallucination detection
│   └── rag_api.py            # FastAPI /ask, /ask/freeform, /health
│
├── storage/
│   ├── postgres.py           # Table creation + migration
│   └── repository.py         # CRUD for incidents and logs
│
├── evaluation/
│   ├── evaluate_rca.py       # Top-1/Top-3 accuracy
│   ├── evaluate_clustering.py# Greedy vs K-Means
│   ├── evaluate_hdbscan.py   # Three-way clustering comparison
│   ├── evaluate_anomalies.py # Isolation Forest precision/recall/FPR
│   ├── evaluate_ranking.py   # MRR
│   ├── evaluate_grounding.py # Hallucination rate
│   ├── evaluate_retrieval.py # Precision@5, Recall@5, MRR (OpenSearch)
│   ├── generate_report.py    # Orchestrator → results.json
│   ├── regression_test.py    # Phase 6: re-validate all targets post-integration
│   └── retrieval_queries.json# 10 labeled retrieval queries
│
├── benchmark/
│   └── stress_test.py        # Wall-clock throughput + P95 latency
│
├── dashboard/
│   └── app.py                # Streamlit dashboard (4 tabs)
│
├── configs/
│   └── settings.yaml         # All config: thresholds, Kafka, PostgreSQL, OpenSearch, RAG
│
├── run_platform.py           # Starts consumer + RAG API together
├── main.py                   # Offline single-scenario CLI
├── docker-compose.yml        # Kafka + Zookeeper + OpenSearch
├── REPRODUCIBILITY.md        # Fresh-clone setup + expected results
└── requirements.txt
```

---

## Key Engineering Decisions

**Why HDBSCAN over K-Means?**
Phase 3 found K-Means (V-Measure 0.3135) underperformed the greedy TF-IDF baseline (0.6186). The root cause: TF-IDF treats "DB connection timeout" and "connection pool exhausted" as unrelated because they share no words. HDBSCAN with Sentence Transformer embeddings (V-Measure 0.7211) captures semantic similarity that TF-IDF misses.

**Why probability-normalised confidence (`score/total`) instead of `score/max`?**
`score/max` always gives the top service a confidence of 1.0 regardless of how dominant it actually is. `score/total` makes the values probability-interpretable and sum to 1.0, so a 0.80 confidence is meaningfully different from a 0.40 confidence.

**Why deterministic hallucination detection instead of a second LLM call?**
LLM-as-judge introduces its own hallucination surface and adds latency and cost. A blocklist of metrics that don't exist in this system (CPU, memory, disk I/O) catches the most dangerous hallucinations for free, deterministically, and testably.

**Why does anomaly recall reach only 0.44?**
The true anomaly rate in the 20-scenario dataset is ~71%, above sklearn's Isolation Forest maximum contamination of 0.5. The model is clamped to 50% and is deliberately conservative — zero false positives in a production alerting system is more valuable than high recall.

---

## Lessons Learned

- **K-Means underperformed the greedy baseline.** More ML does not automatically mean better ML. The evaluation framework was built to surface this honestly.
- **HDBSCAN with embeddings outperformed.** Semantic representations recover clustering quality that TF-IDF cannot achieve with short, high-variance log messages.
- **Streaming timestamps ≠ wall-clock time.** Log timestamps in scenarios are simulation-relative. All latency benchmarks use `time.perf_counter()`.
- **Hallucination prevention is better done deterministically.** A domain-specific blocklist is faster, cheaper, and more reliable than a second LLM call.
- **Phase 4 evaluation corpus ≠ production conditions.** HDBSCAN was evaluated on balanced ERROR logs from root-cause services only. Production streaming uses all services at mixed incident states — different conditions require live validation.
