import yaml
from collections import defaultdict


def detect_incidents(logs: list[dict], config_path: str = "configs/settings.yaml") -> list[dict]:
    """
    Rule-based incident detection: flag any service whose total ERROR count
    across all logs exceeds `error_threshold`.

    Window-based detection is intentionally skipped in Phase 1 — errors are
    generated in root-cause-first order, so a tail window would miss the
    originating service entirely.

    Returns a list of incident dicts, one per affected service.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    threshold = config["detection"]["error_threshold"]

    error_counts: dict[str, int] = defaultdict(int)
    for log in logs:
        if log["level"] == "ERROR":
            error_counts[log["service"]] += 1

    incidents = []
    for service, count in error_counts.items():
        if count >= threshold:
            incidents.append({
                "service": service,
                "error_count": count,
                "triggered_at": logs[-1]["timestamp"],
            })

    return incidents
