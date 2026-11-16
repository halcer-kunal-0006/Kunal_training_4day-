"""SupportTicket can only hold valid data; CleaningReport summarises issues correctly."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable
from typing import Any

import pytest

from ticket_pipeline import (
    CleaningReport,
    DuplicatePolicy,
    InvalidTicketError,
    Priority,
    SupportTicket,
    ValidationIssue,
)

MakeTicket = Callable[..., SupportTicket]


def test_ticket_with_valid_fields_is_created(make_ticket: MakeTicket) -> None:
    ticket = make_ticket()

    assert ticket.ticket_id == "T-1"
    assert ticket.priority is Priority.HIGH


def test_ticket_is_immutable(make_ticket: MakeTicket) -> None:
    ticket = make_ticket()

    with pytest.raises(dataclasses.FrozenInstanceError):
        ticket.status = "open"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticket_id", ""),
        ("ticket_id", "   "),
        ("category", None),
        ("status", 5),
        ("description", None),
        ("priority", "high"),
        ("resolution_time_hours", -1.0),
        ("resolution_time_hours", math.inf),
        ("resolution_time_hours", "2.5"),
        ("customer_rating", 0.0),
        ("customer_rating", 6.0),
        ("customer_rating", math.nan),
        ("customer_rating", True),
        ("customer_rating", 4),  # int, not float: cleaning always produces floats
    ],
)
def test_ticket_with_invalid_field_raises_invalid_ticket_error(
    make_ticket: MakeTicket, field: str, value: Any
) -> None:
    with pytest.raises(InvalidTicketError) as caught:
        make_ticket(**{field: value})

    assert caught.value.field == field


def test_invalid_description_error_does_not_echo_the_value(make_ticket: MakeTicket) -> None:
    with pytest.raises(InvalidTicketError) as caught:
        make_ticket(description=b"secret bytes")

    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resolution_time_hours", None),
        ("resolution_time_hours", 0.0),
        ("customer_rating", None),
        ("customer_rating", 1.0),
        ("customer_rating", 5.0),
    ],
)
def test_ticket_accepts_missing_and_boundary_numbers(
    make_ticket: MakeTicket, field: str, value: float | None
) -> None:
    assert getattr(make_ticket(**{field: value}), field) == value


@pytest.mark.parametrize(
    ("status", "resolved"),
    [("resolved", True), ("closed", True), ("open", False), ("pending", False)],
)
def test_ticket_is_resolved_only_for_resolved_or_closed(
    make_ticket: MakeTicket, status: str, resolved: bool
) -> None:
    assert make_ticket(status=status).is_resolved is resolved


def test_ticket_to_row_formats_numbers_and_blanks_missing_values(make_ticket: MakeTicket) -> None:
    row = make_ticket(resolution_time_hours=8.0, customer_rating=None).to_row()

    assert row == {
        "ticket_id": "T-1",
        "category": "billing",
        "priority": "high",
        "description": "Charged twice",
        "resolution_time_hours": "8",
        "customer_rating": "",
        "status": "resolved",
    }


def test_ticket_to_row_keeps_decimal_precision(make_ticket: MakeTicket) -> None:
    assert make_ticket(resolution_time_hours=2.125).to_row()["resolution_time_hours"] == "2.125"


def test_ticket_str_never_contains_the_description(make_ticket: MakeTicket) -> None:
    text = str(make_ticket(description="Private customer text"))

    assert text == "T-1 [high/billing] resolved"


@pytest.fixture
def report() -> CleaningReport:
    return CleaningReport(
        source_rows=5,
        cleaned_rows=3,
        duplicate_policy=DuplicatePolicy.KEEP_FIRST,
        rows_dropped_missing_ticket_id=1,
        duplicate_ticket_ids=("T-1",),
        issues=(
            ValidationIssue(4, "invalid_customer_rating", "T-4"),
            ValidationIssue(2, "invalid_resolution_time_hours", "T-2"),
            ValidationIssue(4, "invalid_priority", "T-4"),
            ValidationIssue(3, "missing_ticket_id"),
        ),
    )


def test_report_counts_each_problem_record_once(report: CleaningReport) -> None:
    assert report.invalid_record_count == 3


def test_report_groups_issue_codes_by_record_in_record_order(report: CleaningReport) -> None:
    assert report.issues_by_record() == {
        2: ["invalid_resolution_time_hours"],
        3: ["missing_ticket_id"],
        4: ["invalid_customer_rating", "invalid_priority"],
    }


def test_report_issue_counts_are_sorted_by_code(report: CleaningReport) -> None:
    assert list(report.issue_counts()) == sorted(report.issue_counts())


def test_report_quality_summary_has_the_published_fields(report: CleaningReport) -> None:
    summary = report.quality_summary()

    assert summary["invalid_record_count"] == 3
    assert summary["duplicate_ticket_ids"] == ["T-1"]
    assert summary["rows_dropped_missing_ticket_id"] == 1
