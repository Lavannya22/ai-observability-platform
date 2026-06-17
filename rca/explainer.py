FAILURE_TYPE_PHRASES = {
    "resource_exhaustion": "resource exhaustion",
    "job_failure": "a job failure",
    "data_corruption": "data corruption",
    "service_crash": "a service crash",
}

REMEDIATION = {
    "database": [
        "Scale up database connection pool limits.",
        "Identify and kill long-running queries.",
        "Check disk I/O utilisation and consider read replicas.",
    ],
    "metadata": [
        "Validate schema registry for recent changes.",
        "Re-run metadata sync job to restore consistency.",
        "Check database connectivity from the metadata service.",
    ],
    "etl": [
        "Review ETL job logs for the failing transformation step.",
        "Re-run the failed batch with corrected input data.",
        "Ensure metadata service is healthy before restarting ETL.",
    ],
    "analytics": [
        "Increase memory allocation for the analytics worker.",
        "Check for unbounded aggregation queries causing OOM.",
        "Restart the analytics service and monitor memory usage.",
    ],
    "reporting": [
        "Verify upstream analytics service is healthy.",
        "Retry failed report generation jobs.",
        "Check report scheduler for stuck jobs.",
    ],
}


def explain_incident(
    root_cause: str,
    affected_services: list[str],
    sample_logs: list[dict],
    failure_type: str = "unknown",
) -> str:
    failure_phrase = FAILURE_TYPE_PHRASES.get(failure_type, failure_type)
    affected_str = ", ".join(affected_services) if affected_services else "none"

    log_samples = "\n".join(
        f"  [{l['service']}] {l['message']}" for l in sample_logs[:5]
    )

    remediation_steps = REMEDIATION.get(root_cause, ["Investigate service logs manually."])
    remediation_str = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(remediation_steps))

    explanation = f"""INCIDENT SUMMARY
================
Root Cause Service : {root_cause}
Failure Type       : {failure_phrase}
Affected Services  : {affected_str}

WHAT HAPPENED
-------------
The {root_cause} service experienced {failure_phrase}. Because downstream services
depend on {root_cause}, failures cascaded to: {affected_str}.

EVIDENCE (sample log messages)
-------------------------------
{log_samples}

RECOMMENDED REMEDIATION
------------------------
{remediation_str}
"""
    return explanation.strip()
