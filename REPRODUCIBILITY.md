# Reproducibility Guide

Every result in this project is reproducible from a fresh clone.
No manual data preparation, no secret seeds, no pre-trained fine-tuned models.

---

## Prerequisites

- Python 3.11+
- Docker Desktop (for Kafka, Zookeeper, OpenSearch)
- PostgreSQL running locally on port 5432
- (Optional) `ANTHROPIC_API_KEY` for Claude Haiku LLM answers

---

## Fresh Clone Setup

```bash
# 1. Clone and install
git clone <repo-url>
cd ai-observability-platform
pip install -r requirements.txt

# 2. Start infrastructure (Kafka + Zookeeper + OpenSearch)
docker compose up -d

# 3. Set up PostgreSQL tables
python storage/setup_db.py

# 4. Create OpenSearch index
python -m search.create_index

# 5. Start the platform
python run_platform.py                  # consumer + RAG API

# 6. Stream logs (in a separate terminal)
python ingestion/producer.py --scenario S001

# 7. Start the dashboard (in a separate terminal)
streamlit run dashboard/app.py
```

PostgreSQL connection defaults: host=localhost, port=5432, database=observability, user=trading, password=trading.
Edit `configs/settings.yaml` to change these.

---

## Deterministic Evaluation (No Kafka Required)

All evaluation scripts run offline from the scenario definitions.
Results are fixed by `seed=42` in `configs/settings.yaml`.

```bash
# Full evaluation pipeline (Phases 3 + 4)
python -m evaluation.generate_report

# Individual evaluations
python -m evaluation.evaluate_rca           # RCA Top-1/Top-3 accuracy
python -m evaluation.evaluate_clustering    # Greedy vs K-Means
python -m evaluation.evaluate_hdbscan       # Three-way clustering comparison
python -m evaluation.evaluate_anomalies     # Isolation Forest precision/recall
python -m evaluation.evaluate_ranking       # MRR across 20 scenarios
python -m evaluation.evaluate_grounding     # Hallucination rate (Phase 5)
python -m evaluation.evaluate_retrieval     # Precision@5, Recall@5 (needs OpenSearch)

# Phase 6 regression validation (all targets in one run)
python -m evaluation.regression_test

# Performance benchmark
python -m benchmark.stress_test
```

---

## Backfilling the Knowledge Store

After incidents have resolved, index them into OpenSearch:

```bash
python -m knowledge.knowledge_builder
```

---

## Expected Evaluation Results

| Metric | Value |
|---|---|
| RCA Top-1 Accuracy | 100% (20/20) |
| RCA Top-3 Accuracy | 100% (20/20) |
| MRR | 1.0000 |
| Greedy Baseline V-Measure | 0.6186 |
| K-Means V-Measure | 0.3135 |
| HDBSCAN V-Measure | 0.7211 |
| Anomaly Precision | 1.00 |
| Anomaly Recall | 0.44 |
| Anomaly FPR | 0.00 |
| Hallucination Rate | 0.0000 |

All results are written to `evaluation/results.json` after `python -m evaluation.generate_report`.

---

## Scenario Determinism

Log generation uses `seed=42` (set in `configs/settings.yaml`).
Each scenario also applies a `seed_offset = scenario_index * 7` to vary messages
between scenarios while keeping each individual run identical.

Changing `seed` in `configs/settings.yaml` will change log content but not the
evaluation framework or ground truth labels.
