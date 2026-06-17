def rca_accuracy_at_k(candidates: list[dict], ground_truth_service: str, k: int = 1) -> bool:
    """True if ground_truth_service appears in the top-k RCA candidates."""
    top_k = [c["service"] for c in candidates[:k]]
    return ground_truth_service in top_k


def detection_hit(incidents: list[dict], ground_truth_services: list[str]) -> bool:
    """True if at least one detected incident service matches the ground truth affected set."""
    detected = {i["service"] for i in incidents}
    return bool(detected & set(ground_truth_services))


def cluster_noise_reduction(total_error_logs: int, num_clusters: int) -> float:
    """
    Ratio of error logs collapsed into clusters vs raw alert count.
    E.g. 100 error logs → 5 clusters = 95% reduction.
    """
    if total_error_logs == 0:
        return 0.0
    return round(1 - (num_clusters / total_error_logs), 4)


# ── Streaming metrics (Phase 2) ───────────────────────────────────────────────

def throughput(logs_processed: int, duration_seconds: float) -> float:
    """Logs processed per minute."""
    if duration_seconds <= 0:
        return 0.0
    return round((logs_processed / duration_seconds) * 60, 1)


def message_loss(logs_generated: int, logs_stored: int) -> dict:
    """Absolute and percentage message loss between producer and storage."""
    lost = logs_generated - logs_stored
    pct = round(lost / logs_generated * 100, 2) if logs_generated > 0 else 0.0
    return {"lost": lost, "loss_pct": pct}


def detection_latency(log_created_at: str, incident_detected_at: str) -> float:
    """Seconds between log creation and incident detection."""
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%S"
    try:
        t0 = datetime.fromisoformat(log_created_at)
        t1 = datetime.fromisoformat(incident_detected_at)
        return round((t1 - t0).total_seconds(), 3)
    except ValueError:
        return -1.0
