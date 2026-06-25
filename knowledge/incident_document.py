"""Convert a resolved incident record into a searchable knowledge document."""
from __future__ import annotations
import json


def build_document(incident: dict) -> dict:
    """
    Build a knowledge document from a resolved incident.

    Input: dict from repository.get_all_incidents()
    Output: knowledge document ready for indexing.
    """
    confidence = _parse_json_field(incident.get("confidence_scores"), default=[])
    confidence_ranking = {
        entry["service"]: entry["confidence"]
        for entry in confidence
        if isinstance(entry, dict)
    }

    evidence = _parse_json_field(incident.get("evidence"), default=[])
    propagation = _parse_json_field(incident.get("propagation_path"), default=[])
    affected = incident.get("affected_services") or []
    root_cause = incident.get("root_cause") or ""

    summary = _build_summary(root_cause, affected, evidence, propagation)

    return {
        "incident_id":        incident["incident_id"],
        "root_cause":         root_cause,
        "affected_services":  affected,
        "propagation_path":   propagation,
        "confidence_ranking": confidence_ranking,
        "evidence":           evidence,
        "summary":            summary,
        "created_at":         str(incident.get("created_at") or ""),
    }


def _parse_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _build_summary(
    root_cause: str,
    affected: list[str],
    evidence: list[str],
    propagation: list[str],
) -> str:
    if not root_cause:
        return "Unknown failure with no identified root cause."

    downstream = [s for s in affected if s != root_cause]
    parts = []

    if downstream:
        parts.append(
            f"{root_cause.capitalize()} failure caused cascading errors "
            f"across {', '.join(downstream)}."
        )
    else:
        parts.append(f"{root_cause.capitalize()} failure with no downstream cascade.")

    if propagation and len(propagation) > 1:
        parts.append(f"Propagation path: {' -> '.join(propagation)}.")

    if evidence:
        parts.append(evidence[0])

    return " ".join(parts)
