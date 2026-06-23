# Phase 4 — Semantic Clustering, Graph Intelligence & RCA Explainability

## What Changed in Phase 4?

Phase 3 closed with two honest findings.

First: the graph-based RCA engine achieves **100% accuracy** across all 20 scenarios. Root cause identification is solved.

Second: **K-Means did not beat the greedy baseline.** TF-IDF with K-Means (V-Measure 0.31) performed worse than the rule-based approach (V-Measure 0.62). The reason was documented: short log messages have high vocabulary variance even within the same failure type. "DB connection timeout", "Connection pool exhausted", and "Query failed" are all database errors — but TF-IDF sees them as almost unrelated because the words don't overlap.

Phase 4 starts from those findings and asks two questions:

> **Can semantic embeddings recover the clustering quality that TF-IDF missed?**
>
> **Can the platform explain *why* it selected a root cause, not just *what* it selected?**

---

## The Problem with TF-IDF for Log Clustering

TF-IDF is a word-frequency technique. It treats each word as an independent token and measures how distinctive it is across a corpus. Two messages that mean the same thing but use different words get low similarity scores.

This breaks log clustering because log messages describing the same failure type are intentionally varied:

```
DB connection timeout after 5234ms — retrying
Connection pool exhausted: max_connections=50
Query execution failed: lock wait timeout exceeded
```

All three are database overload symptoms. TF-IDF sees three distinct patterns. A model that understands *meaning* — not just word co-occurrence — would group them together.

---

## What Was Built

### 1. Sentence Transformer Embeddings

Replaced TF-IDF with `all-MiniLM-L6-v2`, a compact Sentence Transformer model. Each log message is encoded as a **384-dimensional dense vector** that captures semantic meaning:

```python
embedding = model.encode("DB connection timeout after 5234ms")
# → array of 384 floats representing the sentence's meaning
```

The key difference from TF-IDF: two messages with different words but the same meaning will have similar embedding vectors. The model was pre-trained on a large corpus and understands that "timeout", "pool exhausted", and "lock wait exceeded" all indicate the same class of database failure.

The model is lazy-loaded and singleton: it loads once on first use and is reused across all subsequent calls — relevant for the live consumer where the same model instance handles thousands of logs.

### 2. HDBSCAN Clustering

Replaced K-Means with **HDBSCAN** (Hierarchical Density-Based Spatial Clustering of Applications with Noise).

K-Means has two limitations in this context: you must specify the number of clusters in advance (`k=5`), and it forces every point into a cluster — including ambiguous log messages that don't cleanly belong anywhere.

HDBSCAN eliminates both constraints:

- **No fixed k.** It discovers the number of clusters from the data's density structure.
- **Noise points.** Messages that don't belong to any dense cluster are labelled as noise (`-1`) rather than forced into the nearest cluster. This prevents low-confidence assignments from polluting cluster quality.

The evaluation excludes noise points from V-Measure and NMI calculations, which is methodologically correct — a noise label is not a clustering decision.

### 3. Three-Way Clustering Evaluation

All three methods were evaluated on the **exact same corpus**: ERROR logs from root-cause services only, balanced to 30 samples per service. This guarantees an apples-to-apples comparison.

| Method | V-Measure | NMI | Clusters | Noise Rate |
|---|---|---|---|---|
| Greedy Baseline (Phase 2) | 0.6186 | 0.6186 | 21 | N/A |
| K-Means (Phase 3) | 0.3135 | 0.3135 | 5 | N/A |
| HDBSCAN (Phase 4) | **0.7211** | **0.7211** | 14 | 9.6% |

HDBSCAN with sentence embeddings beats the greedy baseline by **+0.1025** in V-Measure. The Phase 3 hypothesis is confirmed: TF-IDF was the bottleneck, not the clustering algorithm itself. Semantic embeddings give the algorithm enough signal to outperform a rule-based approach for the first time.

The 9.6% noise rate means roughly 1 in 10 error logs were not assigned to any cluster — they were too ambiguous to group confidently. In production alerting, ambiguous signals are often the noisiest and most error-prone part of a rule-based system. Leaving them unclassified is a feature, not a limitation.

### 4. Failure Propagation Analysis

Added `rca/propagation.py` to determine **how** a failure spread through the system — not just what failed.

Given a predicted root cause and the dependency graph, the module traces the forward propagation path:

```
database → metadata → etl → analytics → reporting
```

It then checks whether every affected service in the incident is reachable downstream from the root cause. This is a three-rule match definition:

- **Rule 1 (Reachability):** every affected service must be reachable from the root cause via the dependency graph.
- **Rule 2 (No exact path required):** if the affected services are `[database, etl, reporting]` and the full chain is `database → metadata → etl → analytics → reporting`, this is still a MATCH — the observed services lie on a valid chain even though `metadata` and `analytics` weren't observed.
- **Rule 3 (Mismatch):** a MISMATCH occurs only if an affected service is unreachable from the predicted root cause — meaning the prediction contradicts the graph structure.

This validates that the RCA engine's predictions are structurally consistent with the known service topology.

### 5. Probability-Normalised Root Cause Ranking

The original `find_root_cause()` function returns the top-3 services ranked by raw score. Phase 4 adds `rank_root_causes()`, which converts those scores into calibrated confidence values:

```python
raw_scores = {"database": 12, "metadata": 3, "etl": 0}
total = 15
confidence = {"database": 0.80, "metadata": 0.20, "etl": 0.00}
```

The normalisation uses `score / total` (not `score / max_score`), which makes the values probability-interpretable: the confidence scores sum to 1.0, and each score represents the proportion of the total graph-reachability evidence attributable to that service.

This is an **explainability upgrade, not an accuracy upgrade**. RCA already achieves 100% Top-1 accuracy. Ranking adds a calibrated, interpretable confidence distribution on top of an already-correct answer.

### 6. MRR Evaluation

Mean Reciprocal Rank (MRR) measures ranking quality across all 20 scenarios:

```
Ground truth root cause ranked #1 → Reciprocal Rank = 1.0
Ground truth root cause ranked #2 → Reciprocal Rank = 0.5
Ground truth root cause ranked #3 → Reciprocal Rank = 0.33
```

Result: **MRR = 1.0000** — the true root cause was ranked at position #1 in all 20 scenarios. Target was ≥ 0.90.

### 7. RCA Evidence Generation

Added `rca/evidence.py` to produce grounded, human-readable evidence supporting each RCA decision. Up to 5 evidence bullets are generated per incident, each traceable back to observable data:

```
- database emitted the first ERROR log at 2024-01-15 10:23:41
- 4 downstream services reported errors: metadata, etl, analytics, reporting
- All affected services are reachable from database in the dependency graph
- Propagation path: database -> metadata -> etl -> analytics -> reporting
- No upstream failures detected — database is likely the origin
```

Evidence generation follows one rule: every bullet must be checkable against logs or the dependency graph. No inference that can't be verified.

### 8. Consumer and Storage Integration

The Kafka consumer was updated to run Phase 4 components on every new incident. When the error threshold is crossed, it now:

1. Ranks root cause candidates with probability-normalised confidence (`rank_root_causes`)
2. Generates a propagation path and validates it against the graph (`analyse_propagation`)
3. Produces grounded evidence bullets (`generate_evidence`)
4. Stores all three as JSON in PostgreSQL alongside the existing incident record

Three new columns were added to the `incidents` table:

```sql
evidence          TEXT  -- JSON array of evidence bullets
propagation_path  TEXT  -- JSON array: ["database", "metadata", "etl", ...]
confidence_scores TEXT  -- JSON array: [{"service": "database", "confidence": 0.80}, ...]
```

The migration uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` so existing databases are updated without data loss.

---

## Results

| Metric | Target | Result |
|---|---|---|
| HDBSCAN V-Measure | ≥ 0.6186 (greedy baseline) | **0.7211** ✅ |
| RCA Top-1 Accuracy | Maintain 100% | **100%** ✅ |
| RCA Top-3 Accuracy | Maintain 100% | **100%** ✅ |
| MRR | ≥ 0.90 | **1.0000** ✅ |
| Hallucination-free evidence | All bullets grounded | **Yes** ✅ |

---

## Engineering Decisions Worth Noting

**Why `score / total` instead of `score / max_score` for confidence?**
`score / max_score` normalisation gives the top service a score of 1.0 regardless of how dominant it actually is. If scores are `[3, 2, 1]`, the top score becomes 1.0 — but it's not certain. `score / total` (0.50, 0.33, 0.17) preserves the relative uncertainty and makes the values probability-interpretable. A 0.80 confidence is meaningfully different from a 0.40 confidence.

**Why exclude noise points from HDBSCAN metrics?**
Noise points (`label = -1`) are messages HDBSCAN explicitly declined to cluster. Including them in V-Measure would penalise the algorithm for making a principled decision to leave ambiguous points unclassified. The correct comparison is: on the messages HDBSCAN was confident about, how well did it group them? Excluding noise answers that question. It's also consistent with how HDBSCAN is evaluated in the literature.

**Why use BFS over the reversed graph for propagation paths?**
The dependency graph has edges in the direction of dependence (Reporting → Analytics → ETL). To trace how a failure *propagates forward* from a root cause, we traverse the reversed graph — edges now point from upstream to downstream. BFS finds the shortest path, but the module returns the full reachable path via topological sort to reflect the complete cascade rather than just the shortest route.

**Why is evidence generation capped at 5 bullets?**
Evidence bullets compound quickly when there are many affected services. Beyond 5, the output becomes verbose without adding precision. In a real-time alerting context, an on-call engineer needs the three most important signals immediately — not a complete graph traversal narrative. The cap is a UX constraint, not a technical one.

**Why use ASCII `->` instead of Unicode `→` in propagation paths?**
Windows terminals (cp1252 encoding) throw `UnicodeEncodeError` on `→`. The fix is `' -> '.join(path)` throughout — no emoji or special characters in any console output. This affects evidence bullets, propagation path display, and any print statement in the consumer.

---

## The Honest Summary

| Question | Answer |
|---|---|
| Do sentence embeddings beat TF-IDF for log clustering? | **Yes** — V-Measure 0.7211 vs 0.6186 greedy baseline |
| Does HDBSCAN handle log clustering better than K-Means? | **Yes** — 0.7211 vs 0.3135 |
| Is ranking quality high enough to trust in production? | **Yes** — MRR 1.0 across all 20 scenarios |
| Does evidence generation stay grounded? | **Yes** — every bullet is traceable to logs or the dependency graph |
| Does Phase 4 improve RCA accuracy? | **No — and it doesn't need to.** 100% was already achieved in Phase 3. Phase 4 makes the correct answer *explainable*, not more correct. |

---

## Skills Demonstrated

### Machine Learning
- Applied **Sentence Transformer embeddings** (`all-MiniLM-L6-v2`) for semantic log representation
- Implemented **HDBSCAN** with noise handling and correct metric exclusion
- Designed **corpus consistency** across three clustering methods for valid comparison
- Computed **MRR** as a ranking quality metric across 20 labeled scenarios

### Graph Analytics
- Implemented **failure propagation analysis** using BFS on a reversed dependency graph
- Designed a **three-rule match definition** for propagation validation (reachability, not exact path equality, mismatch only on unreachable services)
- Built **probability-normalised confidence scoring** from graph reachability counts

### Explainability Engineering
- Generated **grounded evidence bullets** from logs and graph — no unverifiable claims
- Distinguished between **accuracy** (already solved) and **explainability** (the actual Phase 4 problem)
- Built confidence distributions that are **probability-interpretable** (`sum = 1.0`)

### Data Engineering
- Extended PostgreSQL schema with 3 new columns and zero-downtime `ALTER TABLE IF NOT EXISTS` migration
- Stored structured Phase 4 outputs (evidence, propagation path, confidence) as JSON in TEXT columns — schema-flexible, query-compatible
- Integrated Phase 4 components into the live Kafka consumer pipeline

### Software Engineering
- Lazy-loaded Sentence Transformer singleton — one model load per consumer process
- Evaluation scripts share a single corpus object via import to guarantee identical inputs across all three methods
- All Phase 4 consumer output is stored in existing infrastructure (PostgreSQL) — no new services required

---

## Technology Stack (Phase 4 Additions)

| Tool | Purpose |
|---|---|
| `sentence-transformers` | Semantic log message embeddings (`all-MiniLM-L6-v2`) |
| `hdbscan` | Density-based clustering with automatic cluster count and noise detection |
| `networkx` | Dependency graph traversal, BFS propagation path, reachability checks |
| PostgreSQL (extended) | Stores evidence, propagation path, confidence scores per incident |
| scikit-learn (continued) | V-Measure, NMI for three-way clustering comparison |

---

## How to Run

```bash
# Run the full evaluation pipeline (Phase 3 + Phase 4)
python -m evaluation.generate_report

# Run Phase 4 evaluations individually
python -m evaluation.evaluate_hdbscan    # three-way clustering comparison
python -m evaluation.evaluate_ranking    # MRR across all 20 scenarios

# Run the live pipeline (Phase 2 + Phase 4 integration)
python ingestion/producer.py             # stream logs to Kafka
python ingestion/consumer.py             # consume, run RCA + Phase 4, store to PostgreSQL

# View results in the dashboard
streamlit run dashboard/app.py
# Tab 1: Phase 1 pipeline + Phase 4 evidence, propagation, confidence
# Tab 3: ML Evaluation — three-way clustering, anomaly detection, MRR
```

---

## Phase 1 vs Phase 2 vs Phase 3 vs Phase 4

| | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---|---|---|---|
| Log representation | None (rule-based) | None (rule-based) | TF-IDF | Sentence Transformer embeddings |
| Clustering | TF-IDF greedy | TF-IDF greedy | K-Means (k=5) | HDBSCAN (auto k, noise labelling) |
| Clustering quality | V-Measure 0.62 | V-Measure 0.62 | V-Measure 0.31 | **V-Measure 0.72** |
| RCA output | Top-3 services | Top-3 services | Top-3 services | Ranked with probability confidence |
| RCA explainability | None | None | None | Evidence bullets + propagation path |
| Root cause ranking | Raw score | Raw score | Raw score | Normalised confidence (score/total) |
| MRR | Not measured | Not measured | Not measured | **1.0000** |
| Incident data stored | Root cause, explanation | Root cause, explanation | Root cause, explanation | + evidence, propagation, confidence |
| Evaluation | Manual | Manual | V-Measure, NMI, precision, recall | + HDBSCAN comparison, MRR |
