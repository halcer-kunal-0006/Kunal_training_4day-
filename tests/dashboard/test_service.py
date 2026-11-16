"""Service-layer tests: uploads in, DashboardResult or a clear error out.

The upload files live in tests/fixtures/uploads so the same files are used for
these automated tests and for the manual UI checklist (docs/UI_TEST_CHECKLIST.md).
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest
from conftest import PROJECT_ROOT

from ticket_dashboard import (
    MAX_UPLOAD_BYTES,
    UploadError,
    cleaned_tickets_frame,
    issue_counts_frame,
    priority_counts_frame,
    process_upload,
    quality_frame,
    resolution_time_frame,
    validate_upload,
)
from ticket_pipeline import (
    DuplicatePolicy,
    DuplicateTicketError,
    EmptyDatasetError,
    MalformedFileError,
    PipelineConfig,
    SchemaMismatchError,
    TicketPipelineError,
    run_pipeline,
)
from ticket_pipeline.config import REQUIRED_COLUMNS

UPLOADS = PROJECT_ROOT / "tests" / "fixtures" / "uploads"
SAMPLE = PROJECT_ROOT / "data" / "tickets.csv"


def upload(name: str) -> tuple[str, bytes]:
    return name, (UPLOADS / name).read_bytes()


# ---- Valid uploads -------------------------------------------------------------


def test_valid_upload_produces_preview_analytics_and_quality() -> None:
    result = process_upload(*upload("valid.csv"))

    assert result.file_name == "valid.csv"
    assert result.preview.shape == (4, 7)
    assert result.preview.columns == REQUIRED_COLUMNS
    assert list(result.preview.dtypes["column"]) == list(REQUIRED_COLUMNS)
    assert result.report.cleaned_rows == 4
    assert result.report.invalid_record_count == 0
    assert result.analytics["ticket_count_by_priority"] == {"high": 2, "low": 1, "medium": 1}
    assert result.analytics["average_resolution_time_hours_by_category"] == {
        "billing": 3.0,
        "shipping": 6.0,
        "technical": 8.0,
    }
    assert result.analytics["unresolved_ticket_count"] == 2


def test_preview_infers_numeric_types_for_clean_numbers() -> None:
    dtypes = process_upload(*upload("valid.csv")).preview.dtypes.set_index("column")["dtype"]
    assert dtypes["resolution_time_hours"] == "int64"
    assert dtypes["customer_rating"] == "int64"


def test_preview_is_limited_to_the_first_rows() -> None:
    result = process_upload("tickets.csv", SAMPLE.read_bytes())
    assert len(result.preview.head) == 10
    assert result.preview.row_count == 25  # rows in the raw file, before cleaning


def test_utf8_bom_from_excel_is_accepted() -> None:
    name, data = upload("valid.csv")
    assert process_upload(name, b"\xef\xbb\xbf" + data).report.cleaned_rows == 4


def test_crlf_line_endings_are_accepted() -> None:
    name, data = upload("valid.csv")
    assert process_upload(name, data.replace(b"\n", b"\r\n")).report.cleaned_rows == 4


def test_only_the_bare_file_name_is_kept() -> None:
    _, data = upload("valid.csv")
    assert process_upload("some/folder/valid.csv", data).file_name == "valid.csv"


def test_file_with_no_valid_ticket_ids_gives_empty_analytics_not_a_crash() -> None:
    result = process_upload(*upload("no_valid_ids.csv"))
    assert result.report.cleaned_rows == 0
    assert result.report.rows_dropped_missing_ticket_id == 2
    assert result.analytics["ticket_count_by_priority"] == {}
    assert result.analytics["average_customer_rating"] is None


# ---- Invalid uploads: each gives a specific, explained error --------------------


@pytest.mark.parametrize(
    ("file_name", "error_type", "message_part"),
    [
        ("empty.csv", UploadError, "is empty (0 bytes)"),
        ("blank_lines.csv", UploadError, "contains only blank lines"),
        ("wrong_ext.txt", UploadError, "instead of '.csv'"),
        ("header_only.csv", EmptyDatasetError, "header row but no ticket records"),
        ("malformed.csv", MalformedFileError, "line 3: expected 7 fields, found 8"),
        ("bad_quotes.csv", MalformedFileError, "expected 7 fields, found 4"),
        ("bad_encoding.csv", MalformedFileError, "not valid UTF-8"),
        ("wrong_columns.csv", SchemaMismatchError, "missing required column(s)"),
    ],
)
def test_invalid_upload_raises_a_specific_error_with_a_hint(
    file_name: str, error_type: type[TicketPipelineError], message_part: str
) -> None:
    with pytest.raises(error_type) as caught:
        process_upload(*upload(file_name))

    message = str(caught.value)
    assert message_part in message
    assert file_name in message  # the user can tell which file failed
    assert str(UPLOADS) not in message  # no local paths leak into the UI


def test_every_invalid_upload_is_catchable_as_one_family() -> None:
    """The UI catches TicketPipelineError only; every fixture error must be in it."""
    for path in UPLOADS.iterdir():
        if path.name in {"valid.csv", "no_valid_ids.csv"}:
            continue
        with pytest.raises(TicketPipelineError):
            process_upload(path.name, path.read_bytes())


def test_oversized_upload_is_rejected_before_parsing() -> None:
    with pytest.raises(UploadError, match="above the 5 MB limit"):
        validate_upload("big.csv", b"x" * (MAX_UPLOAD_BYTES + 1))


def test_upload_at_the_size_limit_passes_the_size_check() -> None:
    validate_upload("big.csv", b"x" * MAX_UPLOAD_BYTES)  # no exception


def test_extension_check_is_case_insensitive() -> None:
    validate_upload("TICKETS.CSV", b"data")  # no exception


def test_raise_policy_rejects_duplicate_ticket_ids() -> None:
    with pytest.raises(DuplicateTicketError, match="T-002"):
        process_upload("tickets.csv", SAMPLE.read_bytes(), DuplicatePolicy.RAISE)


# ---- Analytics agree with the underlying dataset -------------------------------


def test_analytics_match_the_day3_pipeline_on_the_same_file(tmp_path: Path) -> None:
    """The dashboard must show exactly what the CLI/pipeline computes."""
    expected = run_pipeline(PipelineConfig(SAMPLE, tmp_path / "out"), write=False).analytics
    assert process_upload("tickets.csv", SAMPLE.read_bytes()).analytics == expected


def test_priority_counts_match_an_independent_count_of_the_raw_file() -> None:
    """Recount the raw CSV with the csv module, applying the documented rules by hand:
    rows without a ticket ID are dropped, later duplicates of an ID are dropped, and
    a missing or unrecognised priority counts as 'unknown'."""
    seen: set[str] = set()
    expected: Counter[str] = Counter()
    with SAMPLE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticket_id = row["ticket_id"].strip().upper()
            if not ticket_id or ticket_id in seen:
                continue
            seen.add(ticket_id)
            priority = row["priority"].strip().lower()
            expected[priority if priority in {"low", "medium", "high"} else "unknown"] += 1

    result = process_upload("tickets.csv", SAMPLE.read_bytes())

    assert result.analytics["ticket_count_by_priority"] == dict(expected)
    assert sum(expected.values()) == result.report.cleaned_rows == len(result.tickets)


def test_display_tables_carry_the_same_numbers_as_the_analytics() -> None:
    result = process_upload("tickets.csv", SAMPLE.read_bytes())
    analytics = result.analytics

    priorities = priority_counts_frame(analytics)
    assert (
        dict(zip(priorities["priority"], priorities["tickets"], strict=True))
        == (analytics["ticket_count_by_priority"])
    )
    resolution = resolution_time_frame(analytics).set_index("category")
    assert (
        resolution["avg_resolution_time_hours"].to_dict()
        == (analytics["average_resolution_time_hours_by_category"])
    )
    assert resolution["resolution_rate"].to_dict() == analytics["resolution_rate_by_category"]

    quality = quality_frame(result.report).set_index("column")
    assert quality["missing_before"].to_dict() == analytics["missing_values_before_cleaning"]
    assert quality["missing_after"].to_dict() == analytics["missing_values_after_cleaning"]
    issues = issue_counts_frame(result.report)
    assert dict(zip(issues["issue"], issues["records"], strict=True)) == (
        result.report.issue_counts()
    )


def test_cleaned_table_round_trips_through_the_pipeline() -> None:
    """Re-uploading the cleaned table gives the same tickets and no new issues."""
    first = process_upload("tickets.csv", SAMPLE.read_bytes())
    cleaned_csv = cleaned_tickets_frame(first.tickets).to_csv(index=False).encode("utf-8")

    second = process_upload("cleaned.csv", cleaned_csv)

    assert second.tickets == first.tickets
    assert second.report.invalid_record_count == 0


def test_processing_an_upload_writes_nothing_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uploads are processed in memory; the dashboard never leaves files behind."""
    monkeypatch.chdir(tmp_path)
    process_upload("tickets.csv", SAMPLE.read_bytes())
    assert list(tmp_path.iterdir()) == []
