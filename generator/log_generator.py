import json
import random
import yaml
from datetime import datetime, timedelta
from pathlib import Path


NORMAL_TEMPLATES = {
    "database": [
        "Query executed successfully in {ms}ms",
        "Connection established from {service}",
        "Index scan completed on table {table}",
        "Transaction committed successfully",
        "Checkpoint written to disk",
    ],
    "metadata": [
        "Schema validation passed for dataset {ds}",
        "Metadata record updated for {ds}",
        "Cache refreshed for schema registry",
        "Lineage graph updated",
        "Metadata sync completed in {ms}ms",
    ],
    "etl": [
        "ETL job {job} started",
        "Batch {batch} processed: {rows} rows",
        "Transformation step completed for {ds}",
        "ETL job {job} finished successfully",
        "Data loaded into staging in {ms}ms",
    ],
    "analytics": [
        "Aggregation query completed in {ms}ms",
        "Report {report} generated successfully",
        "Analytics pipeline started for {ds}",
        "Model scoring completed: {rows} records",
        "Dashboard cache refreshed",
    ],
    "reporting": [
        "Report {report} delivered to {user}",
        "Scheduled report triggered",
        "Export completed: {rows} rows",
        "PDF rendered in {ms}ms",
        "Report subscription processed",
    ],
}

ERROR_TEMPLATES = {
    "database": [
        "DB connection timeout after {ms}ms",
        "Query latency high: {ms}ms exceeds threshold",
        "Connection pool exhausted: 0 connections available",
        "Transaction rolled back due to deadlock",
        "Disk I/O saturation detected",
    ],
    "metadata": [
        "Schema mismatch detected for dataset {ds}",
        "Invalid data format in metadata record {ds}",
        "Missing required fields in schema for {ds}",
        "Metadata service failed to reach database",
        "Cache invalidation failed",
    ],
    "etl": [
        "ETL job {job} crashed unexpectedly",
        "Data transformation error on batch {batch}",
        "Null pointer in pipeline at step {step}",
        "ETL failed to fetch metadata for {ds}",
        "Batch {batch} aborted after {retries} retries",
    ],
    "analytics": [
        "Out of memory error during aggregation",
        "Segmentation fault in analytics worker",
        "Analytics service terminated unexpectedly",
        "Failed to read ETL output for {ds}",
        "Query timeout after {ms}ms",
    ],
    "reporting": [
        "Report {report} generation failed",
        "Analytics data unavailable for report {report}",
        "Export failed: upstream data missing",
        "Report delivery timeout for {user}",
        "Scheduled report {report} aborted",
    ],
}


def _fill(template: str) -> str:
    return template.format(
        ms=random.randint(100, 9999),
        service=random.choice(["metadata", "etl", "analytics"]),
        table=random.choice(["events", "users", "transactions", "metrics"]),
        ds=f"ds_{random.randint(1, 50):03d}",
        job=f"job_{random.randint(100, 999)}",
        batch=random.randint(1, 200),
        rows=random.randint(1000, 500000),
        report=f"rpt_{random.randint(1, 99):02d}",
        user=f"user_{random.randint(1, 20):02d}",
        step=random.randint(1, 10),
        retries=random.randint(1, 5),
    )


def generate_logs(
    scenario: dict,
    config_path: str = "configs/settings.yaml",
    seed_offset: int = 0,
) -> list[dict]:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    seed = config["log_generator"]["seed"] + seed_offset
    normal_count = config["log_generator"]["normal_logs_per_service"]
    error_count = config["log_generator"]["error_logs_per_service"]
    all_services = config["pipeline"]["services"]

    random.seed(seed)

    root_cause = scenario["root_cause_service"]
    affected = scenario["affected_services"]

    base_time = datetime(2025, 1, 15, 9, 0, 0)
    logs = []
    tick = 0

    def make_log(service, level, message):
        nonlocal tick
        ts = base_time + timedelta(seconds=tick)
        tick += 1
        return {
            "timestamp": ts.isoformat(),
            "service": service,
            "level": level,
            "message": message,
            "scenario_id": scenario["scenario_id"],
        }

    # Normal background logs for all services
    for service in all_services:
        for _ in range(normal_count):
            msg = _fill(random.choice(NORMAL_TEMPLATES[service]))
            logs.append(make_log(service, "INFO", msg))

    # Inject root cause errors first
    for _ in range(error_count):
        msg = _fill(random.choice(ERROR_TEMPLATES[root_cause]))
        logs.append(make_log(root_cause, "ERROR", msg))

    # Propagate downstream failures in dependency order
    for service in affected:
        for _ in range(error_count):
            msg = _fill(random.choice(ERROR_TEMPLATES[service]))
            logs.append(make_log(service, "ERROR", msg))

    # Sort by timestamp so logs appear in chronological order
    logs.sort(key=lambda x: x["timestamp"])
    return logs


def save_logs(logs: list[dict], scenario_id: str, output_dir: str = "data/raw_logs"):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = Path(output_dir) / f"{scenario_id}.json"
    with open(path, "w") as f:
        json.dump(logs, f, indent=2)
    return str(path)
