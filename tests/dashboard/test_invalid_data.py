"""Every file in data/invalid is detected, and explained, the way data/invalid/README.md says.

The files are realistic broken ticket exports for trying the dashboard by hand.
These tests run each one through the service and through the real upload widget,
and fail if a file is added to the folder without an expected result here.
"""

from __future__ import annotations

import pytest
from conftest import PROJECT_ROOT
from streamlit.testing.v1 import AppTest

from ticket_dashboard import UploadError, process_upload
from ticket_pipeline import (
    DuplicatePolicy,
    DuplicateTicketError,
    EmptyDatasetError,
    MalformedFileError,
    SchemaMismatchError,
    TicketPipelineError,
)

INVALID = PROJECT_ROOT / "data" / "invalid"
APP = str(PROJECT_ROOT / "app.py")

# File -> (error the service must raise, text the message must contain)
REJECTED: dict[str, tuple[type[TicketPipelineError], str]] = {
    "empty.csv": (UploadError, "is empty (0 bytes)"),
    "blank_lines_only.csv": (UploadError, "contains only blank lines"),
    "tickets_export.txt": (UploadError, "has the extension '.txt' instead of '.csv'"),
    "header_only.csv": (EmptyDatasetError, "header row but no ticket records"),
    "missing_columns.csv": (SchemaMismatchError, "missing required column(s): customer_rating"),
    "renamed_columns.csv": (SchemaMismatchError, "Found columns: id, type, urgency"),
    "duplicate_column.csv": (SchemaMismatchError, "duplicated column(s): status"),
    "unquoted_comma.csv": (MalformedFileError, "line 4: expected 7 fields, found 8"),
    "missing_field.csv": (MalformedFileError, "line 2: expected 7 fields, found 6"),
    "unclosed_quote.csv": (MalformedFileError, "line 3: expected 7 fields, found 4"),
    "latin1_encoding.csv": (MalformedFileError, "not valid UTF-8"),
}  # fmt: skip
# Files that are readable, so they are processed and their problems reported.
ACCEPTED = {"duplicate_ticket_ids.csv", "no_valid_ticket_ids.csv", "dirty_values.csv"}


def read(name: str) -> bytes:
    return (INVALID / name).read_bytes()


def test_every_file_in_the_folder_has_an_expected_result() -> None:
    files = {path.name for path in INVALID.iterdir() if path.name != "README.md"}
    assert files == set(REJECTED) | ACCEPTED


def test_every_file_is_listed_in_the_folder_readme() -> None:
    readme = (INVALID / "README.md").read_text(encoding="utf-8")
    missing = [name for name in [*REJECTED, *ACCEPTED] if f"`{name}`" not in readme]
    assert not missing


# ---- Service layer ---------------------------------------------------------------


@pytest.mark.parametrize("policy", list(DuplicatePolicy))
@pytest.mark.parametrize("name", sorted(REJECTED))
def test_rejected_file_raises_a_specific_explained_error(
    name: str, policy: DuplicatePolicy
) -> None:
    error, message_part = REJECTED[name]

    with pytest.raises(error) as caught:
        process_upload(name, read(name), policy)

    message = str(caught.value)
    assert message_part in message
    assert name in message  # names the file the user picked
    assert str(PROJECT_ROOT) not in message  # never leaks a server path


def test_duplicate_ids_are_removed_with_keep_first() -> None:
    report = process_upload("duplicate_ticket_ids.csv", read("duplicate_ticket_ids.csv")).report

    assert (report.source_rows, report.cleaned_rows) == (4, 3)
    assert report.duplicate_rows_removed == 1
    assert report.duplicate_ticket_ids == ("T-101",)


@pytest.mark.parametrize("name", ["duplicate_ticket_ids.csv", "dirty_values.csv"])
def test_duplicate_ids_stop_the_file_with_reject(name: str) -> None:
    with pytest.raises(DuplicateTicketError, match="Ticket ID T-101 appears in record 1"):
        process_upload(name, read(name), DuplicatePolicy.RAISE)


def test_file_without_any_ticket_ids_gives_empty_analytics() -> None:
    result = process_upload("no_valid_ticket_ids.csv", read("no_valid_ticket_ids.csv"))

    assert result.report.cleaned_rows == 0
    assert result.report.rows_dropped_missing_ticket_id == 2
    assert result.analytics["average_customer_rating"] is None


def test_dirty_values_report_one_issue_per_cleaning_rule() -> None:
    result = process_upload("dirty_values.csv", read("dirty_values.csv"))
    report = result.report

    assert (report.source_rows, report.cleaned_rows) == (11, 9)
    assert report.invalid_record_count == 8
    assert report.issue_counts() == {
        "duplicate_ticket_id": 1,
        "invalid_customer_rating": 3,
        "invalid_priority": 1,
        "invalid_resolution_time_hours": 3,
        "missing_ticket_id": 1,
    }
    tickets = {ticket.ticket_id: ticket for ticket in result.tickets}
    assert tickets["T-108"].category == "billing"  # spaces and case tidied, not rejected
    assert tickets["T-108"].status == "resolved"
    assert tickets["T-107"].category == "unknown"  # missing label filled in
    assert tickets["T-109"].resolution_time_hours is None  # "nan" is not a number here
    assert tickets["T-109"].customer_rating is None  # nor is "inf"


# ---- Through the real upload widget ------------------------------------------------


@pytest.fixture
def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def upload_and_process(app: AppTest, name: str) -> None:
    app.file_uploader[0].upload(name, read(name), "text/csv")
    app.button(key="process").click().run()


@pytest.mark.ui
@pytest.mark.parametrize("name", sorted(REJECTED))
def test_rejected_file_shows_an_error_box_not_a_traceback(app: AppTest, name: str) -> None:
    upload_and_process(app, name)

    assert not app.exception
    assert REJECTED[name][1] in app.error[0].value
    assert app.session_state["result"] is None
    assert not app.tabs


@pytest.mark.ui
def test_dirty_file_shows_the_problems_in_the_data_quality_tab(app: AppTest) -> None:
    upload_and_process(app, "dirty_values.csv")

    assert not app.exception
    assert not app.error
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Clean tickets"] == "9"
    assert metrics["Invalid records"] == "8"
    assert metrics["Dropped (no ID)"] == "1"
    assert metrics["Duplicates removed"] == "1"


@pytest.mark.ui
def test_file_without_ticket_ids_warns(app: AppTest) -> None:
    upload_and_process(app, "no_valid_ticket_ids.csv")

    assert not app.exception
    assert "No valid tickets remained" in app.warning[0].value
