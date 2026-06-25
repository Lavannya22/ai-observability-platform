"""
RAG answer generator.

Calls the Anthropic API (claude-haiku-4-5-20251001) when ANTHROPIC_API_KEY is set.
Falls back to a rule-based answer when the key is absent or the package is missing.
"""
from __future__ import annotations
import os

from rag.prompt_builder import build_prompt
from rag.grounding_validator import validate

_LLM_AVAILABLE = False
_client = None
_MODEL = "claude-haiku-4-5-20251001"

try:
    import anthropic as _anthropic
    _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if _api_key:
        _client = _anthropic.Anthropic(api_key=_api_key)
        _LLM_AVAILABLE = True
except ImportError:
    pass


def generate_answer(
    question: str,
    current_incident: dict,
    retrieved_incidents: list[dict],
) -> dict:
    """
    Build prompt -> call LLM (or fallback) -> validate grounding.

    Returns:
        {
            "answer": str,
            "grounding": {"grounded": bool, "hallucination_rate": float, ...},
            "sources": [incident_id, ...],
            "llm_used": bool,
        }
    """
    prompt = build_prompt(question, current_incident, retrieved_incidents)

    if _LLM_AVAILABLE and _client is not None:
        try:
            message = _client.messages.create(
                model=_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = message.content[0].text
            llm_used = True
        except Exception as e:
            answer = _fallback_answer(question, current_incident, retrieved_incidents)
            llm_used = False
            print(f"[RAG] LLM call failed ({e}), using fallback")
    else:
        answer = _fallback_answer(question, current_incident, retrieved_incidents)
        llm_used = False

    grounding = validate(answer, current_incident, retrieved_incidents)
    sources = [
        inc["incident_id"]
        for inc in retrieved_incidents
        if inc.get("incident_id")
    ]

    return {
        "answer": answer,
        "grounding": grounding,
        "sources": sources,
        "llm_used": llm_used,
    }


def _fallback_answer(question: str, incident: dict, retrieved: list[dict]) -> str:
    root = incident.get("root_cause") or "an unknown service"
    affected_list = incident.get("affected_services") or []
    affected = ", ".join(s for s in affected_list if s != root)
    propagation = incident.get("propagation_path") or []
    propagation_str = " -> ".join(propagation)
    evidence = incident.get("evidence") or []
    confidence = incident.get("confidence_scores") or []
    similar = next(
        (inc["incident_id"] for inc in retrieved if inc.get("incident_id")), None
    )
    history = f" A similar failure was previously observed in {similar}." if similar else ""

    q = question.lower()

    # "What is the confidence?" / "How sure?" — check BEFORE "why" to avoid "cause" false match
    if any(kw in q for kw in ["confident", "confidence", "certain", "sure", "probability", "likely"]):
        if confidence:
            ranking = ", ".join(
                f"{c['service']} ({c['confidence']:.0%})"
                for c in confidence
                if isinstance(c, dict)
            )
            return (
                f"Root cause confidence ranking: {ranking}. "
                f"'{root}' is ranked #1 with the highest downstream impact score. "
                f"Confidence is derived from the number of downstream services each candidate explains via graph traversal."
            )
        return f"No confidence scores recorded. Root cause identified as '{root}'."

    # "Why did X fail?" / "Why did this incident occur?"
    if any(kw in q for kw in ["why", "what caused", "occur", "happen", "triggered"]):
        ev_text = " ".join(evidence[:2]) if evidence else ""
        return (
            f"This incident was caused by a failure in '{root}'. "
            f"{ev_text} "
            f"The failure cascaded downstream to: {affected}. "
            f"{history} "
            f"Recommended action: investigate '{root}' error logs and its upstream dependencies."
        ).strip()

    # "What is the propagation path?" / "How did it spread?"
    if any(kw in q for kw in ["propagat", "spread", "path", "chain", "cascade"]):
        if propagation:
            return (
                f"The failure originated at '{root}' and propagated downstream as follows: "
                f"{propagation_str}. "
                f"Each service in the chain depends on the service before it, so a failure "
                f"at '{root}' caused errors in all dependent services."
                f"{history}"
            )
        return f"No propagation path was recorded for this incident. Root cause: '{root}'."

    # "Have we seen this before?" / "Historical?" / "Similar?"
    if any(kw in q for kw in ["before", "similar", "historical", "seen", "previous", "past"]):
        if retrieved:
            summaries = [
                f"{inc.get('incident_id', '?')} (root cause: {inc.get('root_cause', '?')})"
                for inc in retrieved[:3]
            ]
            return (
                f"Yes — similar incidents have been observed: {', '.join(summaries)}. "
                f"All share the same root cause pattern: '{root}' failure cascading to downstream services. "
                f"Reviewing those incidents may help identify whether this is a recurring issue."
            )
        return (
            f"No similar historical incidents were found in the knowledge store. "
            f"This may be the first recorded occurrence of a '{root}' failure with this propagation pattern."
        )

    # "What action?" / "How to resolve?" / "What should I do?"
    if any(kw in q for kw in ["action", "resolve", "fix", "should", "recommend", "how to", "steps"]):
        ev_last = evidence[-1] if evidence else ""
        return (
            f"To resolve this incident: "
            f"(1) Investigate '{root}' — check its error logs and resource usage. "
            f"(2) Verify the dependency chain: {propagation_str}. "
            f"(3) Restore '{root}' first; downstream services ({affected}) should recover automatically. "
            f"{ev_last} "
            f"{'Review ' + similar + ' for a prior resolution approach.' if similar else ''}"
        ).strip()

    # Default — general incident summary
    ev_text = evidence[0] if evidence else "No evidence recorded."
    return (
        f"Incident summary: root cause is '{root}', affecting {affected}. "
        f"Propagation path: {propagation_str}. "
        f"{ev_text} "
        f"{history} "
        f"Recommended action: investigate '{root}' error logs and service dependencies."
    ).strip()
