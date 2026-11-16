"""Headless UI tests with Streamlit's AppTest.

AppTest runs app.py the way the server does, without a browser. Each fixture in
tests/fixtures/uploads is pushed through the real ``st.file_uploader`` widget, so
these tests are the automated version of docs/UI_TEST_CHECKLIST.md.
"""

from __future__ import annotations

import pytest
from conftest import PROJECT_ROOT
from streamlit.testing.v1 import AppTest

from ticket_dashboard import process_upload
from ticket_pipeline import DuplicatePolicy

pytestmark = pytest.mark.ui

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "data" / "tickets.csv"
UPLOADS = PROJECT_ROOT / "tests" / "fixtures" / "uploads"


@pytest.fixture
def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def upload_and_process(app: AppTest, file_name: str) -> None:
    app.file_uploader[0].upload(file_name, (UPLOADS / file_name).read_bytes(), "text/csv")
    app.button(key="process").click().run()


def test_valid_upload_through_the_widget_shows_results(app: AppTest) -> None:
    upload_and_process(app, "valid.csv")

    assert not app.exception
    assert not app.error
    assert "valid.csv" in app.success[0].value
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Clean tickets"] == "4"
    assert metrics["Rows"] == "4"


@pytest.mark.parametrize(
    ("file_name", "message_part"),
    [
        ("empty.csv", "is empty"),
        ("blank_lines.csv", "only blank lines"),
        ("header_only.csv", "no ticket records"),
        ("malformed.csv", "expected 7 fields, found 8"),
        ("bad_quotes.csv", "expected 7 fields"),
        ("bad_encoding.csv", "not valid UTF-8"),
        ("wrong_columns.csv", "missing required column(s)"),
        ("wrong_ext.txt", "instead of '.csv'"),
    ],
)
def test_invalid_upload_shows_an_explanation_not_a_crash(
    app: AppTest, file_name: str, message_part: str
) -> None:
    upload_and_process(app, file_name)

    assert not app.exception  # no traceback on the page
    assert message_part in app.error[0].value
    assert app.session_state["result"] is None
    assert not app.tabs  # no half-rendered results


def test_upload_with_no_valid_tickets_warns_instead_of_crashing(app: AppTest) -> None:
    upload_and_process(app, "no_valid_ids.csv")

    assert not app.exception
    assert "No valid tickets remained" in app.warning[0].value


def test_app_starts_without_exceptions_and_shows_the_empty_state(app: AppTest) -> None:
    assert not app.exception
    assert app.title[0].value == "Support ticket dashboard"
    assert "Upload a ticket CSV" in app.info[0].value
    assert not app.error
    assert app.session_state["result"] is None


def test_load_sample_shows_tabs_and_metrics_that_match_the_service(app: AppTest) -> None:
    app.button(key="load_sample").click().run()

    assert not app.exception
    assert not app.error
    assert [tab.label for tab in app.tabs] == ["Preview", "Analytics", "Data quality",
                                               "Cleaned data"]  # fmt: skip
    expected = process_upload(SAMPLE.name, SAMPLE.read_bytes())
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Rows"] == str(expected.preview.row_count)
    assert metrics["Clean tickets"] == str(expected.report.cleaned_rows)
    assert metrics["Unresolved tickets"] == str(expected.analytics["unresolved_ticket_count"])
    assert metrics["Invalid records"] == str(expected.report.invalid_record_count)
    assert metrics["Average rating"] == f"{expected.analytics['average_customer_rating']:.2f}"


def test_process_without_a_file_explains_what_to_do(app: AppTest) -> None:
    app.button(key="process").click().run()

    assert not app.exception
    assert "No file selected" in app.error[0].value
    assert app.session_state["result"] is None


def test_pipeline_error_is_shown_as_a_message_not_a_traceback(app: AppTest) -> None:
    app.selectbox(key="policy").select(DuplicatePolicy.RAISE)
    app.button(key="load_sample").click().run()

    assert not app.exception
    assert "T-002" in app.error[0].value  # the sample file repeats ticket T-002
    assert app.session_state["result"] is None


def test_rerun_keeps_the_result_without_reprocessing(app: AppTest) -> None:
    app.button(key="load_sample").click().run()
    first = app.session_state["result"]

    app.button(key="load_sample").click().run()  # same bytes, same policy
    app.run()  # an unrelated rerun

    assert app.session_state["result"] is first  # same object: not recomputed


def test_error_after_success_replaces_the_old_result(app: AppTest) -> None:
    app.button(key="load_sample").click().run()
    app.selectbox(key="policy").select(DuplicatePolicy.RAISE)
    app.button(key="load_sample").click().run()

    assert app.session_state["result"] is None  # no stale analytics next to an error
    assert app.error


def test_clear_resets_to_the_empty_state(app: AppTest) -> None:
    app.button(key="load_sample").click().run()
    uploader_version = app.session_state["uploader_v"]

    app.button(key="clear").click().run()

    assert not app.exception
    assert app.session_state["result"] is None
    assert app.session_state["error"] is None
    assert app.session_state["uploader_v"] == uploader_version + 1
    assert "Upload a ticket CSV" in app.info[0].value
