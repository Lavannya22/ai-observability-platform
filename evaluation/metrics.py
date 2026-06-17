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
