# Phase 2 — Real-Time Streaming & Persistence

## What Changed in Phase 2?

Phase 1 proved that the platform could **detect incidents and identify root causes** from a batch of logs. But in a real production system, logs don't arrive all at once — they stream in continuously, thousands per minute, from multiple services simultaneously.

Phase 2 answers the question:

> **Can the system ingest logs in real time, correlate related failures across services, and maintain incident state — without breaking the accuracy Phase 1 proved?**

The answer is yes.

---

## The Problem with Batch Processing

Phase 1 worked like this:

```
Load all logs → Run detection → Run RCA → Done
```

This works for testing, but production systems never "finish" producing logs. A real pipeline needs to:

- **Continuously ingest** logs as they arrive, not wait for a full batch
- **Decide in real time** which logs belong to which incident
- **Persist** that state so it survives restarts and can be queried later
- **Automatically resolve** incidents when the storm passes

Phase 2 adds all of this.

---

## What Was Built

### 1. Kafka Log Streaming

Logs are now streamed through **Apache Kafka** — a distributed message queue used by companies like LinkedIn, Uber, and Netflix to move billions of events per day.

A **producer** reads a scenario, generates logs, and publishes them to a Kafka topic at a controlled rate (default: ~1,000 logs/minute). A **consumer** reads from that topic in real time and processes each log as it arrives.

```
Producer → Kafka Topic ("logs") → Consumer → PostgreSQL
```

This decouples log generation from processing. The producer can run at full speed; the consumer processes at its own pace. No data is lost even if the consumer is temporarily slow.

### 2. PostgreSQL Persistence

All logs and incidents are now stored in **PostgreSQL** — a production-grade relational database.

Two tables:

**`logs`** — every log that flows through the system:
```
id | timestamp | service | level | message | scenario_id | incident_id
```

**`incidents`** — one row per detected incident, updated as it evolves:
```
incident_id | status | affected_services | root_cause | created_at | resolved_at | explanation | last_log_at
```

This makes logs **searchable and queryable** — you can find every `timeout` error across all services in the last hour with a single SQL query.

### 3. Incident Lifecycle Management

In Phase 1, an incident was a simple flag: "this service has too many errors." In Phase 2, incidents have a full lifecycle:

```
OPEN → DETECTING → ACTIVE → RESOLVED
```

- **OPEN** — first error arrives, incident created
- **DETECTING** — error count crosses the threshold, RCA begins
- **ACTIVE** — root cause identified, explanation stored
- **RESOLVED** — no new logs for 10 minutes, incident auto-closes

A background thread checks every 10 seconds and resolves any incident that has gone quiet.

### 4. Incident Merging (Graph-Based Correlation)

This is the most technically interesting part of Phase 2.

When a database fails, it triggers a cascade: metadata fails, then ETL, then analytics, then reporting. Without merging, the system would create 5 separate incidents — one per service. Each one would get its own (wrong) root cause.

The merge logic prevents this by using the **dependency graph** to decide whether a new error belongs to an existing incident:

```python
# If the failing service is graph-connected to any service already in the incident,
# attach it — don't create a new incident
if graph_related(new_service, incident.affected_services):
    attach to existing incident
else:
    create new incident
```

Graph connectivity is checked in **both directions** (ancestor and descendant), because in a real streaming system, errors don't always arrive in strict dependency order. ETL might log an error before the database error that caused it has been processed.

A **time window** (10 minutes) prevents unrelated failures hours apart from being incorrectly merged.

### 5. Wall-Clock Time vs. Simulation Time

One subtle but important engineering decision: the log generator produces logs with **fake timestamps** (`2025-01-15 09:00:00`) for simulation purposes. If the incident timeout logic used these fake timestamps, it would think every incident had been inactive for ~500 days — and resolve it immediately.

The fix: the consumer tracks `last_log_at` using **real wall-clock time** (`datetime.utcnow()`) — when the log was *received*, not when it was *created* in the simulation. This is the correct approach for any real-time system where log timestamps may be delayed, backdated, or out of order.

### 6. Dashboard Upgrade

The dashboard now has two tabs:

**Tab 1 — Deterministic Analysis (Phase 1):** Unchanged — run any scenario and see the full RCA pipeline output.

**Tab 2 — Live Incidents (Phase 2):** Shows live data from PostgreSQL:
- Active incidents with status, root cause, and affected services
- Incident log drilldown — click any incident to see its logs
- Incident history — resolved incidents with timestamps
- Log search — keyword search across all stored logs
- Live log stream — last 200 logs, filterable by level

---

## Engineering Decisions Worth Noting

**Why `confluent-kafka` instead of `kafka-python`?**
`kafka-python` has a compatibility bug with Python 3.13's `selectors` module. `confluent-kafka` is a C-extension-based client maintained by Confluent (the company behind Kafka) and has no such issues. Same Kafka, production-grade client.

**Why does the resolver re-read the config on every cycle?**
If the timeout was read once at startup, changing it would require restarting the consumer. By reading from the config file on each check cycle, the timeout can be adjusted live — no downtime.

**Why didn't `rca/detector.py` or `rca/clustering.py` need changes?**
Both functions were written in Phase 1 to operate on any list of logs. For streaming, the consumer simply passes incident-scoped logs instead of all logs. No code changes needed — the abstraction held.

---

## Results

| Criteria | Result |
|---|---|
| Throughput | ~1,000 logs/min (17 logs/sec sustained) |
| Message loss | 0% |
| RCA accuracy (all 4 scenarios) | 100% — preserved from Phase 1 |
| Incident merging | Cascade failures correctly merged into single incident |
| Auto-resolution | Incidents close after 10 min inactivity |

---

## Skills Demonstrated

### Event Streaming
- Produced and consumed real messages through **Apache Kafka**
- Controlled throughput with rate limiting (logs/sec)
- Handled consumer group offsets and partition assignment via `confluent-kafka`

### Database Engineering
- Designed a PostgreSQL schema for both time-series log data and mutable incident state
- Built a repository layer with parameterised queries (no SQL injection risk)
- Implemented `ILIKE` full-text search for log retrieval

### Distributed Systems Thinking
- Understood the difference between internal Docker networking (`kafka:9092`) and host-accessible listeners (`localhost:29092`)
- Handled the simulation-time vs wall-clock-time problem that would break any naively implemented streaming system
- Designed the incident merger to handle out-of-order message arrival

### Incident Management Systems
- Modelled incident lifecycle state machine (OPEN → DETECTING → ACTIVE → RESOLVED)
- Built graph-based correlation logic to prevent incident fragmentation
- Implemented time-windowed merging to avoid false correlations between unrelated failures

### Software Engineering
- Config-driven timeout (live reload without restart)
- Graceful shutdown on Ctrl+C (`consumer.close()`)
- Background thread for stale incident resolution
- Absolute path resolution so scripts run correctly from any working directory

---

## Technology Stack (Phase 2 Additions)

| Tool | Purpose |
|---|---|
| Apache Kafka | Log message queue and streaming backbone |
| confluent-kafka | Python Kafka client (Python 3.13 compatible) |
| PostgreSQL | Persistent storage for logs and incidents |
| psycopg2 | PostgreSQL adapter for Python |
| NetworkX | Graph connectivity checks for incident merging |

---

## How to Run

```bash
# 1. Start infrastructure (PostgreSQL + Kafka + ZooKeeper via Docker)
docker start obs-postgres zookeeper kafka

# 2. One-time database setup
python storage/setup_db.py

# 3. Terminal 1 — start consumer (keeps running)
python ingestion/consumer.py

# 4. Terminal 2 — stream a scenario
python ingestion/producer.py --scenario S001

# 5. Open dashboard
streamlit run dashboard/app.py
# Navigate to the "Live Incidents (Phase 2)" tab
```

---

## Phase 1 vs Phase 2

| | Phase 1 | Phase 2 |
|---|---|---|
| Log delivery | Batch (all at once) | Streaming (real time via Kafka) |
| Storage | JSON files on disk | PostgreSQL |
| Incident state | Single detection pass | Lifecycle (OPEN → RESOLVED) |
| Incident correlation | N/A | Graph-based merge across services |
| Dashboard data source | In-memory (session state) | PostgreSQL queries |
| Log search | No | Yes (SQL `ILIKE`) |
| RCA accuracy | 100% | 100% (preserved) |
