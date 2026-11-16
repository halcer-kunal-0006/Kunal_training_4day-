"""Internal ticket-data dashboard (Streamlit UI).

This file contains widgets, session state and layout only. Every rule about
what valid data is, how it is cleaned and how metrics are computed lives in
``ticket_pipeline`` and is reached through ``ticket_dashboard.service``.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st

from ticket_dashboard import (
    MAX_UPLOAD_MB,
    DashboardResult,
    cleaned_tickets_frame,
    issue_counts_frame,
    priority_counts_frame,
    process_upload,
    quality_frame,
    resolution_time_frame,
)
from ticket_pipeline import DuplicatePolicy, TicketPipelineError, configure_logging
from ticket_pipeline.config import REQUIRED_COLUMNS

SAMPLE_PATH = Path(__file__).resolve().parent / "data" / "tickets.csv"
POLICY_LABELS = {
    DuplicatePolicy.KEEP_FIRST: "Keep first, report later copies",
    DuplicatePolicy.RAISE: "Reject the file if any ticket ID repeats",
}

# ---- Session state -----------------------------------------------------------
# result      DashboardResult | None  what the page currently shows
# error       str | None              last user-fixable error, shown above everything
# source_key  str | None              hash of the processed bytes + policy; a rerun
#                                     with the same input does not reprocess
# uploader_v  int                     bumped by "Clear" to give the uploader a new
#                                     key, which is the supported way to empty it
DEFAULTS: dict[str, object] = {"result": None, "error": None, "source_key": None, "uploader_v": 0}


def init_state() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)


def run_processing(name: str, data: bytes, policy: DuplicatePolicy) -> None:
    """Call the service and store either the result or the error, never both."""
    key = f"{hashlib.sha256(data).hexdigest()}:{policy.value}"
    if key == st.session_state.source_key and st.session_state.result is not None:
        st.session_state.error = None
        return  # same file, same options: keep the existing result
    try:
        result = process_upload(name, data, policy)
    except TicketPipelineError as exc:  # expected, user-fixable problems only
        st.session_state.update(result=None, error=str(exc), source_key=None)
        return
    st.session_state.update(result=result, error=None, source_key=key)


def on_process() -> None:
    uploaded = st.session_state.get(f"uploader_{st.session_state.uploader_v}")
    if uploaded is None:
        message = "No file selected. Choose a CSV file, then press Process."
        st.session_state.update(result=None, error=message, source_key=None)
        return
    run_processing(uploaded.name, uploaded.getvalue(), st.session_state.policy)


def on_load_sample() -> None:
    run_processing(SAMPLE_PATH.name, SAMPLE_PATH.read_bytes(), st.session_state.policy)


def on_clear() -> None:
    st.session_state.update(result=None, error=None, source_key=None)
    st.session_state.uploader_v += 1


# ---- Layout ------------------------------------------------------------------


def sidebar() -> None:
    with st.sidebar:
        st.header("Data source")
        with st.form("upload_form"):
            # No ``type=["csv"]`` here on purpose: Streamlit enforces it by raising
            # StreamlitAPIException (a traceback, not a message). The service
            # checks the extension instead and explains the problem.
            st.file_uploader(
                f"Ticket CSV (max {MAX_UPLOAD_MB} MB)",
                key=f"uploader_{st.session_state.uploader_v}",
            )
            st.selectbox(
                "Duplicate ticket IDs",
                options=list(POLICY_LABELS),
                format_func=POLICY_LABELS.__getitem__,
                key="policy",
            )
            # Both submit buttons live in the form so each one uses the policy
            # currently selected, not the one from the previous submission.
            st.form_submit_button("Process", type="primary", key="process", on_click=on_process)
            st.form_submit_button("Load sample data", key="load_sample", on_click=on_load_sample)
        st.button("Clear", key="clear", on_click=on_clear)


def empty_state() -> None:
    st.info(
        "Upload a ticket CSV in the sidebar and press **Process**, "
        "or press **Load sample data** to try the dashboard."
    )
    st.markdown("**Required columns** (extra columns are ignored):")
    st.code(", ".join(REQUIRED_COLUMNS), language=None)


def preview_tab(result: DashboardResult) -> None:
    preview = result.preview
    rows, cols = preview.shape
    c1, c2 = st.columns(2)
    c1.metric("Rows", rows)
    c2.metric("Columns", cols)
    st.subheader("Columns and inferred types")
    st.dataframe(preview.dtypes, hide_index=True)
    st.subheader(f"First {len(preview.head)} rows (raw, before cleaning)")
    st.dataframe(preview.head, hide_index=True)


def analytics_tab(result: DashboardResult) -> None:
    analytics = result.analytics
    rating = analytics["average_customer_rating"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Clean tickets", result.report.cleaned_rows)
    c2.metric("Unresolved tickets", analytics["unresolved_ticket_count"])
    c3.metric("Average rating", "n/a" if rating is None else f"{rating:.2f}")

    st.subheader("Tickets by priority")
    priorities = priority_counts_frame(analytics)
    st.bar_chart(priorities, x="priority", y="tickets")
    st.dataframe(priorities, hide_index=True)

    st.subheader("Resolution time by category")
    resolution = resolution_time_frame(analytics)
    st.bar_chart(resolution, x="category", y="avg_resolution_time_hours")
    st.dataframe(resolution, hide_index=True)


def quality_tab(result: DashboardResult) -> None:
    report = result.report
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Source rows", report.source_rows)
    c2.metric("Invalid records", report.invalid_record_count)
    c3.metric("Dropped (no ID)", report.rows_dropped_missing_ticket_id)
    c4.metric("Duplicates removed", report.duplicate_rows_removed)
    if report.duplicate_ticket_ids:
        st.write("Duplicated ticket IDs:", ", ".join(report.duplicate_ticket_ids))
    st.subheader("Missing and invalid values per column")
    st.dataframe(quality_frame(report), hide_index=True)
    st.subheader("Issues found")
    issues = issue_counts_frame(report)
    if issues.empty:
        st.success("No data-quality issues found.")
    else:
        st.dataframe(issues, hide_index=True)


def cleaned_tab(result: DashboardResult) -> None:
    frame = cleaned_tickets_frame(result.tickets)
    st.dataframe(frame, hide_index=True)
    st.download_button(
        "Download cleaned CSV",
        frame.to_csv(index=False).encode("utf-8"),
        file_name="cleaned_tickets.csv",
        mime="text/csv",
    )


def results(result: DashboardResult) -> None:
    st.success(f"Processed **{result.file_name}**: {result.report.cleaned_rows} clean tickets.")
    if result.report.cleaned_rows == 0:
        st.warning("No valid tickets remained after cleaning, so analytics are empty.")
    tabs = st.tabs(["Preview", "Analytics", "Data quality", "Cleaned data"])
    with tabs[0]:
        preview_tab(result)
    with tabs[1]:
        analytics_tab(result)
    with tabs[2]:
        quality_tab(result)
    with tabs[3]:
        cleaned_tab(result)


def main() -> None:
    st.set_page_config(page_title="Ticket Dashboard", layout="wide")
    # Pipeline logs (counts and timings, never ticket text) go to the terminal.
    # configure_logging replaces its handler, so reruns do not duplicate lines.
    configure_logging("INFO")
    init_state()
    st.title("Support ticket dashboard")
    st.caption("Upload a ticket export to check its quality and see summary analytics.")
    sidebar()
    if st.session_state.error:
        st.error(st.session_state.error)
    if st.session_state.result is None:
        empty_state()
    else:
        results(st.session_state.result)


main()
