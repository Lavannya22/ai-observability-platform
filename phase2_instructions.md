# Phase 2 — Real-Time Streaming & Persistence (Final)

## Goal

Transform the Phase 1 batch pipeline into a real-time observability system while preserving:

* Deterministic evaluation
* RCA correctness
* Clustering quality
* Reproducibility

Phase 2 changes **how data flows**, not **how RCA works**.

---

## Success Criteria

### Streaming

* Kafka producer streams logs continuously
* Kafka consumer processes logs in real time
* PostgreSQL stores logs and incidents
* Dashboard updates automatically

### Incident Lifecycle

* Incidents open automatically
* Incidents accumulate logs while active
* Related failures are merged into the same incident
* Incidents resolve automatically after inactivity

### Evaluation

* Phase 1 deterministic mode still works
* All 4 scenarios still achieve correct Top-1 RCA

### Performance

* Sustain 1,000+ logs/minute
* End-to-end latency < 5 seconds
* 0% message loss

### Note

```text
Phase 2 target: 1,000 logs/minute
Phase 6 target: 10,000+ logs/minute
```

Phase 2 validates architecture.
Phase 6 validates scalability.

---

## Updated Project Structure

```text
ai-observability-platform/

├── ingestion/
│   ├── producer.py
│   └── consumer.py
│
├── storage/
│   ├── postgres.py
│   └── repository.py
│
├── scenarios/
├── generator/
├── rca/
├── evaluation/
├── dashboard/
├── configs/
├── data/
│
└── main.py
```

---

## Step 1 — Kafka Integration

### Producer

File:

```text
ingestion/producer.py
```

Responsibilities:

```text
Load scenario
Generate logs
Publish logs to Kafka
```

Example:

```python
producer.send("logs", log_record)
```

---

### Consumer

File:

```text
ingestion/consumer.py
```

Responsibilities:

```text
Read logs
Store logs
Update incidents
Trigger clustering
Trigger RCA
```

---

## Step 2 — PostgreSQL Storage

### logs

```sql
CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    service VARCHAR(100),
    level VARCHAR(20),
    message TEXT,
    scenario_id VARCHAR(20),
    incident_id VARCHAR(50)
);
```

---

### incidents

```sql
CREATE TABLE incidents (
    incident_id VARCHAR(50),
    status VARCHAR(20),
    root_cause VARCHAR(100),
    created_at TIMESTAMP,
    resolved_at TIMESTAMP,
    explanation TEXT
);
```

---

## Step 3 — Incident Lifecycle

### Problem

Phase 1 used:

```python
count_errors_across_all_logs()
```

Streaming never ends. Eventually every service triggers an incident.

### Solution

Every incident follows:

```text
OPEN
 ↓
DETECTING
 ↓
ACTIVE
 ↓
RESOLVED
```

**OPEN** — Potential issue detected.

**DETECTING** — Threshold crossed. Additional logs collected.

**ACTIVE** — Incident confirmed. Logs continue arriving. Clustering updates. RCA updates.

**RESOLVED** — No incident logs received for:

```yaml
incident:
  timeout_seconds: 30
```

Incident automatically closes.

---

## Step 4 — Incident Association & Merge Rules

This prevents incident fragmentation.

### Problem

Without merging:

```text
Database error
      ↓
Metadata error
      ↓
ETL error
```

creates:

```text
INC001
INC002
INC003
```

RCA loses propagation context.

### Desired Behavior

Create:

```text
INC001
 ├─ Database
 ├─ Metadata
 ├─ ETL
 └─ Analytics
```

One incident. One root cause.

---

### Rule 1 — Dependency Graph Check

Dependency graph:

```text
database → metadata → etl → analytics → reporting
```

When a new error arrives:

```python
service = incoming_log.service
```

Check all ACTIVE incidents. If the service is connected (in either direction —
ancestor or descendant) to services already inside the incident:

```text
Attach to existing incident
```

> **Note:** Reachability must be checked in both directions through the
> dependency graph (e.g. `nx.has_path()`), not just downstream. Errors may
> arrive out of strict propagation order under real streaming conditions.

#### Example

Current incident:

```text
INC001

Affected:
database
metadata
```

New error:

```text
ERROR ETL failed
```

Since `database → metadata → etl`, attach ETL logs to `INC001`.

---

### Rule 2 — Time Proximity Check

Related services should not merge forever.

Configuration:

```yaml
incident:
  merge_window_minutes: 10
```

Only merge if:

```python
time_difference <= merge_window
```

---

### Rule 3 — New Incident Creation

Create a new incident when:

**A. Service is unrelated**

```text
Database timeout
Reporting disk full
```

No dependency relationship → create `INC002`.

**B. Merge window expired**

```text
Database failure at 09:00
ETL failure at 15:00
```

→ create `INC002`.

---

### Assignment Algorithm

```python
def assign_incident(log):
    for incident in active_incidents:
        if within_merge_window(log, incident):
            if graph_related(
                log.service,
                incident.affected_services
            ):
                return incident.id

    return create_new_incident()
```

> **Testing note:** Write a unit test that feeds errors out of strict
> dependency order (e.g. `etl` arrives before `metadata`) and confirms they
> still merge correctly into the same incident.

---

## Step 5 — Detection Upgrade

Phase 1:

```python
count_errors_across_all_logs()
```

Phase 2:

```python
count_errors_within_active_incident()
```

Incident opens when:

```python
error_count >= threshold
```

inside the active incident.

---

## Step 6 — Streaming Clustering

Phase 1:

```text
Cluster entire batch
```

Phase 2:

```text
Cluster logs inside active incident
```

Workflow:

```text
Incident
   ↓
New log arrives
   ↓
Compare to clusters
   ↓
Assign cluster
   ↓
Update statistics
```

### Noise Reduction Metrics

**Global Noise Reduction** — used in README and project success criteria:

```text
1 - (total_clusters / total_logs)
```

**Incident Noise Reduction** — used internally:

```text
1 - (incident_clusters / incident_logs)
```

---

## Step 7 — Dashboard Upgrade

Dashboard now reads from PostgreSQL.

Views:

* **Live Logs** — real-time stream
* **Active Incidents** — current incidents
* **RCA Results** — root-cause predictions
* **Incident History** — resolved incidents

---

## Step 8 — Search

Simple PostgreSQL search.

```sql
SELECT *
FROM logs
WHERE message ILIKE '%timeout%';
```

Supported queries:

```text
database timeout
etl failure
schema mismatch
```

---

## Step 9 — Evaluation Framework

Two execution modes remain.

### Mode 1 — Deterministic Evaluation

```bash
python main.py --scenario S001
```

Used for: RCA accuracy, clustering quality, regression testing.

### Mode 2 — Streaming Demo

```bash
python ingestion/producer.py
python ingestion/consumer.py
```

Used for: throughput testing, latency testing, dashboard demonstration.

### Metrics

**Throughput**

```text
logs processed per minute
```

**Latency**

```text
log created
      ↓
incident detected
```

**Message Loss**

```text
generated_logs - stored_logs
```

Target: `0%`

---

## Step 10 — Configuration

Update `configs/settings.yaml`:

```yaml
kafka:
  topic: logs
  bootstrap_servers: localhost:9092

postgres:
  host: localhost
  port: 5432
  database: observability

incident:
  timeout_seconds: 30
  merge_window_minutes: 10
```

---

## Build Order

1. `storage/postgres.py`
2. `storage/repository.py`
3. SQL table creation (`logs`, `incidents`)
4. `ingestion/consumer.py` (lifecycle + merge logic)
5. `ingestion/producer.py`
6. Detection upgrade (`rca/detector.py`)
7. Streaming clustering upgrade (`rca/clustering.py`)
8. `evaluation/evaluate.py` — add throughput/latency/message-loss metrics
9. `configs/settings.yaml` updates
10. `dashboard/app.py` — PostgreSQL-backed views

> Storage comes first because the consumer depends on it. Lifecycle and merge
> logic should be unit tested before wiring up the live Kafka consumer loop.

---

## What NOT to do in Phase 2

Do NOT add:

* OpenSearch
* Sentence Transformers
* HDBSCAN
* LangGraph
* RAG
* AWS deployment

Keep the architecture focused on streaming and persistence.

---

## Deliverables

By the end of Phase 2 you should have:

* Kafka-based ingestion
* PostgreSQL persistence
* Incident lifecycle management
* Incident merging based on graph relationships
* Streaming detection
* Streaming clustering
* Searchable logs
* Live dashboard updates
* Deterministic evaluation preserved

---

## Mental Model

**Phase 1 proved:**

> Can we detect and explain incidents?

**Phase 2 proves:**

> Can we continuously ingest, store, correlate, merge, and investigate incidents in real time without breaking RCA accuracy?
