import sys
import json
from pathlib import Path

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from generator.log_generator import generate_logs
from rca.dependency_graph import build_graph
from rca.detector import detect_incidents
from rca.clustering import cluster_logs
from rca.engine import find_root_cause
from rca.explainer import explain_incident

SCENARIOS_PATH = Path("scenarios/scenarios.json")


def load_scenarios():
    with open(SCENARIOS_PATH) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}


def run_pipeline(scenario: dict):
    logs = generate_logs(scenario)
    incidents = detect_incidents(logs)
    clusters = cluster_logs(logs)
    graph = build_graph()
    incident_services = [i["service"] for i in incidents]
    rca_candidates = find_root_cause(incident_services, graph)
    root_cause = rca_candidates[0]["service"]
    downstream = [i["service"] for i in incidents if i["service"] != root_cause]
    explanation = explain_incident(
        root_cause=root_cause,
        affected_services=downstream,
        sample_logs=[l for l in logs if l["level"] == "ERROR"][:10],
        failure_type=scenario["failure_type"],
    )
    return logs, incidents, clusters, rca_candidates, root_cause, explanation


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="AI Observability Platform", layout="wide")
st.title("AI Observability Platform")
st.caption("Phase 1 MVP — Deterministic Incident Intelligence Pipeline")

scenarios = load_scenarios()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Controls")
scenario_id = st.sidebar.selectbox(
    "Select Scenario",
    options=list(scenarios.keys()),
    format_func=lambda sid: f"{sid} — {scenarios[sid]['name']}",
)
scenario = scenarios[scenario_id]

st.sidebar.markdown("**Scenario Info**")
st.sidebar.markdown(f"- **Type:** {scenario['failure_type']}")
st.sidebar.markdown(f"- **Root Cause:** `{scenario['root_cause_service']}`")
st.sidebar.markdown(f"- **Affected:** {', '.join(scenario['affected_services'])}")

run_clicked = st.sidebar.button("Run Pipeline", type="primary", use_container_width=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
    st.session_state.ran_scenario = None

if run_clicked:
    with st.spinner(f"Running pipeline for {scenario_id}..."):
        results = run_pipeline(scenario)
    st.session_state.results = results
    st.session_state.ran_scenario = scenario_id
    st.success(f"Pipeline complete for {scenario_id}!")

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.results is None:
    st.info("Select a scenario from the sidebar and click **Run Pipeline** to begin.")
    st.stop()

logs, incidents, clusters, rca_candidates, root_cause, explanation = st.session_state.results
ran_scenario = st.session_state.ran_scenario

if ran_scenario != scenario_id:
    st.warning(f"Showing results for **{ran_scenario}**. Click Run Pipeline to run **{scenario_id}**.")

# ── Summary Cards ─────────────────────────────────────────────────────────────
error_logs = [l for l in logs if l["level"] == "ERROR"]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Logs", len(logs))
col2.metric("Error Logs", len(error_logs))
col3.metric("Clusters", len(clusters))
col4.metric("Services Affected", len(incidents))

st.divider()

# ── Root Cause Analysis ───────────────────────────────────────────────────────
st.subheader("Root Cause Analysis")
rca_col, explain_col = st.columns([1, 2])

with rca_col:
    st.markdown("**Top-3 RCA Candidates**")
    for rank, c in enumerate(rca_candidates, 1):
        label = f"#{rank} {c['service']}"
        if rank == 1:
            st.success(f"{label} — confidence {c['confidence']:.0%}")
        else:
            st.info(f"{label} — confidence {c['confidence']:.0%}")

    st.markdown("**Ground Truth**")
    expected = scenarios[ran_scenario]["root_cause_service"]
    match = root_cause == expected
    if match:
        st.success(f"Predicted matches expected: **{expected}**")
    else:
        st.error(f"Expected: **{expected}** | Predicted: **{root_cause}**")

with explain_col:
    st.markdown("**Incident Explanation**")
    st.code(explanation, language=None)

st.divider()

# ── Incident Clusters ─────────────────────────────────────────────────────────
st.subheader("Incident Clusters")
noise_reduction = 1 - (len(clusters) / len(error_logs)) if error_logs else 0
st.caption(
    f"{len(error_logs)} error logs collapsed into {len(clusters)} clusters "
    f"— {noise_reduction:.1%} noise reduction"
)

cluster_rows = [
    {
        "Cluster ID": c["cluster_id"],
        "Size": c["size"],
        "Services": ", ".join(c["services"]),
        "Representative Message": c["summary"],
    }
    for c in clusters
]
st.dataframe(pd.DataFrame(cluster_rows), use_container_width=True, hide_index=True)

st.divider()

# ── Raw Logs ──────────────────────────────────────────────────────────────────
st.subheader("Log Stream")
level_filter = st.multiselect(
    "Filter by level",
    options=["INFO", "WARNING", "ERROR"],
    default=["ERROR"],
)
filtered_logs = [l for l in logs if l["level"] in level_filter]
log_df = pd.DataFrame(filtered_logs)[["timestamp", "service", "level", "message"]]
st.dataframe(log_df, use_container_width=True, hide_index=True, height=300)
