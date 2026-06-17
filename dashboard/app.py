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


def try_import_storage():
    """Return repository module if PostgreSQL deps are available, else None."""
    try:
        from storage import repository
        return repository
    except ImportError:
        return None


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="AI Observability Platform", layout="wide")
st.title("AI Observability Platform")
st.caption("Phase 1 + Phase 2 — Incident Intelligence Pipeline")

scenarios = load_scenarios()
tab1, tab2 = st.tabs(["Deterministic Analysis (Phase 1)", "Live Incidents (Phase 2)"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Phase 1 deterministic pipeline
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    col_sidebar, col_main = st.columns([1, 3])

    with col_sidebar:
        st.markdown("### Controls")
        scenario_id = st.selectbox(
            "Select Scenario",
            options=list(scenarios.keys()),
            format_func=lambda sid: f"{sid} — {scenarios[sid]['name']}",
            key="p1_scenario",
        )
        scenario = scenarios[scenario_id]

        st.markdown("**Scenario Info**")
        st.markdown(f"- **Type:** {scenario['failure_type']}")
        st.markdown(f"- **Root Cause:** `{scenario['root_cause_service']}`")
        st.markdown(f"- **Affected:** {', '.join(scenario['affected_services'])}")

        run_clicked = st.button(
            "Run Pipeline", type="primary", use_container_width=True, key="p1_run"
        )

    # Session state for Phase 1 results
    if "p1_results" not in st.session_state:
        st.session_state.p1_results = None
        st.session_state.p1_ran_scenario = None

    if run_clicked:
        with st.spinner(f"Running pipeline for {scenario_id}..."):
            results = run_pipeline(scenario)
        st.session_state.p1_results = results
        st.session_state.p1_ran_scenario = scenario_id
        st.success(f"Pipeline complete for {scenario_id}!")

    with col_main:
        if st.session_state.p1_results is None:
            st.info("Select a scenario and click **Run Pipeline** to begin.")
        else:
            logs, incidents, clusters, rca_candidates, root_cause, explanation = (
                st.session_state.p1_results
            )
            ran_scenario = st.session_state.p1_ran_scenario

            if ran_scenario != scenario_id:
                st.warning(
                    f"Showing results for **{ran_scenario}**. "
                    f"Click Run Pipeline to run **{scenario_id}**."
                )

            # Summary cards
            error_logs = [l for l in logs if l["level"] == "ERROR"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Logs", len(logs))
            c2.metric("Error Logs", len(error_logs))
            c3.metric("Clusters", len(clusters))
            c4.metric("Services Affected", len(incidents))

            st.divider()

            # RCA + Explanation
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
                if root_cause == expected:
                    st.success(f"Predicted matches expected: **{expected}**")
                else:
                    st.error(f"Expected: **{expected}** | Predicted: **{root_cause}**")

            with explain_col:
                st.markdown("**Incident Explanation**")
                st.code(explanation, language=None)

            st.divider()

            # Clusters
            st.subheader("Incident Clusters")
            noise_reduction = 1 - (len(clusters) / len(error_logs)) if error_logs else 0
            st.caption(
                f"{len(error_logs)} error logs -> {len(clusters)} clusters "
                f"({noise_reduction:.1%} noise reduction)"
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
            st.dataframe(
                pd.DataFrame(cluster_rows), use_container_width=True, hide_index=True
            )

            st.divider()

            # Log stream
            st.subheader("Log Stream")
            level_filter = st.multiselect(
                "Filter by level",
                options=["INFO", "WARNING", "ERROR"],
                default=["ERROR"],
                key="p1_level_filter",
            )
            filtered_logs = [l for l in logs if l["level"] in level_filter]
            log_df = pd.DataFrame(filtered_logs)[["timestamp", "service", "level", "message"]]
            st.dataframe(log_df, use_container_width=True, hide_index=True, height=300)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Phase 2 live incidents from PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    repository = try_import_storage()

    if repository is None:
        st.error("psycopg2 not installed. Run `pip install psycopg2-binary` and restart.")
    else:
        try:
            # ── Controls ──────────────────────────────────────────────────────
            ctrl_col, _ = st.columns([1, 3])
            with ctrl_col:
                auto_refresh = st.toggle("Auto-refresh (10s)", value=False, key="p2_refresh")
                if st.button("Refresh Now", key="p2_refresh_btn"):
                    st.rerun()

            if auto_refresh:
                import time
                time.sleep(10)
                st.rerun()

            st.divider()

            # ── Active Incidents ───────────────────────────────────────────────
            st.subheader("Active Incidents")
            all_incidents = repository.get_all_incidents()
            active = [i for i in all_incidents if i["status"] in ("OPEN", "DETECTING", "ACTIVE")]

            if not active:
                st.info("No active incidents. Start the producer and consumer to generate live data.")
            else:
                status_color = {"OPEN": "🟡", "DETECTING": "🟠", "ACTIVE": "🔴"}
                for inc in active:
                    icon = status_color.get(inc["status"], "⚪")
                    with st.expander(
                        f"{icon} {inc['incident_id']} — {inc['status']} | "
                        f"Root cause: {inc['root_cause'] or 'detecting...'}"
                    ):
                        c1, c2, c3 = st.columns(3)
                        c1.markdown(f"**Status:** {inc['status']}")
                        c2.markdown(f"**Root Cause:** `{inc['root_cause'] or 'TBD'}`")
                        c3.markdown(
                            f"**Affected:** {', '.join(inc['affected_services']) or 'TBD'}"
                        )
                        if inc["explanation"]:
                            st.code(inc["explanation"], language=None)

                        incident_logs = repository.get_logs_for_incident(inc["incident_id"])
                        if incident_logs:
                            st.markdown(f"**{len(incident_logs)} logs in this incident**")
                            inc_df = pd.DataFrame(incident_logs)[
                                ["timestamp", "service", "level", "message"]
                            ]
                            st.dataframe(inc_df, use_container_width=True, hide_index=True, height=200)

            st.divider()

            # ── Incident History ───────────────────────────────────────────────
            st.subheader("Incident History")
            resolved = [i for i in all_incidents if i["status"] == "RESOLVED"]
            if not resolved:
                st.info("No resolved incidents yet.")
            else:
                history_rows = [
                    {
                        "Incident ID": i["incident_id"],
                        "Root Cause": i["root_cause"] or "—",
                        "Affected Services": ", ".join(i["affected_services"]),
                        "Created": i["created_at"],
                        "Resolved": i["resolved_at"] or "—",
                    }
                    for i in resolved
                ]
                st.dataframe(
                    pd.DataFrame(history_rows), use_container_width=True, hide_index=True
                )

            st.divider()

            # ── Log Search ────────────────────────────────────────────────────
            st.subheader("Log Search")
            query = st.text_input("Search log messages", placeholder="e.g. timeout, ETL, schema mismatch")
            if query:
                results = repository.search_logs(query, limit=100)
                if results:
                    st.caption(f"{len(results)} results for '{query}'")
                    search_df = pd.DataFrame(results)[
                        ["timestamp", "service", "level", "message", "incident_id"]
                    ]
                    st.dataframe(search_df, use_container_width=True, hide_index=True, height=300)
                else:
                    st.info(f"No logs matching '{query}'")

            st.divider()

            # ── Live Log Stream ───────────────────────────────────────────────
            st.subheader("Live Log Stream")
            level_filter_p2 = st.multiselect(
                "Filter by level",
                options=["INFO", "WARNING", "ERROR"],
                default=["ERROR"],
                key="p2_level_filter",
            )
            recent_logs = repository.get_recent_logs(limit=200)
            filtered = [l for l in recent_logs if l["level"] in level_filter_p2]
            if filtered:
                live_df = pd.DataFrame(filtered)[
                    ["timestamp", "service", "level", "message", "incident_id"]
                ]
                st.dataframe(live_df, use_container_width=True, hide_index=True, height=300)
            else:
                st.info("No logs in database yet.")

        except Exception as e:
            st.error(
                f"Cannot connect to PostgreSQL: {e}\n\n"
                "Make sure PostgreSQL is running and `configs/settings.yaml` has the correct credentials."
        )
