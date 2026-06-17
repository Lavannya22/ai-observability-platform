# Phase 1 — Project Overview for Recruiters

## What Is This Project?

This is an **AI-powered observability platform** — a system that watches over a simulated enterprise data pipeline, automatically detects when something goes wrong, figures out what caused it, and explains the problem in plain English.

Think of it as a junior version of tools like **Datadog, PagerDuty, or Splunk** — but built entirely from scratch, end-to-end, by one person.

---

## The Problem It Solves

In any production data platform, hundreds of services run simultaneously. When one service fails, it triggers failures in every service that depends on it. Within seconds, you can have **thousands of error logs flooding in from dozens of services at once**.

Without automation, an on-call engineer has to:
1. Manually read through thousands of logs
2. Figure out which errors are symptoms vs. the actual cause
3. Trace the failure back through service dependencies
4. Write up what happened and how to fix it

This typically takes **30–60 minutes per incident** — during which time the platform remains broken.

**This project automates that entire process in seconds.**

---

## What It Does (In Plain English)

Given a failure scenario, the platform:

1. **Generates realistic logs** — simulates what a real enterprise pipeline would produce during an incident (thousands of log lines across multiple services)

2. **Detects the incident** — identifies which services are experiencing abnormal error rates

3. **Groups related errors** — instead of treating 75 individual error messages as 75 separate alerts, it collapses them into a handful of meaningful groups (reducing alert noise by ~74%)

4. **Finds the root cause** — uses the known dependency structure between services to reason about which service most likely caused the cascade of failures

5. **Explains what happened** — produces a plain-English summary of the incident, what was affected, and what to do about it

6. **Shows it all on a dashboard** — an interactive web UI where you can run scenarios and explore results visually

---

## The System Being Monitored

A simulated 5-service data pipeline where each service depends on the one before it:

```
Database  →  Metadata  →  ETL  →  Analytics  →  Reporting
```

If the **Database** fails, the **Metadata** service can't connect to it, so it fails too. That causes **ETL** to fail, which breaks **Analytics**, which breaks **Reporting**. One failure cascades into five.

The platform's job is to detect all five failures, ignore the four that are just symptoms, and correctly identify the **Database** as the true root cause.

---

## Results

Every scenario was tested against a known ground truth. The platform got them all right:

| Scenario | What Failed | Platform's Answer | Correct? | Alert Noise Reduced |
|---|---|---|---|---|
| S001 — Database Overload | Database | Database | Yes | 74.7% |
| S002 — ETL Job Failure | ETL | ETL | Yes | 73.3% |
| S003 — Data Quality Issue | Metadata | Metadata | Yes | 75.0% |
| S004 — Analytics Crash | Analytics | Analytics | Yes | 73.3% |

**100% root cause accuracy. ~74% alert noise reduction across all scenarios.**

---

## Skills Demonstrated

### Data Engineering
- Designed a multi-service pipeline simulation with realistic log structures
- Built deterministic log generation (same input → same output, every time) — a key requirement for reproducible testing
- Managed data flow across multiple stages with structured JSON output at each step

### Machine Learning
- Applied **TF-IDF** (term frequency–inverse document frequency) to turn raw log messages into numerical vectors
- Used **cosine similarity** to measure how related two log messages are
- Built a clustering algorithm that groups semantically similar error logs without any labelled training data

### Graph Algorithms
- Modelled service dependencies as a **directed graph** using NetworkX
- Implemented **graph traversal** (descendants in a directed graph) to score which service caused the most downstream failures
- Identified and fixed a logical inversion bug in the scoring algorithm that would have produced wrong answers

### AI / NLP
- Built a structured **natural language generation** system that produces human-readable incident reports from structured data
- Designed the output to mirror what a senior engineer would write: root cause, narrative, evidence, remediation steps

### Software Engineering
- Clean modular architecture — each concern (detection, clustering, RCA, explanation) is a separate, testable module
- Config-driven design — thresholds, paths, and parameters live in a single YAML file, not hardcoded
- End-to-end evaluation framework that scores predictions against ground truth automatically

### Full-Stack / Product Thinking
- Built an interactive **Streamlit dashboard** with session state management, scenario switching, live metrics, and filtered log views
- Designed the UX so a non-technical user could run an investigation by clicking one button

---

## Technology Stack

| Tool | Purpose |
|---|---|
| Python | Core language |
| NetworkX | Service dependency graph and traversal |
| scikit-learn | TF-IDF vectorisation and cosine similarity |
| Streamlit | Interactive web dashboard |
| pandas | Data handling and table rendering |
| PyYAML | Configuration management |

---

## Why Phase 1 Is Deliberately Simple

Phase 1 is intentionally constrained — no distributed systems, no cloud services, no heavy ML models. The goal was to **prove the logic works** before adding complexity.

Each Phase 1 component has a direct upgrade path:

| Phase 1 (Done) | Future Phase |
|---|---|
| TF-IDF similarity | Sentence Transformer embeddings (semantic understanding) |
| Greedy threshold clustering | HDBSCAN (handles noise, variable cluster sizes) |
| Template-based explanation | RAG-powered LLM (context-aware, grounded in past incidents) |
| Batch log processing | Kafka streaming (real-time, 10K+ logs/minute) |
| Local file storage | OpenSearch vector database (scalable similarity search) |

The architecture was designed with these upgrades in mind — swapping a component doesn't require rewriting the system.

---

## How to Run It

```bash
# Install dependencies
pip install -r requirements.txt

# Run a scenario through the command line
python main.py --scenario S001

# Launch the interactive dashboard
streamlit run dashboard/app.py
```
