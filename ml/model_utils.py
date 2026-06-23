import re
import json
from collections import defaultdict
from datetime import datetime


def extract_latency_ms(message: str) -> float:
    """Parse the first integer followed by 'ms' from a log message. Returns 0 if not found."""
    match = re.search(r'(\d+)\s*ms', message)
    return float(match.group(1)) if match else 0.0


def extract_service_features(logs: list[dict], services: list[str]) -> dict[str, list[float]]:
    """
    Compute per-service feature vector:
        [error_rate, warning_rate, avg_latency_ms, retry_count]

    error_rate / warning_rate are counts (not per-minute) — sufficient for
    Isolation Forest since all scenarios have the same log count.
    """
    counts: dict[str, dict] = {
        s: {"errors": 0, "warnings": 0, "latencies": [], "retries": 0}
        for s in services
    }

    retry_pattern = re.compile(r'retry|retries|aborted after', re.IGNORECASE)

    for log in logs:
        svc = log["service"]
        if svc not in counts:
            continue
        level = log["level"]
        msg = log["message"]

        if level == "ERROR":
            counts[svc]["errors"] += 1
        elif level == "WARNING":
            counts[svc]["warnings"] += 1

        lat = extract_latency_ms(msg)
        if lat > 0:
            counts[svc]["latencies"].append(lat)

        if retry_pattern.search(msg):
            counts[svc]["retries"] += 1

    features = {}
    for svc in services:
        c = counts[svc]
        avg_lat = sum(c["latencies"]) / len(c["latencies"]) if c["latencies"] else 0.0
        features[svc] = [
            float(c["errors"]),
            float(c["warnings"]),
            avg_lat,
            float(c["retries"]),
        ]
    return features


def build_feature_matrix(
    scenarios: list[dict],
    logs_map: dict[str, list[dict]],
    services: list[str],
) -> tuple[list[list[float]], list[str], list[str]]:
    """
    Build feature matrix for Isolation Forest across all scenarios.

    Returns:
        X         — list of feature vectors (one per service per scenario)
        svc_labels — service name for each row
        gt_labels  — 'anomaly' or 'normal' for each row (ground truth)
    """
    X, svc_labels, gt_labels = [], [], []

    for scenario in scenarios:
        sid = scenario["scenario_id"]
        logs = logs_map.get(sid, [])
        anomalous = set([scenario["root_cause_service"]] + scenario["affected_services"])
        features = extract_service_features(logs, services)
        for svc in services:
            X.append(features[svc])
            svc_labels.append(svc)
            gt_labels.append("anomaly" if svc in anomalous else "normal")

    return X, svc_labels, gt_labels


def load_scenarios(path: str = "scenarios/scenarios.json") -> dict:
    with open(path) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}


def load_ground_truth(path: str = "scenarios/ground_truth.json") -> dict:
    with open(path) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}
