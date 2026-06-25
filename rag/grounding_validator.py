"""
Deterministic hallucination validator.

Checks every sentence in an LLM answer against known facts from:
  - the current incident (root cause, affected services, evidence, propagation path)
  - retrieved historical incidents (incident IDs, root causes)
  - the controlled service vocabulary

No second LLM call — this is entirely rule-based.
"""
from __future__ import annotations
import re

CONTROLLED_SERVICES = {"database", "metadata", "etl", "analytics", "reporting"}

ALLOWED_VOCABULARY = {
    "error", "errors", "logs", "log", "failure", "failed", "fail",
    "service", "services", "incident", "incidents", "downstream", "upstream",
    "propagation", "propagate", "dependency", "dependencies", "reachable",
    "confidence", "affected", "cascade", "cascading", "timeout", "connection",
    "retry", "retrying", "warning", "warnings", "similar", "resembles",
    "caused", "impacted", "detected", "identified", "observed", "reported",
    "investigate", "check", "review", "utilization", "usage", "resource",
    "recommended", "action", "based", "evidence", "grounded", "ranked",
    "root", "cause", "path", "chain", "origin", "first", "second",
}

HALLUCINATION_PATTERNS = [
    r"\bCPU\s*(usage|utilization|load|spike)?\b",
    r"\bmemory\s*(usage|pressure|leak|heap)?\b",
    r"\bdisk\s*(I/O|usage|space|exhaustion)?\b",
    r"\bnetwork\s*(latency|bandwidth|congestion)?\b",
    r"\bP\d{2}\b",
    r"\bpercentile\b",
    r"\btraffic\s*spike\b",
    r"\bdeployment\b",
    r"\bDNS\b",
    r"\bload\s*balancer\b",
    r"\bKubernetes\b",
    r"\bcontainer\b",
    r"\bpod\b",
    r"\bthread\s*pool\b",
    r"\bGC\s*(pause|pressure)?\b",
]


def validate(
    answer: str,
    current_incident: dict,
    retrieved_incidents: list[dict],
) -> dict:
    """
    Validate every sentence in the answer against known facts.

    Returns:
        {
            "grounded": bool,
            "total_claims": int,
            "unsupported_claims": [str],
            "hallucination_rate": float,
        }
    """
    sentences = [s.strip() for s in re.split(r"[.!?\n]", answer) if len(s.strip()) > 10]
    known_facts = _build_fact_set(current_incident, retrieved_incidents)
    unsupported = []

    for sentence in sentences:
        if _contains_hallucination(sentence):
            unsupported.append(sentence)
        elif not _is_supported(sentence, known_facts):
            unsupported.append(sentence)

    total = len(sentences)
    rate = round(len(unsupported) / total, 4) if total > 0 else 0.0

    return {
        "grounded": len(unsupported) == 0,
        "total_claims": total,
        "unsupported_claims": unsupported,
        "hallucination_rate": rate,
    }


def _build_fact_set(incident: dict, retrieved: list[dict]) -> set[str]:
    facts: set[str] = set(CONTROLLED_SERVICES) | ALLOWED_VOCABULARY

    if incident.get("root_cause"):
        facts.add(incident["root_cause"].lower())
    for svc in (incident.get("affected_services") or []):
        facts.add(svc.lower())
    for svc in (incident.get("propagation_path") or []):
        facts.add(svc.lower())
    for ev in (incident.get("evidence") or []):
        if isinstance(ev, str):
            facts.update(w.lower() for w in re.findall(r"[a-zA-Z]+", ev))

    for inc in retrieved:
        if inc.get("incident_id"):
            facts.add(inc["incident_id"].lower())
        if inc.get("root_cause"):
            facts.add(inc["root_cause"].lower())
        for svc in (inc.get("affected_services") or []):
            facts.add(svc.lower())

    return facts


def _contains_hallucination(sentence: str) -> bool:
    for pattern in HALLUCINATION_PATTERNS:
        if re.search(pattern, sentence, re.IGNORECASE):
            return True
    return False


def _is_supported(sentence: str, facts: set[str]) -> bool:
    # Check that any specific service or incident names mentioned are known facts
    lower = sentence.lower()

    # Extract tokens that look like service names or incident IDs (specific identifiers)
    identifiers = re.findall(r"\b(INC-[A-Z0-9]+|[a-z]{4,12})\b", lower)
    unknown_identifiers = [
        w for w in identifiers
        if w not in facts and w not in _COMMON_ENGLISH and len(w) >= 6
    ]
    # Allow up to 2 unknown identifiers (generous threshold for general English)
    return len(unknown_identifiers) <= 2


# Common English words that are never facts but are never hallucinations either
_COMMON_ENGLISH = {
    "which", "their", "there", "these", "those", "where", "about", "after",
    "while", "since", "until", "during", "because", "caused", "though",
    "should", "would", "could", "might", "other", "first", "second", "third",
    "having", "shows", "means", "being", "found", "known", "based", "along",
    "across", "through", "between", "within", "without", "toward", "before",
    "below", "above", "under", "further", "still", "again", "already",
    "likely", "failed", "errors", "error", "failure", "failures", "impacted",
    "triggered", "detected", "observed", "indicates", "identified", "reported",
    "recommended", "investigate", "review", "check", "utilization", "usage",
    "resource", "action", "grounded", "evidence", "similar", "pattern",
    "historical", "generated", "producing", "causing", "cascading", "downstream",
    "upstream", "service", "services", "incident", "incidents", "affected",
    "propagation", "propagated", "dependency", "dependencies", "reachable",
    "confidence", "ranked", "ranking", "origin", "source", "please", "ensure",
    "however", "therefore", "although", "specifically", "additionally",
    "furthermore", "following", "indicating", "suggesting", "consistent",
}
