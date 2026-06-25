from __future__ import annotations


def build_prompt(
    question: str,
    current_incident: dict,
    retrieved_incidents: list[dict],
) -> str:
    return f"""You are an incident investigation assistant for an observability platform.
Answer the engineer's question using only the incident data provided below.
Do not mention CPU usage, memory metrics, disk I/O, network latency, deployments,
Kubernetes, or any information not present in the incident data.

Question:
{question}

Current Incident:
{_format_incident(current_incident)}

Historical Similar Incidents:
{_format_retrieved(retrieved_incidents)}

Instructions:
- Reference specific evidence bullets when available.
- Cite the propagation path to explain how the failure spread.
- If a historical incident is similar, cite its incident ID.
- End with one actionable recommendation grounded in the evidence."""


def _format_incident(incident: dict) -> str:
    lines = [
        f"Incident ID : {incident.get('incident_id', 'unknown')}",
        f"Status      : {incident.get('status', 'unknown')}",
        f"Root Cause  : {incident.get('root_cause') or 'not yet determined'}",
        f"Affected    : {', '.join(incident.get('affected_services') or [])}",
    ]

    propagation = incident.get("propagation_path") or []
    if propagation:
        lines.append(f"Propagation : {' -> '.join(propagation)}")

    confidence = incident.get("confidence_scores") or []
    if confidence:
        ranking = ", ".join(
            f"{c['service']} ({c['confidence']:.0%})"
            for c in confidence
            if isinstance(c, dict)
        )
        lines.append(f"Confidence  : {ranking}")

    evidence = incident.get("evidence") or []
    if evidence:
        lines.append("Evidence:")
        for ev in evidence:
            lines.append(f"  - {ev}")

    return "\n".join(lines)


def _format_retrieved(incidents: list[dict]) -> str:
    if not incidents:
        return "No similar historical incidents found."
    parts = []
    for i, inc in enumerate(incidents, 1):
        header = (
            f"[{i}] {inc.get('incident_id', '?')} | "
            f"Root Cause: {inc.get('root_cause', '?')} | "
            f"Affected: {', '.join(inc.get('affected_services') or [])}"
        )
        parts.append(header)
        summary = inc.get("summary")
        if summary:
            parts.append(f"     {summary}")
    return "\n".join(parts)
