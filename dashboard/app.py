import sys
import json
import time
from pathlib import Path

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from generator.log_generator import generate_logs
from rca.dependency_graph import build_graph
from rca.detector import detect_incidents
from rca.clustering import cluster_logs
from rca.engine import find_root_cause, rank_root_causes
from rca.explainer import explain_incident
from rca.evidence import generate_evidence
from rca.propagation import analyse_propagation

SCENARIOS_PATH = Path("scenarios/scenarios.json")
RESULTS_PATH   = Path("evaluation/results.json")


def load_scenarios():
    with open(SCENARIOS_PATH) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}


def load_results():
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH) as f:
            return json.load(f)
    return None


def run_pipeline(scenario: dict):
    logs      = generate_logs(scenario)
    incidents = detect_incidents(logs)
    clusters  = cluster_logs(logs)
    graph     = build_graph()

    incident_services = list({i["service"] for i in incidents})
    ranked     = rank_root_causes(incident_services, graph)
    rca_top3   = find_root_cause(incident_services, graph)
    root_cause = ranked[0]["service"] if ranked else incident_services[0]

    affected    = [s for s in incident_services if s != root_cause]
    explanation = explain_incident(
        root_cause=root_cause,
        affected_services=affected,
        sample_logs=[l for l in logs if l["level"] == "ERROR"][:10],
        failure_type=scenario["failure_type"],
    )
    evidence    = generate_evidence(root_cause, incident_services, logs, graph)
    propagation = analyse_propagation(root_cause, incident_services, graph)

    return logs, incidents, clusters, rca_top3, ranked, root_cause, explanation, evidence, propagation


def try_storage():
    try:
        from storage import repository
        return repository
    except ImportError:
        return None


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="AI Observability Platform", layout="wide")
st.title("AI Observability Platform")
st.caption("Phase 1 + Phase 2 + Phase 3 + Phase 4")

scenarios = load_scenarios()
tab1, tab2, tab3, tab4 = st.tabs([
    "Deterministic Analysis (Phase 1)",
    "Live Incidents (Phase 2)",
    "ML Evaluation (Phase 3 + 4)",
    "AI Assistant (Phase 5)",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Phase 1 pipeline + Phase 4 evidence
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
        st.markdown(f"- **Affected:** {', '.join(scenario['affected_services']) or 'none'}")

        run_clicked = st.button(
            "Run Pipeline", type="primary", use_container_width=True, key="p1_run"
        )

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
            logs, incidents, clusters, rca_top3, ranked, root_cause, explanation, evidence, propagation = (
                st.session_state.p1_results
            )
            ran_scenario = st.session_state.p1_ran_scenario

            if ran_scenario != scenario_id:
                st.warning(
                    f"Showing results for **{ran_scenario}**. "
                    f"Click Run Pipeline to run **{scenario_id}**."
                )

            error_logs = [l for l in logs if l["level"] == "ERROR"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Logs", len(logs))
            c2.metric("Error Logs", len(error_logs))
            c3.metric("Clusters", len(clusters))
            c4.metric("Services Affected", len(set(i["service"] for i in incidents)))

            st.divider()

            rca_col, evidence_col = st.columns([1, 2])

            with rca_col:
                st.subheader("Root Cause Analysis")
                st.markdown("**Confidence Ranking**")
                for i, c in enumerate(ranked, 1):
                    pct = f"{c['confidence']:.0%}" if c["confidence"] > 0 else "<1%"
                    if i == 1:
                        st.success(f"#{i} **{c['service']}** — {pct}")
                    else:
                        st.info(f"#{i} {c['service']} — {pct}")

                expected = scenarios[ran_scenario]["root_cause_service"]
                if root_cause == expected:
                    st.success(f"Correct: matches ground truth `{expected}`")
                else:
                    st.error(f"Expected `{expected}` — got `{root_cause}`")

                st.markdown("**Propagation Path**")
                st.code(" -> ".join(propagation["propagation_path"]))
                if propagation["match"]:
                    st.success("All services reachable via dependency graph")
                else:
                    st.error(f"Unexpected: {propagation['unmatched_services']}")

            with evidence_col:
                st.subheader("RCA Evidence")
                for line in evidence["evidence"]:
                    st.markdown(f"- {line}")

                with st.expander("Full Incident Explanation"):
                    st.code(explanation, language=None)

            st.divider()

            cluster_col, log_col = st.columns([1, 2])

            with cluster_col:
                st.subheader("Incident Clusters")
                noise_pct = 1 - (len(clusters) / len(error_logs)) if error_logs else 0
                st.caption(f"{len(error_logs)} errors -> {len(clusters)} clusters ({noise_pct:.1%} noise reduction)")
                st.dataframe(
                    pd.DataFrame([
                        {
                            "ID": c["cluster_id"],
                            "Size": c["size"],
                            "Services": ", ".join(c["services"]),
                            "Summary": c["summary"],
                        }
                        for c in clusters
                    ]),
                    use_container_width=True, hide_index=True,
                )

            with log_col:
                st.subheader("Log Stream")
                level_filter = st.multiselect(
                    "Filter by level",
                    options=["INFO", "WARNING", "ERROR"],
                    default=["ERROR"],
                    key="p1_level_filter",
                )
                filtered_logs = [l for l in logs if l["level"] in level_filter]
                st.dataframe(
                    pd.DataFrame(filtered_logs)[["timestamp", "service", "level", "message"]],
                    use_container_width=True, hide_index=True, height=300,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Phase 2 live incidents from PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    repository = try_storage()

    if repository is None:
        st.error("psycopg2 not installed. Run `pip install psycopg2-binary` and restart.")
    else:
        try:
            ctrl_col, _ = st.columns([1, 3])
            with ctrl_col:
                auto_refresh = st.toggle("Auto-refresh (10s)", value=False, key="p2_refresh")
                if st.button("Refresh Now", key="p2_refresh_btn"):
                    st.rerun()

            if auto_refresh:
                time.sleep(10)
                st.rerun()

            st.divider()

            st.subheader("Active Incidents")
            all_incidents = repository.get_all_incidents()
            active   = [i for i in all_incidents if i["status"] in ("OPEN", "DETECTING", "ACTIVE")]
            resolved = [i for i in all_incidents if i["status"] == "RESOLVED"]

            if not active:
                st.info("No active incidents. Start the producer and consumer to generate live data.")
            else:
                status_color = {"OPEN": "yellow", "DETECTING": "orange", "ACTIVE": "red"}
                for inc in active:
                    color = status_color.get(inc["status"], "grey")
                    with st.expander(
                        f"{inc['incident_id']} — :{color}[{inc['status']}] | "
                        f"Root cause: {inc['root_cause'] or 'detecting...'}"
                    ):
                        c1, c2 = st.columns(2)
                        c1.markdown(f"**Root Cause:** `{inc['root_cause'] or 'TBD'}`")
                        c2.markdown(f"**Affected:** {', '.join(inc['affected_services']) or 'TBD'}")
                        if inc["explanation"]:
                            st.code(inc["explanation"], language=None)

                        inc_logs = repository.get_logs_for_incident(inc["incident_id"])
                        if inc_logs:
                            st.caption(f"{len(inc_logs)} logs")
                            st.dataframe(
                                pd.DataFrame(inc_logs)[["timestamp", "service", "level", "message"]],
                                use_container_width=True, hide_index=True, height=180,
                            )

            st.divider()

            st.subheader("Incident History")
            if not resolved:
                st.info("No resolved incidents yet.")
            else:
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Incident ID": i["incident_id"],
                            "Root Cause": i["root_cause"] or "—",
                            "Affected Services": ", ".join(i["affected_services"]),
                            "Created": i["created_at"],
                            "Resolved": i["resolved_at"] or "—",
                        }
                        for i in resolved
                    ]),
                    use_container_width=True, hide_index=True,
                )

            st.divider()

            st.subheader("Log Search")
            query = st.text_input("Search log messages", placeholder="e.g. timeout, ETL, schema mismatch")
            if query:
                hits = repository.search_logs(query, limit=100)
                if hits:
                    st.caption(f"{len(hits)} results for '{query}'")
                    st.dataframe(
                        pd.DataFrame(hits)[["timestamp", "service", "level", "message", "incident_id"]],
                        use_container_width=True, hide_index=True, height=300,
                    )
                else:
                    st.info(f"No logs matching '{query}'")

            st.divider()

            st.subheader("Live Log Stream")
            lvl = st.multiselect(
                "Filter by level", ["INFO", "WARNING", "ERROR"], default=["ERROR"], key="p2_level_filter"
            )
            recent = [l for l in repository.get_recent_logs(limit=200) if l["level"] in lvl]
            if recent:
                st.dataframe(
                    pd.DataFrame(recent)[["timestamp", "service", "level", "message", "incident_id"]],
                    use_container_width=True, hide_index=True, height=300,
                )
            else:
                st.info("No logs in database yet.")

        except Exception as e:
            st.error(
                f"Cannot connect to PostgreSQL: {e}\n\n"
                "Make sure PostgreSQL is running and `configs/settings.yaml` has the correct credentials."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Phase 3 + Phase 4 ML evaluation
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    results = load_results()

    if results is None:
        st.warning("No results found. Run `python -m evaluation.generate_report` first.")
    else:
        st.subheader("Clustering — Three-Way Comparison")
        st.caption(
            "All three methods run on the same corpus: ERROR logs from root-cause services, "
            "balanced to 30 samples per service."
        )

        h = results.get("clustering_three_way", {})
        if h:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Method": "Greedy Baseline",
                        "V-Measure": h["greedy"]["v_measure"],
                        "NMI": h["greedy"]["nmi"],
                        "Clusters": h["greedy"]["num_clusters"],
                        "Noise Rate": "N/A",
                    },
                    {
                        "Method": "K-Means (Phase 3)",
                        "V-Measure": h["kmeans"]["v_measure"],
                        "NMI": h["kmeans"]["nmi"],
                        "Clusters": h["kmeans"]["num_clusters"],
                        "Noise Rate": "N/A",
                    },
                    {
                        "Method": "HDBSCAN (Phase 4)",
                        "V-Measure": h["hdbscan"]["v_measure"],
                        "NMI": h["hdbscan"]["nmi"],
                        "Clusters": h["hdbscan"]["num_clusters"],
                        "Noise Rate": f"{h['hdbscan'].get('noise_rate', 0):.1%}",
                    },
                ]),
                use_container_width=True, hide_index=True,
            )
            hdb_vm    = h["hdbscan"]["v_measure"]
            greedy_vm = h["greedy"]["v_measure"]
            if hdb_vm > greedy_vm:
                st.success(
                    f"HDBSCAN ({hdb_vm:.4f}) beats greedy baseline ({greedy_vm:.4f}) — "
                    f"sentence embeddings capture semantic similarity that TF-IDF misses."
                )
            else:
                st.info(f"Greedy baseline leads ({greedy_vm:.4f} vs {hdb_vm:.4f})")

        st.divider()

        anomaly_col, rca_col = st.columns(2)

        with anomaly_col:
            st.subheader("Anomaly Detection — Isolation Forest")
            a = results.get("anomaly_detection", {})
            d = results.get("anomaly_detection_detail", {})
            if a:
                m1, m2, m3 = st.columns(3)
                m1.metric("Precision", f"{a.get('precision', 0):.2f}")
                m2.metric("Recall",    f"{a.get('recall', 0):.2f}")
                m3.metric("FPR",       f"{a.get('false_positive_rate', 0):.2f}")
                if d:
                    st.caption(
                        f"TP={d.get('tp')}  FP={d.get('fp')}  "
                        f"FN={d.get('fn')}  TN={d.get('tn')}  "
                        f"(contamination={a.get('contamination_used')})"
                    )

        with rca_col:
            st.subheader("RCA Accuracy + MRR")
            r  = results.get("rca", {})
            rk = results.get("ranking", {})
            if r:
                m1, m2, m3 = st.columns(3)
                m1.metric("Top-1", f"{r.get('top1_accuracy', 0):.1%}")
                m2.metric("Top-3", f"{r.get('top3_accuracy', 0):.1%}")
                mrr = rk.get("mrr", 0) if rk else 0
                m3.metric("MRR",   f"{mrr:.4f}")
                if mrr >= 0.90:
                    st.success("MRR target met (>= 0.90)")

        st.divider()

        with st.expander("Per-Scenario Detail"):
            per_rca     = results.get("per_scenario_rca", [])
            per_ranking = results.get("per_scenario_ranking", [])
            if per_rca and per_ranking:
                rank_by_sid = {r["scenario_id"]: r for r in per_ranking}
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Scenario":  r["scenario_id"],
                            "Expected":  r["expected"],
                            "Predicted": r["predicted"] or "—",
                            "Top-1":     "correct" if r["top1"] else "wrong",
                            "Top-3":     "correct" if r["top3"] else "wrong",
                            "Rank":      rank_by_sid.get(r["scenario_id"], {}).get("rank", "—"),
                            "RR":        rank_by_sid.get(r["scenario_id"], {}).get("reciprocal_rank", 0),
                        }
                        for r in per_rca
                    ]),
                    use_container_width=True, hide_index=True,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Phase 5: AI Assistant (RAG)
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("AI Incident Investigation Assistant")
    st.caption(
        "Ask natural-language questions about any incident. "
        "Answers are grounded in incident evidence, propagation path, "
        "and similar historical incidents retrieved from OpenSearch."
    )

    # Check dependencies
    rag_ready = True
    try:
        from rag.answer_generator import generate_answer as _generate_answer
        from rag.grounding_validator import validate as _validate
    except ImportError:
        st.error("RAG components not available. Run `pip install anthropic`.")
        rag_ready = False

    opensearch_ready = True
    retrieved_incidents_cache = []
    try:
        from search.vector_search import search as _vector_search
    except ImportError:
        opensearch_ready = False

    if rag_ready:
        repo5 = try_storage()
        if repo5 is None:
            st.error("PostgreSQL not available — cannot load incidents.")
        else:
            try:
                all_inc = repo5.get_all_incidents()
                if not all_inc:
                    st.info(
                        "No incidents in the database yet. "
                        "Run the producer and consumer to generate incidents."
                    )
                else:
                    ctrl_col5, main_col5 = st.columns([1, 2])

                    with ctrl_col5:
                        st.markdown("### Select Incident")
                        inc_options = {
                            i["incident_id"]: (
                                f"{i['incident_id']} — "
                                f"{i['status']} | "
                                f"root: {i['root_cause'] or 'detecting...'}"
                            )
                            for i in all_inc
                        }
                        selected_iid = st.selectbox(
                            "Incident",
                            options=list(inc_options.keys()),
                            format_func=lambda k: inc_options[k],
                            key="p5_incident",
                        )
                        selected_incident = next(
                            i for i in all_inc if i["incident_id"] == selected_iid
                        )

                        st.markdown("**Incident Summary**")
                        st.markdown(f"- **Root Cause:** `{selected_incident['root_cause'] or 'TBD'}`")
                        st.markdown(
                            f"- **Affected:** "
                            f"{', '.join(selected_incident['affected_services']) or 'TBD'}"
                        )
                        propagation5 = selected_incident.get("propagation_path") or []
                        if propagation5:
                            st.markdown(f"- **Propagation:** `{' -> '.join(propagation5)}`")

                        if not opensearch_ready:
                            st.warning(
                                "OpenSearch not available — vector search disabled. "
                                "Answers will use incident data only."
                            )

                    with main_col5:
                        st.markdown("### Ask a Question")

                        suggested = [
                            "Why did this incident occur?",
                            f"Why did {selected_incident.get('affected_services', ['the service'])[0] if selected_incident.get('affected_services') else 'the service'} fail?",
                            "What is the failure propagation path?",
                            "Have we seen this type of incident before?",
                            "What action should I take to resolve this?",
                        ]
                        question = st.text_input(
                            "Question",
                            placeholder="e.g. Why did reporting fail?",
                            key="p5_question",
                        )
                        st.caption("Suggested: " + " | ".join(f"*{s}*" for s in suggested[:3]))

                        ask_clicked = st.button(
                            "Ask", type="primary", use_container_width=False, key="p5_ask"
                        )

                        if "p5_result" not in st.session_state:
                            st.session_state.p5_result = None

                        if ask_clicked and question.strip():
                            with st.spinner("Retrieving similar incidents and generating answer..."):
                                retrieved5 = []
                                if opensearch_ready:
                                    try:
                                        query_text = (
                                            f"{question} "
                                            f"{selected_incident.get('root_cause', '')} "
                                            f"{' '.join(selected_incident.get('affected_services', []))}"
                                        )
                                        retrieved5 = _vector_search(query_text, top_k=5)
                                    except Exception as e:
                                        st.warning(f"OpenSearch unavailable: {e}")

                                result5 = _generate_answer(
                                    question, selected_incident, retrieved5
                                )
                                st.session_state.p5_result = result5
                                st.session_state.p5_retrieved = retrieved5

                        if st.session_state.p5_result:
                            r5 = st.session_state.p5_result
                            retrieved5 = st.session_state.get("p5_retrieved", [])

                            st.divider()

                            # Answer
                            st.markdown("#### Answer")
                            st.markdown(r5["answer"])

                            # Grounding badge
                            grounding = r5["grounding"]
                            rate = grounding["hallucination_rate"]
                            if grounding["grounded"]:
                                st.success(
                                    f"Fully grounded — hallucination rate: {rate:.0%}"
                                )
                            else:
                                st.warning(
                                    f"Hallucination rate: {rate:.0%} | "
                                    f"{len(grounding['unsupported_claims'])} unsupported claim(s)"
                                )

                            llm_label = "claude-haiku-4-5" if r5.get("llm_used") else "rule-based fallback"
                            st.caption(f"Generated by: {llm_label}")

                            # Sources
                            if r5["sources"]:
                                st.markdown(
                                    "**Sources:** " + ", ".join(f"`{s}`" for s in r5["sources"])
                                )

                            # Similar incidents
                            if retrieved5:
                                with st.expander(f"Similar Historical Incidents ({len(retrieved5)})"):
                                    st.dataframe(
                                        pd.DataFrame([
                                            {
                                                "Incident ID": inc.get("incident_id", "?"),
                                                "Root Cause": inc.get("root_cause", "?"),
                                                "Affected": ", ".join(inc.get("affected_services") or []),
                                                "Summary": (inc.get("summary") or "")[:80],
                                                "Score": round(inc.get("_score", 0), 4),
                                            }
                                            for inc in retrieved5
                                        ]),
                                        use_container_width=True, hide_index=True,
                                    )

                            # Grounding detail
                            if not grounding["grounded"] and grounding["unsupported_claims"]:
                                with st.expander("Unsupported Claims (hallucination detail)"):
                                    for claim in grounding["unsupported_claims"]:
                                        st.markdown(f"- {claim}")

            except Exception as e:
                st.error(f"Cannot connect to PostgreSQL: {e}")
