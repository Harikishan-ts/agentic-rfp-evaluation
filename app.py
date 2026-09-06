import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from database import initialize_database, seed_criteria, load_active_criteria, get_supplier_results
from orchestrator import create_rfp_run

st.set_page_config(page_title="Agentic RFP Evaluation", page_icon="📊", layout="wide")

initialize_database()
seed_criteria()


def load_latest_saved_run():
    from database import get_connection

    conn = get_connection()
    row = conn.execute("""
        SELECT rfp_run_id FROM rfp_runs
        WHERE status = 'COMPLETED'
        ORDER BY created_at DESC LIMIT 1
    """).fetchone()
    conn.close()
    if not row:
        return None

    rfp_run_id = row[0]
    suppliers = []
    for row in get_supplier_results(rfp_run_id):
        supplier = dict(row)
        try:
            supplier["result"] = json.loads(supplier["result_json"])
        except (TypeError, json.JSONDecodeError):
            supplier["result"] = {}
        supplier.update(supplier["result"])
        suppliers.append(supplier)
    return {"rfp_run_id": rfp_run_id, "suppliers": suppliers}


if "last_run" not in st.session_state:
    st.session_state["last_run"] = load_latest_saved_run()


def save_uploaded_file(uploaded_file):
    suffix = Path(uploaded_file.name).suffix or ".pdf"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp.write(uploaded_file.getbuffer())
        return temp.name
    finally:
        temp.close()


st.title("📊 Agentic AI + RFP Evaluation")
st.caption("LLM-assisted supplier evaluation with deterministic scoring, peer benchmarking, ranking, and SQLite persistence.")

st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Criteria", "Supplier Input", "Leaderboard", "Run Details"])

if page == "Criteria":
    st.header("Active Evaluation Criteria")
    criteria = load_active_criteria()
    if not criteria:
        st.warning("No active criteria found.")
    else:
        df = pd.DataFrame(criteria)[["criterion_id", "name", "description", "weight", "max_score", "is_active"]]
        df.columns = ["ID", "Criterion", "Description", "Weight (%)", "Max Score", "Active"]
        st.dataframe(df, use_container_width=True, hide_index=True)
        total_weight = df["Weight (%)"].sum()
        st.metric("Total Active Weight", f"{total_weight:.1f}%")
        if abs(total_weight - 100.0) < 0.001:
            st.success("✓ Active criterion weights total 100%.")
        else:
            st.error("Active criterion weights must total 100%.")

elif page == "Supplier Input":
    st.header("Supplier Input")
    st.write("Upload multiple supplier RFP PDFs and provide the required supplier metadata.")

    uploaded_files = st.file_uploader("Upload supplier RFP PDFs", type=["pdf"], accept_multiple_files=True)
    supplier_records = []

    if uploaded_files:
        st.subheader("Supplier Metadata")
        for i, uploaded_file in enumerate(uploaded_files):
            st.markdown(f"### Supplier {i + 1}: {uploaded_file.name}")
            default_name = Path(uploaded_file.name).stem.replace("_RFP", "").replace("_", " ")
            supplier_name = st.text_input("Supplier Name", value=default_name, key=f"name_{i}")
            submission_date = st.date_input("Submission Date", key=f"date_{i}")
            experience_rating = st.number_input("Historical Experience Rating", min_value=0.0, max_value=10.0, value=5.0, step=0.5, key=f"experience_{i}")
            supplier_records.append({
                "supplier_name": supplier_name.strip(),
                "submission_date": submission_date.isoformat(),
                "experience_rating": experience_rating,
                "uploaded_file": uploaded_file,
            })
            st.divider()

    if supplier_records:
        st.subheader("Ready to Evaluate")
        preview = pd.DataFrame([{
            "Supplier": s["supplier_name"],
            "Submission Date": s["submission_date"],
            "Experience": s["experience_rating"],
            "PDF": s["uploaded_file"].name,
        } for s in supplier_records])
        st.dataframe(preview, use_container_width=True, hide_index=True)

        names = [s["supplier_name"].casefold() for s in supplier_records]
        if any(not n for n in names):
            st.error("Every supplier must have a name.")
        elif len(set(names)) != len(names):
            st.error("Supplier names must be unique.")
        elif st.button("🚀 Evaluate All Suppliers", type="primary"):
            if not os.getenv("OPENROUTER_API_KEY"):
                try:
                    secret_key = st.secrets.get("OPENROUTER_API_KEY")
                except Exception:
                    secret_key = None
                if not secret_key:
                    st.error("OPENROUTER_API_KEY is not configured. Add it to local .env or Streamlit Cloud Secrets.")
                    st.stop()

            temp_paths = []
            suppliers = []
            try:
                for supplier in supplier_records:
                    pdf_path = save_uploaded_file(supplier["uploaded_file"])
                    temp_paths.append(pdf_path)
                    suppliers.append({
                        "supplier_name": supplier["supplier_name"],
                        "submission_date": supplier["submission_date"],
                        "experience_rating": supplier["experience_rating"],
                        "pdf_path": pdf_path,
                    })

                with st.spinner("Evaluating supplier proposals..."):
                    result = create_rfp_run(suppliers)
                st.session_state["last_run"] = result
                st.success(f"Evaluation completed! Run ID: {result['rfp_run_id']}")
                st.info("Go to Leaderboard or Run Details to view the results.")
            except Exception as exc:
                st.error(f"Evaluation failed: {exc}")
            finally:
                for path in temp_paths:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

elif page == "Leaderboard":
    st.header("Supplier Leaderboard")
    last_run = st.session_state.get("last_run")
    if last_run:
        st.success(f"Current Run: {last_run['rfp_run_id']}")
        rows = [{
            "Rank": s["final_rank"],
            "Supplier": s["supplier_name"],
            "Absolute Score": s["absolute_score"],
            "PPI": s["ppi"],
            "Submission Date": s["submission_date"],
            "Experience": s["experience_rating"],
        } for s in last_run["suppliers"]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download Results JSON", data=json.dumps(last_run, indent=2), file_name=f"{last_run['rfp_run_id']}.json", mime="application/json")
    else:
        st.info("No completed run is available yet. Run an evaluation from Supplier Input.")

elif page == "Run Details":
    st.header("Run Details")
    last_run = st.session_state.get("last_run")
    if not last_run:
        st.info("No completed run is available yet.")
    else:
        st.write(f"**RFP Run ID:** {last_run['rfp_run_id']}")
        st.download_button("⬇️ Download Complete Run JSON", data=json.dumps(last_run, indent=2), file_name=f"{last_run['rfp_run_id']}.json", mime="application/json")
        st.caption("Ranking order: higher PPI → earlier submission date → higher historical experience → supplier name ascending.")

        for supplier in last_run["suppliers"]:
            st.subheader(f"{supplier['final_rank']}. {supplier['supplier_name']}")
            col1, col2, col3 = st.columns(3)
            col1.metric("Absolute Score", f"{supplier['absolute_score']:.2f}")
            col2.metric("PPI", f"{supplier['ppi']:.2f}%")
            col3.metric("Experience", f"{supplier['experience_rating']:.1f}/10")

            if supplier.get("overall_summary"):
                st.write("**Overall Summary:**", supplier["overall_summary"])
            if supplier.get("risks"):
                st.write("**Risks:**")
                for risk in supplier["risks"]:
                    st.write(f"• {risk}")

            details = [{
                "Criterion": c["name"], "Score": c["score"], "Max": c["max_score"],
                "Weight (%)": c["weight"], "Benchmark": c["benchmark"], "Gap": c["gap"],
                "Relative (%)": c["relative_performance"],
            } for c in supplier["criteria"]]
            st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)

            for criterion in supplier["criteria"]:
                with st.expander(f"Evidence — {criterion['name']}"):
                    st.write("**Justification:**")
                    st.write(criterion["justification"] or "No justification returned.")
                    st.write("**Supporting Evidence:**")
                    if criterion["evidence"]:
                        for evidence in criterion["evidence"]:
                            st.write(f"• {evidence}")
                    else:
                        st.write("No supporting evidence returned.")

            if supplier.get("warnings"):
                st.warning("Validation warnings:")
                for warning in supplier["warnings"]:
                    st.write(f"⚠️ {warning}")
