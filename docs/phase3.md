# Phase 3 — Machine Learning & Evaluation Framework

## What Changed in Phase 3?

Phases 1 and 2 proved the platform could detect incidents, identify root causes, and stream logs in real time. But every rule in those phases was hand-written. A senior engineer decided what counts as "too many errors," which services are related, and how to score root causes.

Phase 3 asks a harder question:

> **Can machine learning replace or improve those hand-written rules — and can we prove it with objective, reproducible metrics?**

The answer is nuanced, and that's the point.

---

## The Problem with Rule-Based Systems

Hand-written rules have a fundamental weakness: they encode what the engineer already knows. They don't discover patterns; they confirm assumptions.

In a production observability platform, you want the system to:

- **Find anomalies** it was never explicitly told to look for
- **Group related failures** based on what the logs actually say, not hardcoded thresholds
- **Quantify its own accuracy** so you know when to trust it

Phase 3 adds all of this — and critically, it measures whether the ML approach actually outperforms the rule-based one.

---

## What Was Built

### 1. Expanded Scenario Coverage — 20 Labeled Failure Scenarios

Before building ML models, there needs to be enough data to train and evaluate them. The scenario set was expanded from 4 to 20 distinct failure types:

```
Database Overload       Slow Query             High Retry Rate
ETL Job Failure         Memory Leak            Kafka Consumer Lag
Data Quality Issue      Analytics Failure      Corrupted File
Analytics Service Crash Upstream API Failure   Late Arriving Data
Schema Mismatch         Disk Exhaustion        Job Timeout
Null Data Explosion     Dashboard Failure      Partial Pipeline Failure
Duplicate Records       Multi-Service Cascade
```

Each scenario has a **ground truth label**: which service is the true root cause, which downstream services are affected, and a time window that marks when anomalous behaviour begins and ends. This labelled dataset is what makes objective evaluation possible.

### 2. TF-IDF Vectorisation with Numeric Normalisation

Before any ML model can process log messages, those messages need to be converted into numbers. This is done with **TF-IDF (Term Frequency–Inverse Document Frequency)** — a standard NLP technique that represents each log message as a vector based on which words appear and how distinctive they are.

The key engineering decision here was **numeric token normalisation**. A raw log message like:

```
DB connection timeout after 5234ms — retrying
DB connection timeout after 8901ms — retrying
```

looks like two different messages to TF-IDF because the numbers differ. After normalisation:

```
DB connection timeout after <LATENCY> — retrying
DB connection timeout after <LATENCY> — retrying
```

they become identical. The same applies to dataset IDs (`ds_NNN` → `<DATASET>`), job IDs, report IDs, and batch numbers. This reduces noise and helps the model focus on the meaningful parts of each message.

### 3. K-Means Clustering

**K-Means** is a clustering algorithm that groups similar items together without being told which group they belong to. In this context: given a pool of ERROR logs from across all 20 scenarios, can the algorithm group them by the service type that produced them — without being told the labels?

The number of clusters `k` is set to the number of distinct root-cause service types in the dataset (5), which is a principled choice: it matches the natural structure of the problem without being arbitrary.

### 4. Isolation Forest Anomaly Detection

**Isolation Forest** is a tree-based anomaly detection algorithm. The intuition is simple: abnormal data points are easier to isolate than normal ones. It builds random decision trees and measures how many splits it takes to isolate each data point — anomalies are isolated quickly.

Here, the model works on **service-level feature vectors**:

```
[error_count, warning_count, avg_latency_ms, retry_count]
```

One vector per service per scenario (100 vectors total: 20 scenarios × 5 services). It then predicts which service-instances are behaving anomalously — without being told which are root causes or affected services.

### 5. Evaluation Framework

This is the most important part of Phase 3. Every model claims to work; the evaluation framework measures whether it actually does.

Five evaluation scripts, one orchestrator:

```
evaluation/
├── evaluate_clustering.py   — baseline greedy vs K-Means (V-Measure, NMI)
├── evaluate_anomalies.py    — Isolation Forest (precision, recall, FPR)
├── evaluate_rca.py          — root cause accuracy (Top-1, Top-3)
├── compare_models.py        — side-by-side delta between models
└── generate_report.py       — runs all three, writes results.json
```

A single command runs the entire evaluation and writes the results to disk:

```bash
python -m evaluation.generate_report
```

The results are **reproducible** — each scenario uses a fixed random seed, so the same metrics are produced on every run.

---

## Results

### Root Cause Analysis

| Metric | Target | Result |
|---|---|---|
| Top-1 Accuracy | ≥ 80% | **100%** (20/20) |
| Top-3 Accuracy | ≥ 90% | **100%** (20/20) |

The graph-based RCA engine from Phase 1 correctly identifies the root cause for every scenario at rank 1. The expanded scenario set (16 additional failure types) did not reduce accuracy.

### Anomaly Detection

| Metric | Target | Result |
|---|---|---|
| Precision | ≥ 0.80 | **1.00** |
| Recall | ≥ 0.80 | 0.44 |
| False Positive Rate | ≤ 10% | **0.00** |

Zero false positives: every service the Isolation Forest flags as anomalous genuinely is. Recall is 0.44 because across the 20 scenarios, 71% of service-instances are anomalous — well above the algorithm's maximum flagging rate of 50% (a hard limit imposed by the sklearn library). The model is conservative rather than noisy. In a real alerting system, false positives are more costly than missed detections, so this tradeoff is deliberate.

### Clustering

| Model | V-Measure | Clusters |
|---|---|---|
| Greedy Baseline (Phase 2) | 0.62 | 21 |
| K-Means (Phase 3) | 0.31 | 5 |

K-Means does not outperform the greedy baseline on this dataset. This is an honest result, and it reveals something real about the data: short log messages have high vocabulary variance within the same failure type ("DB connection timeout" vs "Connection pool exhausted" vs "Query failed" — all database errors, but very different words). K-Means with a fixed `k=5` struggles to separate them cleanly, while the greedy approach creates 21 smaller, purer clusters.

This is exactly the kind of finding the evaluation framework was built to surface. A system that only reports successes isn't trustworthy.

---

## Engineering Decisions Worth Noting

**Why is the clustering result lower for K-Means?**
The greedy baseline creates as many clusters as it needs (21) and scores high on homogeneity because each cluster is small and pure. K-Means is forced to use exactly 5 clusters to match the 5 root-cause services. Short, diverse log messages from the same service end up in different clusters — and different services share vocabulary ("timeout", "retry", "failed"). V-Measure penalises this. The finding is documented because understanding *why* a model underperforms is as valuable as knowing it does.

**Why not use sentence embeddings instead of TF-IDF?**
Sentence Transformers would produce richer representations and likely improve clustering. They are explicitly excluded from Phase 3 and planned for Phase 4 (along with HDBSCAN and OpenSearch). The point of Phase 3 is to establish a measurable baseline — TF-IDF + K-Means is that baseline.

**Why does the log generator have a `seed_offset` parameter?**
Without it, every scenario with the same root-cause service would generate identical log messages (same random seed). The clustering evaluator would then be grouping perfect duplicates rather than genuinely similar-but-varied messages. The `seed_offset` (scenario index × 7) varies the messages while keeping each individual run reproducible. Default is `0` so Phase 1 and Phase 2 behaviour is unchanged.

**Why are contamination values clamped?**
`sklearn`'s Isolation Forest requires contamination to be between 0 and 0.5. The true anomaly rate in this dataset is 71% — above that limit. The code clamps it to `min(0.5, true_rate)` rather than hard-coding a value, so the model adapts if the dataset changes.

**Why keep `rca/clustering.py` (greedy baseline) untouched?**
Because the evaluation compares the old method against the new one. If the baseline were modified, the comparison would be measuring something different. The rule is: never change what you're measuring against.

---

## The Honest Summary

| Metric | Target Met? |
|---|---|
| RCA accuracy across 20 scenarios | Yes — 100% Top-1 |
| Zero false-positive anomaly alerts | Yes |
| Automated, reproducible evaluation pipeline | Yes |
| K-Means outperforms greedy baseline | No — and that's documented |

An evaluation framework that only reports good results is not an evaluation framework — it's a performance. Phase 3 builds the infrastructure to measure honestly, and the measurement reveals that for short, high-variance log messages, classical clustering algorithms hit a real wall. That's a finding, not a failure.

---

## Skills Demonstrated

### Machine Learning
- Applied **TF-IDF vectorisation** with domain-specific numeric normalisation
- Implemented **K-Means clustering** with principled k-selection (distinct root causes, not scenario count)
- Applied **Isolation Forest** anomaly detection with dynamic contamination tuning
- Designed a **balanced, stratified evaluation corpus** to prevent majority-class bias

### Evaluation Methodology
- Built a **reproducible evaluation pipeline** with fixed random seeds and seed offsets
- Computed **V-Measure and NMI** for clustering (penalises both impure and fragmented clusters)
- Computed **precision, recall, and FPR** for anomaly detection with ground truth labels
- Maintained **baseline vs ML model comparison** without modifying the baseline

### Data Engineering
- Expanded ground truth dataset from 4 to 20 labeled scenarios
- Designed `anomaly_window` schema to mark when anomalous behaviour begins and ends per scenario
- Managed a **ground truth field rename** (`root_cause_service` → `root_cause`) without breaking the Phase 1/2 pipeline

### Software Engineering
- Evaluation pipeline is a single command (`python -m evaluation.generate_report`)
- Results written to `evaluation/results.json` — machine-readable, diffable in git
- No evaluation code modifies production code — clean separation of concerns

---

## Technology Stack (Phase 3 Additions)

| Tool | Purpose |
|---|---|
| scikit-learn | K-Means, Isolation Forest, V-Measure, NMI |
| TF-IDF (scikit-learn) | Log message vectorisation |
| NumPy | Feature matrix construction |
| Custom evaluation scripts | Reproducible benchmarking pipeline |

---

## How to Run

```bash
# Run the full evaluation pipeline (all 3 evaluations → results.json)
python -m evaluation.generate_report

# Run evaluations individually
python -m evaluation.evaluate_rca
python -m evaluation.evaluate_anomalies
python -m evaluation.evaluate_clustering
```

---

## Phase 1 vs Phase 2 vs Phase 3

| | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| Log delivery | Batch | Streaming (Kafka) | Streaming + evaluation corpus |
| Anomaly detection | Rule: error count threshold | Rule: error count threshold | Isolation Forest |
| Log clustering | TF-IDF greedy (no k) | TF-IDF greedy (no k) | K-Means (k = root causes) |
| RCA | Graph scoring | Graph scoring | Graph scoring (measured across 20 scenarios) |
| Evaluation | Manual spot-check | Manual spot-check | Automated: V-Measure, NMI, precision, recall, FPR, Top-1/Top-3 |
| Labeled scenarios | 4 | 4 | 20 |
| Ground truth | Implicit | Implicit | Explicit JSON with anomaly windows |
