"""Every error is catchable as TicketPipelineError and its message is actionable:
it says what failed, where, and what to do. Facts are also kept as attributes."""

from __future__ import annotations

from pathlib import Path

import pytest

from ticket_pipeline import (
    DuplicateTicketError,
    EmptyDatasetError,
    InvalidPathError,
    InvalidTicketError,
    MalformedFileError,
    OutputWriteError,
    SchemaMismatchError,
    TicketPipelineError,
)

PATH = Path("data/tickets.csv")


@pytest.mark.parametrize(
    "error",
    [
        InvalidPathError(PATH, "does not exist", "Check the path."),
        MalformedFileError(PATH, "bad", "Fix it."),
        EmptyDatasetError(PATH, "empty", "Export again."),
        SchemaMismatchError(PATH, missing=["status"]),
        DuplicateTicketError("T-1", 1, 2),
        InvalidTicketError("ticket_id", "must be non-empty"),
        OutputWriteError(PATH, "denied", "Check permissions."),
    ],
    ids=lambda error: type(error).__name__,
)
def test_every_error_is_a_ticket_pipeline_error(error: Exception) -> None:
    assert isinstance(error, TicketPipelineError)


def test_errors_are_not_value_errors_so_bugs_are_not_caught_by_accident() -> None:
    assert not issubclass(TicketPipelineError, ValueError)


def test_empty_dataset_error_is_a_malformed_file_error() -> None:
    assert issubclass(EmptyDatasetError, MalformedFileError)


def test_invalid_path_error_message_names_path_reason_and_hint() -> None:
    error = InvalidPathError(PATH, "does not exist", "Check the spelling.")

    assert str(error) == f"Input path '{PATH}' does not exist. Check the spelling."
    assert (error.path, error.reason, error.hint) == (PATH, "does not exist", "Check the spelling.")


@pytest.mark.parametrize(
    ("line", "expected_location"),
    [(7, f"'{PATH}' line 7: "), (None, f"'{PATH}': ")],
)
def test_malformed_file_error_includes_line_only_when_known(
    line: int | None, expected_location: str
) -> None:
    error = MalformedFileError(PATH, "expected 7 fields, found 8", "Quote commas.", line=line)

    assert str(error) == f"{expected_location}expected 7 fields, found 8. Quote commas."
    assert error.line == line


def test_schema_mismatch_error_lists_missing_duplicated_and_found_columns() -> None:
    error = SchemaMismatchError(
        PATH, missing=["status"], found=["ticket_id", "ticket_id"], duplicated=["ticket_id"]
    )

    message = str(error)
    assert "missing required column(s): status" in message
    assert "duplicated column(s): ticket_id" in message
    assert "Found columns: ticket_id, ticket_id" in message
    assert error.missing == ("status",)


def test_schema_mismatch_error_with_empty_header_says_none() -> None:
    assert "Found columns: (none)" in str(SchemaMismatchError(PATH, missing=["status"]))


def test_duplicate_ticket_error_names_both_records_and_the_alternative_policy() -> None:
    error = DuplicateTicketError("T-002", 2, 23)

    assert "T-002 appears in record 2 and again in record 23" in str(error)
    assert "keep_first" in str(error)
    assert (error.first_record, error.duplicate_record) == (2, 23)
