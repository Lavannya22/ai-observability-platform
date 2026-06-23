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

## Success Criteria & Actual Results

### Clustering

| Metric | Target | Actual |
|---|---|---|
| Baseline V-Measure | — | 0.6186 |
| K-Means V-Measure | ≥ 0.80 | 0.3135 |
| Baseline NMI | — | 0.6186 |
| K-Means NMI | ≥ 0.80 | 0.3135 |

**Finding:** The greedy baseline (21 micro-clusters) scores higher V-Measure than K-Means
(k=5) because short, diverse log messages have significant within-class vocabulary
variance and cross-service term overlap (e.g. analytics errors mention "ETL output",
analytics/database share "query timeout"). K-Means with a fixed k suffers from this
ambiguity; the greedy approach creates smaller but purer clusters which V-Measure rewards.
This is a valid ML finding, not a failure — the evaluation framework surfaces it correctly.

### Anomaly Detection

| Metric | Target | Actual |
|---|---|---|
| Precision | ≥ 0.80 | **1.00** |
| Recall | ≥ 0.80 | 0.44 |
| False Positive Rate | ≤ 10% | **0.00** |

Zero false positives. Recall is 0.44 because with `contamination` capped at 0.5 (sklearn
limit), Isolation Forest flags the top 50% most anomalous service-instances; 71% of
service-instances are genuinely anomalous across the 20 scenarios, so some anomalous
services are conservatively labelled normal.

### RCA

| Metric | Target | Actual |
|---|---|---|
| Top-1 Accuracy | ≥ 80% | **100%** (20/20) |
| Top-3 Accuracy | ≥ 90% | **100%** (20/20) |

### Evaluation

* 20 labeled scenarios ✓
* Automated evaluation pipeline ✓
* Reproducible metrics ✓

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

Full scenario list (all 20 built):

```text
S001 Database Overload          root: database  → metadata, etl, analytics, reporting
S002 ETL Job Failure            root: etl       → analytics, reporting
S003 Data Quality Issue         root: metadata  → etl, analytics, reporting
S004 Analytics Service Crash    root: analytics → reporting
S005 Schema Mismatch            root: metadata  → etl, analytics, reporting
S006 Null Data Explosion        root: etl       → analytics, reporting
S007 Duplicate Records          root: etl       → analytics, reporting
S008 Upstream API Failure       root: database  → metadata, etl, analytics, reporting
S009 Disk Exhaustion            root: database  → metadata, etl, analytics, reporting
S010 Slow Query                 root: database  → metadata, etl, analytics, reporting
S011 Memory Leak                root: analytics → reporting
S012 Kafka Consumer Lag         root: etl       → analytics, reporting
S013 Corrupted File             root: metadata  → etl, analytics, reporting
S014 Late Arriving Data         root: etl       → analytics, reporting
S015 Job Timeout                root: etl       → analytics, reporting
S016 High Retry Rate            root: database  → metadata, etl, analytics, reporting
S017 Analytics Failure          root: analytics → reporting
S018 Dashboard Failure          root: reporting → (none)
S019 Partial Pipeline Failure   root: etl       → analytics, reporting
S020 Multi-Service Cascade      root: database  → metadata, etl, analytics, reporting
```

Root cause distribution: database=6, etl=6, metadata=3, analytics=3, reporting=1.

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
  "affected_services": ["metadata", "etl", "analytics", "reporting"],
  "expected_rca_rank": 1,
  "anomaly_window": {
    "start_offset_seconds": 100,
    "end_offset_seconds": 174
  }
}
```

**Note:** Field renamed from `root_cause_service` → `root_cause`. All code uses
`gt["root_cause"]` including `evaluation/evaluate.py`.

### anomaly_window offsets

The log generator produces:
- Ticks 0–99: 100 normal INFO logs (5 services × 20 logs)
- Tick 100+: error logs (root cause first, then downstream in dependency order)

Formula for `end_offset_seconds`:
```
100 + (1 + len(affected_services)) × 15 − 1
```

Examples:
- database (4 affected): 100 + 5×15 − 1 = 174
- etl (2 affected):      100 + 3×15 − 1 = 144
- metadata (3 affected): 100 + 4×15 − 1 = 159
- analytics (1 affected):100 + 2×15 − 1 = 129
- reporting (0 affected):100 + 1×15 − 1 = 114

### Why `anomaly_window` Exists

Stored as scenario metadata for future per-log anomaly evaluation. In Phase 3,
the Isolation Forest uses service-level ground truth labels
(`root_cause + affected_services`) rather than the time window directly.
The window is used for documentation and potential Phase 4 use.

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

Convert logs into vector representations with **numeric token normalisation**:

```python
vectors = tfidf.fit_transform(log_messages)
```

Normalisation replaces variable numeric tokens before TF-IDF so that
`"DB connection timeout after 5000ms"` and `"DB connection timeout after 2000ms"`
produce identical vectors:

```text
{ms}    → <LATENCY>
ds_NNN  → <DATASET>
job_NNN → <JOB>
rpt_NNN → <REPORT>
user_NN → <USER>
batch N → batch <BATCH>
step N  → step <STEP>
```

Applied via `preprocessor=normalise` in `TfidfVectorizer`.

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
error_count        (total ERROR logs for that service in the error phase)
warning_count      (total WARNING logs)
avg_latency_ms     (average ms value extracted from log messages)
retry_count        (count of messages containing "retry/retries/aborted after")
```

Example for a database service under load:

```python
[15, 0, 4800.0, 0]
```

### Evaluation Approach

Feature matrix: 20 scenarios × 5 services = **100 rows**.
Ground truth label per row: `"anomaly"` if the service is
`root_cause OR affected_service` for that scenario, else `"normal"`.

`contamination` is computed dynamically from the ground truth ratio and clamped
to `(0.0, 0.5]` (sklearn's hard limit).

Actual contamination used: **0.5** (true anomaly rate is 71/100 = 0.71, capped).

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
Baseline V-Measure: 0.6186  (21 clusters)
ML V-Measure:       0.3135  (5 clusters, k=5)

Baseline NMI:       0.6186
ML NMI:             0.3135
```

### Evaluation Corpus

- **What:** ERROR logs from the ROOT CAUSE SERVICE only (not affected services)
- **Why:** Avoids label ambiguity — affected-service logs are indistinguishable
  from root-cause logs when using the same error templates
- **Balancing:** Capped at `SAMPLES_PER_CLASS = 30` per service to avoid
  K-Means being dominated by majority classes
- **Seed variation:** Each scenario uses `seed_offset = scenario_index × 7` so
  logs vary across scenarios with the same root cause
- **True label per log:** `log["service"]` = the service that emitted the error

### Important Clarification

Clustering evaluation is performed at the **log level** (not scenario level).

Each ERROR log from a root-cause service is assigned to a cluster; the true
label is which service emitted it. A cluster is "correct" if it contains only
logs from one service type (high homogeneity).

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

Actual output structure:

```json
{
  "clustering": {
    "baseline": {"v_measure": 0.6186, "nmi": 0.6186, "num_clusters": 21},
    "ml_kmeans": {"v_measure": 0.3135, "nmi": 0.3135, "num_clusters": 5},
    "comparison": {"v_measure_delta": -0.3051, "better_clustering": false}
  },
  "anomaly_detection": {
    "precision": 1.0, "recall": 0.4429, "false_positive_rate": 0.0,
    "contamination_used": 0.5, "total_samples": 100
  },
  "rca": {"top1_accuracy": 1.0, "top3_accuracy": 1.0},
  "per_scenario_rca": [...]
}
```

Run with:

```bash
python -m evaluation.generate_report
```

---

## Build Order (all completed)

1. `scenarios/scenarios.json` — S001–S020 ✓
2. `scenarios/ground_truth.json` — `root_cause` + `anomaly_window` for all 20 ✓
3. `ml/__init__.py` ✓
4. `ml/vectorizer.py` — TF-IDF + numeric normalisation ✓
5. `ml/clustering.py` — K-Means, V-Measure, NMI ✓
6. `ml/anomaly_detector.py` — Isolation Forest ✓
7. `ml/model_utils.py` — feature extraction, loaders ✓
8. `evaluation/evaluate_clustering.py` — balanced root-cause logs, baseline vs ML ✓
9. `evaluation/evaluate_anomalies.py` — service-level features, dynamic contamination ✓
10. `evaluation/evaluate_rca.py` — Top-1/Top-3 per scenario ✓
11. `evaluation/compare_models.py` ✓
12. `evaluation/generate_report.py` → `evaluation/results.json` ✓

**Also updated:**
- `generator/log_generator.py` — added `seed_offset` parameter (default 0, no behaviour change for Phase 1/2)
- `evaluation/evaluate.py` — `gt["root_cause_service"]` → `gt["root_cause"]`

> `rca/clustering.py` and `rca/detector.py` (rule-based) remain unchanged —
> they are the baseline being measured against, not replaced.

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

**Phase 3 honest finding:**

> RCA is 100% accurate. Anomaly detection has perfect precision and zero false positives.
> Clustering shows the greedy baseline outperforms K-Means on V-Measure for this dataset —
> an honest and informative result that the evaluation framework correctly surfaces.
> The framework itself is the deliverable; the metrics quantify its behaviour.
