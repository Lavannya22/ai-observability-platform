# Phase 3 — Machine Learning & Evaluation Framework (Final)

## Goal

Upgrade the observability platform from rule-based intelligence to machine-learning-driven intelligence while preserving:

* Kafka streaming
* Incident lifecycle
* Incident merging
* RCA correctness
* Reproducible evaluation

Phase 3 focuses on:

```text
Machine Learning
+
Evaluation
```

Not Generative AI.

---

## Success Criteria

### Clustering

* V-Measure ≥ 0.80
* NMI ≥ 0.80
* Global Noise Reduction ≥ 90%

### Anomaly Detection

* Precision ≥ 0.80
* Recall ≥ 0.80
* False Positive Rate ≤ 10%

### RCA

* Top-1 Accuracy ≥ 80%
* Top-3 Accuracy ≥ 90%

### Evaluation

* 20+ labeled scenarios
* Automated evaluation pipeline
* Reproducible metrics

---

## Architecture Evolution

Phase 2:

```text
Logs
 ↓
Kafka
 ↓
Rule Detection
 ↓
Greedy Clustering
 ↓
RCA
```

Phase 3:

```text
Logs
 ↓
Kafka
 ↓
Isolation Forest
 ↓
TF-IDF Vectorization
 ↓
K-Means Clustering
 ↓
RCA
 ↓
Evaluation
```

---

## Step 1 — Expand Scenario Coverage

Current:

```text
S001 Database Overload
S002 Metadata Failure
S003 ETL Failure
S004 Reporting Failure
```

Expand to 20+ scenarios:

```text
S005 Schema Mismatch
S006 Null Data Explosion
S007 Duplicate Records
S008 Upstream API Failure
S009 Disk Exhaustion
S010 Slow Query
S011 Memory Leak
S012 Kafka Consumer Lag
S013 Corrupted File
S014 Late Arriving Data
S015 Job Timeout
S016 High Retry Rate
S017 Analytics Failure
S018 Dashboard Failure
S019 Partial Pipeline Failure
S020 Multi-Service Cascade
```

Goal: **20+ labeled incidents**.

---

## Step 2 — Extend Ground Truth Dataset

Continue using:

```text
scenarios/ground_truth.json
```

as the single source of truth. Do NOT create a second ground truth file.

### Updated Schema

```json
{
  "scenario_id": "S001",
  "root_cause": "database",
  "affected_services": [
    "metadata",
    "etl",
    "analytics"
  ],
  "anomaly_window": {
    "start_offset_seconds": 60,
    "end_offset_seconds": 180
  }
}
```

### Why `anomaly_window` Exists

Needed to calculate:

* Precision
* Recall
* False Positive Rate

Without anomaly labels, TP/FP/FN cannot be computed for anomaly detection.

---

## Step 3 — Create ML Module

```text
ml/
├── vectorizer.py
├── clustering.py
├── anomaly_detector.py
└── model_utils.py
```

---

## Step 4 — Preserve Phase 2 Clustering as Baseline

Do NOT delete:

```text
rca/clustering.py
```

It becomes the baseline model.

### Baseline Model

Uses:

* Greedy clustering
* TF-IDF similarity
* Threshold matching

### ML Model

```text
ml/clustering.py
```

Uses:

* TF-IDF
* K-Means

### Evaluation Goal

Compare baseline clustering vs ML clustering before replacing anything.

---

## Step 5 — TF-IDF Vectorization

File:

```text
ml/vectorizer.py
```

Convert logs into vector representations:

```python
vectors = tfidf.fit_transform(log_messages)
```

---

## Step 6 — K-Means Clustering

File:

```text
ml/clustering.py
```

### K Selection Strategy

K must never be hardcoded.

**Evaluation Mode:**

```python
k = number_of_distinct_root_causes
```

Not `number_of_scenarios` — multiple scenarios may share the same root cause
(e.g. `S001 Database Overload` and `S010 Slow Query` may both map to
`Database`), so root-cause labels provide a more stable clustering target
than scenario IDs.

**Future Production Mode:**

Phase 4 will replace K-Means with HDBSCAN, which automatically discovers
cluster counts without a fixed `k`.

---

## Step 7 — Isolation Forest

Replace:

```python
error_count > threshold
```

with:

```python
IsolationForest
```

File:

```text
ml/anomaly_detector.py
```

### Features (per service)

```text
errors_per_minute
warnings_per_minute
avg_latency
retry_count
```

Example:

```python
[120, 15, 800, 10]
```

---

## Step 8 — Evaluation Framework

```text
evaluation/
├── evaluate_clustering.py
├── evaluate_anomalies.py
├── evaluate_rca.py
├── compare_models.py
└── generate_report.py
```

---

## Step 9 — Clustering Evaluation

Metrics:

```python
v_measure_score()
normalized_mutual_info_score()
```

Compare baseline vs ML model:

```text
Baseline V-Measure: 0.72
ML V-Measure:       0.86

Baseline NMI:       0.70
ML NMI:             0.84
```

### Important Clarification

Clustering evaluation is performed at the **cluster level**.

The objective is: did logs with the same root cause end up in the same
cluster? A cluster may legitimately contain logs from multiple scenarios
if they share the same root cause.

---

## Step 10 — Anomaly Evaluation

Using `anomaly_window` from `scenarios/ground_truth.json`, calculate:

**Precision**

```text
TP / (TP + FP)
```

**Recall**

```text
TP / (TP + FN)
```

**False Positive Rate**

```text
FP / (FP + TN)
```

---

## Step 11 — RCA Evaluation

Run:

```bash
python evaluate_rca.py
```

For every scenario:

```text
Predicted Root Cause
Actual Root Cause
```

Metrics:

```text
Top-1 Accuracy  (target ≥ 80%)
Top-3 Accuracy  (target ≥ 90%)
```

### Important Clarification

RCA evaluation is performed at the **scenario level**.

Even if `S001 Database Overload` and `S010 Slow Query` are grouped into the
same cluster, RCA is evaluated separately for `S001` and `S010` using each
scenario's own logs. This keeps clustering quality and RCA accuracy as
independent metrics — a clustering decision never changes how RCA is scored.

---

## Step 12 — Automated Reporting

Generate:

```text
evaluation/results.json
```

```json
{
  "v_measure": 0.85,
  "nmi": 0.84,
  "precision": 0.87,
  "recall": 0.83,
  "false_positive_rate": 0.08,
  "top1_rca_accuracy": 0.90,
  "top3_rca_accuracy": 0.96
}
```

---

## Build Order

1. `scenarios/scenarios.json` — add S005–S020
2. `scenarios/ground_truth.json` — extend existing entries + add `anomaly_window` to all
3. `ml/__init__.py`
4. `ml/vectorizer.py` — TF-IDF vectorization (used by both clustering and anomaly features)
5. `ml/clustering.py` — K-Means with `k = number_of_distinct_root_causes`
6. `ml/anomaly_detector.py` — Isolation Forest
7. `ml/model_utils.py` — shared helpers
8. `evaluation/evaluate_clustering.py` — baseline vs ML comparison
9. `evaluation/evaluate_anomalies.py` — precision/recall/FPR using `anomaly_window`
10. `evaluation/evaluate_rca.py` — per-scenario Top-1/Top-3 accuracy
11. `evaluation/compare_models.py`
12. `evaluation/generate_report.py` — writes `evaluation/results.json`

> `rca/clustering.py` and `rca/detector.py` (rule-based) remain unchanged and
> untouched — they are the baseline being measured against, not replaced.

---

## Deliverables

By the end of Phase 3:

* 20+ failure scenarios
* Extended ground truth dataset
* TF-IDF vectorization
* Isolation Forest anomaly detection
* K-Means clustering
* Baseline vs ML comparison
* Automated evaluation framework
* V-Measure reporting
* NMI reporting
* RCA accuracy measurement
* Reproducible metrics

---

## What NOT to Build in Phase 3

Do NOT add:

* Sentence Transformers
* HDBSCAN
* OpenSearch
* RAG
* LLM explanations
* LangGraph
* AWS deployment

These belong to later phases.

---

## Mental Model

**Phase 1 proved:**

> Can we detect incidents?

**Phase 2 proved:**

> Can we ingest, correlate, and investigate incidents in real time?

**Phase 3 proves:**

> Can machine learning outperform our rule-based baseline, and can we prove it with objective, reproducible metrics?
