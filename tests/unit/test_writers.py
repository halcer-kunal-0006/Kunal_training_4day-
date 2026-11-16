"""Writers produce the documented formats, never overwrite the input, and never leave
half-written files behind when the operating system refuses a write."""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from ticket_pipeline import (
    CleaningReport,
    DuplicatePolicy,
    OutputWriteError,
    SupportTicket,
    ValidationIssue,
)
from ticket_pipeline.processing.writers import write_cleaned_csv, write_json, write_quality_report

MakeTicket = Callable[..., SupportTicket]


def test_cleaned_csv_has_header_and_one_row_per_ticket(
    tmp_path: Path, make_ticket: MakeTicket
) -> None:
    destination = tmp_path / "cleaned.csv"

    write_cleaned_csv(
        [make_ticket(), make_ticket(ticket_id="T-2", customer_rating=None)], destination
    )

    with destination.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["ticket_id"] for row in rows] == ["T-1", "T-2"]
    assert rows[1]["customer_rating"] == ""


def test_quality_report_lists_each_problem_record_once(tmp_path: Path) -> None:
    report = CleaningReport(
        source_rows=3,
        cleaned_rows=2,
        duplicate_policy=DuplicatePolicy.KEEP_FIRST,
        issues=(
            ValidationIssue(3, "invalid_priority", "T-3"),
            ValidationIssue(3, "invalid_customer_rating", "T-3"),
            ValidationIssue(1, "missing_ticket_id"),
        ),
    )

    path = write_quality_report(report, tmp_path / "issues.csv")

    assert path.read_text(encoding="utf-8").splitlines() == [
        "source_record_number,issues",
        "1,missing_ticket_id",
        "3,invalid_customer_rating;invalid_priority",
    ]


def test_json_output_round_trips(tmp_path: Path) -> None:
    data = {"average_customer_rating": None, "unresolved_ticket_count": 3}

    path = write_json(data, tmp_path / "analytics.json")

    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_missing_output_folders_are_created(tmp_path: Path) -> None:
    path = write_json({}, tmp_path / "a" / "b" / "out.json")

    assert path.exists()


def test_writing_over_a_protected_input_is_refused_and_input_is_untouched(
    tmp_path: Path, make_ticket: MakeTicket
) -> None:
    raw = tmp_path / "tickets.csv"
    raw.write_text("original", encoding="utf-8")

    with pytest.raises(OutputWriteError, match="it is the input file"):
        write_cleaned_csv([make_ticket()], tmp_path / "." / "tickets.csv", protected=[raw])

    assert raw.read_text(encoding="utf-8") == "original"


def test_os_failure_is_wrapped_chained_and_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "analytics.json"
    destination.write_text("previous run", encoding="utf-8")

    def disk_full(source: object, target: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", disk_full)  # boundary: the file system

    with pytest.raises(OutputWriteError, match="No space left on device") as caught:
        write_json({"x": 1}, destination)

    assert isinstance(caught.value.__cause__, OSError)
    assert destination.read_text(encoding="utf-8") == "previous run"
    assert list(tmp_path.iterdir()) == [destination]  # the .tmp file was removed
