# Phase 4 — Advanced Incident Correlation & Graph Intelligence (Final)

## Goal

Upgrade the platform from:

```text
Detect Incident
↓
Find Root Cause
```

to

```text
Detect Incident
↓
Correlate Similar Failures
↓
Explain Failure Propagation
↓
Rank Likely Root Causes
↓
Provide RCA Evidence
```

Phase 4 focuses on:

```text
Sentence Embeddings
+
HDBSCAN
+
Graph Analytics
+
Root Cause Explainability
```

Not LLMs.

---

## Why Phase 4 Exists

Phase 3 produced two important findings.

### Finding 1

```text
RCA Accuracy = 100%
```

for all 20 scenarios. Meaning: **root cause identification works**.

### Finding 2

```text
Greedy Clustering outperformed K-Means
```

Meaning: **more ML does not automatically mean better ML**.

### Phase 4 Question

Instead of:

```text
Can we improve RCA accuracy?
```

Ask:

```text
Can advanced clustering improve incident correlation quality
while preserving RCA accuracy?
```

Phase 4 is not "make RCA more accurate." Phase 4 is "make RCA more
explainable, more robust, and more realistic."

---

## Success Criteria

### Clustering

Evaluate Greedy vs K-Means vs HDBSCAN.

| Metric          | Target     |
| --------------- | ---------- |
| V-Measure       | ≥ Baseline (0.6186) |
| NMI             | ≥ Baseline (0.6186) |
| Noise Reduction | ≥ 90%      |

**Transparency Requirement:** every clustering report must include Cluster
Count alongside V-Measure, NMI, and Noise Reduction.

| Method  | Clusters | V-Measure |
| ------- | -------- | --------- |
| Greedy  | 21       | 0.62      |
| K-Means | 5        | 0.31      |
| HDBSCAN | 18       | ?         |

This prevents score inflation through over-fragmentation — a high V-Measure
from a method that simply produces many small clusters is not evidence that
the method is better.

### RCA

Top-1 and Top-3 accuracy are now **regression tests**, not improvement
targets, because Phase 3 already achieved 100% on both.

| Metric         | Target        |
| -------------- | ------------- |
| Top-1 Accuracy | Maintain 100% |
| Top-3 Accuracy | Maintain 100% |

### New RCA Goal

Evaluate **Root Cause Ranking Quality** using Mean Reciprocal Rank (MRR).

```text
MRR ≥ 0.90
```

### Dependency Analysis

Correctly identify root cause → affected services → failure propagation
path for all 20 scenarios (see Step 6 for the precise match definition).

---

## Architecture Evolution

Phase 3:

```text
Logs
 ↓
Isolation Forest
 ↓
TF-IDF
 ↓
K-Means
 ↓
RCA
```

Phase 4:

```text
Logs
 ↓
Sentence Transformer Embeddings
 ↓
HDBSCAN
 ↓
Dependency Graph Analysis
 ↓
Root Cause Ranking
 ↓
RCA Evidence Generation
```

---

## Step 1 — Preserve Existing Models

Keep unchanged:

```text
rca/clustering.py
ml/clustering.py
```

These remain benchmark baselines. Do NOT delete anything — Phase 4 compares
against them, it does not replace them.

---

## Step 2 — Sentence Embeddings

Create:

```text
ml/embeddings.py
```

Model: `all-MiniLM-L6-v2` via `sentence-transformers`.

**Input:**

```text
Database timeout
```

**Output:** 384-dimensional embedding vector.

---

## Step 3 — HDBSCAN Clustering

Create:

```text
ml/hdbscan_clustering.py
```

Pipeline:

```text
Logs
↓
Embeddings
↓
HDBSCAN
↓
Clusters
```

### Corpus Consistency Rule

All three clustering methods (Greedy, K-Means, HDBSCAN) must run on the
**exact same evaluation corpus** used in Phase 3: ERROR logs from root-cause
services only. This preserves comparability with the Phase 3 baseline and
guarantees an apples-to-apples comparison.

---

## Step 4 — Clustering Evaluation

Create:

```text
evaluation/evaluate_hdbscan.py
```

Compare Greedy / K-Means / HDBSCAN on:

* V-Measure
* NMI
* Noise Reduction
* Cluster Count

Generate:

```text
evaluation/comparison_report.json
```

---

## Step 5 — Dependency Graph Module

Move graph logic into:

```text
rca/dependency_graph.py
```

### Graph Definition

Edges represent `depends_on`:

```text
Reporting → Analytics
Analytics → ETL
ETL → Metadata
Metadata → Database
```

Meaning: Reporting depends on Analytics, and so on upstream to Database.

---

## Step 6 — Failure Propagation Analysis

Create:

```text
rca/propagation.py
```

Goal: determine **how** a failure spread, not just what failed.

**Example output:**

```json
{
  "root_cause": "database",
  "propagation_path": [
    "database",
    "metadata",
    "etl",
    "analytics",
    "reporting"
  ]
}
```

### Propagation Match Definition

"Propagation path matched dependency graph" means:

**Rule 1 — Reachability.** Every affected service must be reachable
downstream from the predicted root cause. If `["database", "etl",
"analytics"]` are all reachable from `database`, this is a **MATCH**.

**Rule 2 — Exact path equality is NOT required.** If observed services are
`["database", "etl", "reporting"]` and the full graph chain is
`database → metadata → etl → analytics → reporting`, this is still a
**MATCH** — every observed service lies on a valid dependency chain, even
though `metadata` and `analytics` weren't observed.

**Rule 3 — Mismatch condition.** A mismatch occurs when an affected service
cannot be explained by graph traversal. If `["database", "etl",
"external_api"]` are observed and `external_api` is not downstream of
`database`, this is **NO MATCH**.

---

## Step 7 — Root Cause Ranking

Current RCA returns a single service. Phase 4 returns ranked confidence:

```json
{
  "database": 0.91,
  "metadata": 0.06,
  "etl": 0.02,
  "analytics": 0.01
}
```

### Important Clarification

These confidence scores are **not** produced by a new ML model. They are
derived from the existing RCA graph scores (the "downstream victims
explained" count from Phase 1), normalized:

```python
raw_scores = {"database": 12, "metadata": 1, "etl": 0}
confidence = score / total
```

### Purpose

This is an **explainability upgrade**, not an accuracy upgrade — RCA already
achieves 100% Top-1/Top-3 from Phase 1/3. Ranking adds calibrated confidence
on top of an already-correct answer; it does not make the answer more
correct.

---

## Step 8 — MRR Evaluation

Create:

```text
evaluation/evaluate_ranking.py
```

Metric: Mean Reciprocal Rank.

```text
True cause ranked #1 → MRR = 1.0
True cause ranked #2 → MRR = 0.5
```

Target: `MRR ≥ 0.90`

---

## Step 9 — RCA Evidence Generation

Create:

```text
rca/evidence.py
```

Generate evidence supporting RCA decisions:

```json
{
  "root_cause": "database",
  "evidence": [
    "Database generated first ERROR",
    "4 downstream services impacted",
    "All affected services are reachable from database in dependency graph"
  ]
}
```

### Evidence Rules

Every RCA explanation must provide at least one of:

* First error evidence
* Dependency graph evidence
* Propagation path evidence (per the match definition in Step 6)
* Downstream impact evidence

The RCA conclusion must always be traceable back to observable system
behavior — no evidence line may assert something that can't be checked
against logs or the graph.

---

## Step 10 — Automated Reporting

Extend `evaluation/results.json`:

```json
{
  "clustering": {
    "greedy": {},
    "kmeans": {},
    "hdbscan": {}
  },
  "ranking": {
    "mrr": 0.95
  }
}
```

---

## Build Order

1. `ml/embeddings.py` — Sentence Transformer wrapper
2. `ml/hdbscan_clustering.py` — embeddings → HDBSCAN pipeline
3. `evaluation/evaluate_hdbscan.py` — three-way comparison with cluster count transparency
4. `rca/dependency_graph.py` — graph logic moved/centralized here
5. `rca/propagation.py` — propagation path + match definition (Rules 1–3)
6. Root cause ranking logic (normalize existing RCA scores)
7. `evaluation/evaluate_ranking.py` — MRR calculation
8. `rca/evidence.py` — evidence generation
9. `evaluation/results.json` — extend with clustering + ranking sections

> `rca/clustering.py` and `ml/clustering.py` remain untouched throughout —
> they are baselines being compared against, not replaced.

---

## Deliverables

By the end of Phase 4:

* Sentence Transformer embeddings
* HDBSCAN clustering
* Three-way clustering comparison (Greedy / K-Means / HDBSCAN)
* Cluster count transparency reporting
* Dependency graph module
* Failure propagation analysis with precise match definition
* Root-cause ranking (explainability, not accuracy)
* MRR evaluation
* RCA evidence generation
* Advanced graph-based RCA

---

## What NOT to Build in Phase 4

Do NOT add:

* OpenSearch
* RAG
* LLM explanations
* LangGraph
* Chat interface
* AWS deployment
* Knowledge Graph

The knowledge graph is deferred to Phase 5, where it will have a clear
purpose for RAG retrieval rather than being designed speculatively.

---

## Mental Model

**Phase 1 proved:**

> Can we detect incidents?

**Phase 2 proved:**

> Can we process incidents in real time?

**Phase 3 proved:**

> Can we objectively evaluate ML methods?

**Phase 4 proves:**

> Can we explain why a root cause was selected, how failures propagated
> through the system, and whether semantic clustering genuinely outperforms
> simpler approaches?
