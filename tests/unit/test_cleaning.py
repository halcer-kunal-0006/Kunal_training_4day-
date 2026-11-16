"""clean_records applies every cleaning rule and reports what it changed.

Records are built in memory, so these tests run without any file I/O.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path

import pytest

from ticket_pipeline import (
    DuplicatePolicy,
    DuplicateTicketError,
    Priority,
    RawRecord,
    ValidationIssue,
    clean_records,
    open_ticket_csv,
)

DEFAULTS = {
    "ticket_id": "T-1",
    "category": "billing",
    "priority": "high",
    "description": "Charged twice",
    "resolution_time_hours": "2",
    "customer_rating": "5",
    "status": "resolved",
}


def record(number: int, **values: str) -> RawRecord:
    return RawRecord(record_number=number, line=number + 1, values={**DEFAULTS, **values})


def test_text_is_trimmed_ids_upper_cased_and_labels_lower_cased() -> None:
    result = clean_records([record(1, ticket_id=" t-9 ", category=" Billing ", status="CLOSED")])

    (ticket,) = result.tickets
    assert (ticket.ticket_id, ticket.category, ticket.status) == ("T-9", "billing", "closed")


def test_record_without_ticket_id_is_dropped_and_reported() -> None:
    result = clean_records([record(1), record(2, ticket_id="  ")])

    assert [ticket.ticket_id for ticket in result.tickets] == ["T-1"]
    assert result.report.rows_dropped_missing_ticket_id == 1
    assert result.report.issues == (ValidationIssue(2, "missing_ticket_id"),)


def test_duplicate_id_keep_first_keeps_the_first_record_and_reports_the_rest() -> None:
    result = clean_records(
        [record(1, status="open"), record(2, ticket_id="t-1", status="closed"), record(3)]
    )

    assert [ticket.status for ticket in result.tickets] == ["open"]
    assert result.report.duplicate_ticket_ids == ("T-1",)
    assert result.report.duplicate_rows_removed == 2
    assert {issue.record_number for issue in result.report.issues} == {2, 3}


def test_duplicate_id_raise_policy_stops_with_both_record_numbers() -> None:
    records = [record(1), record(2, ticket_id="T-2"), record(3, ticket_id="T-1")]

    with pytest.raises(DuplicateTicketError) as caught:
        clean_records(records, DuplicatePolicy.RAISE)

    assert (caught.value.ticket_id, caught.value.first_record, caught.value.duplicate_record) == (
        "T-1",
        1,
        3,
    )


@pytest.mark.parametrize(
    ("column", "text", "code"),
    [
        ("resolution_time_hours", "bad", "invalid_resolution_time_hours"),
        ("resolution_time_hours", "-2", "invalid_resolution_time_hours"),
        ("customer_rating", "6", "invalid_customer_rating"),
        ("customer_rating", "inf", "invalid_customer_rating"),
    ],
)
def test_invalid_number_is_cleared_and_reported(column: str, text: str, code: str) -> None:
    result = clean_records([record(1, **{column: text})])

    assert getattr(result.tickets[0], column) is None
    assert result.report.invalid_numeric_values[column] == 1
    assert result.report.issues == (ValidationIssue(1, code, "T-1"),)


def test_missing_number_stays_missing_and_is_not_reported() -> None:
    result = clean_records([record(1, customer_rating="")])

    assert result.tickets[0].customer_rating is None
    assert result.report.issues == ()
    assert result.report.missing_values_after_cleaning["customer_rating"] == 1


def test_unrecognised_priority_becomes_unknown_and_is_reported() -> None:
    result = clean_records([record(1, priority="Urgent")])

    assert result.tickets[0].priority is Priority.UNKNOWN
    assert result.report.issues == (ValidationIssue(1, "invalid_priority", "T-1"),)


def test_missing_text_fields_get_placeholders() -> None:
    result = clean_records([record(1, category="", priority="", description=" ", status="")])

    ticket = result.tickets[0]
    assert (ticket.category, ticket.priority, ticket.status) == (
        "unknown",
        Priority.UNKNOWN,
        "unknown",
    )
    assert ticket.description == ""
    assert result.report.issues == ()


def test_missing_values_are_counted_before_and_after_cleaning() -> None:
    result = clean_records([record(1, category="  ", customer_rating=""), record(2, ticket_id="")])

    before = result.report.missing_values_before_cleaning
    after = result.report.missing_values_after_cleaning
    assert (before["category"], before["customer_rating"], before["ticket_id"]) == (1, 1, 1)
    assert (after["category"], after["customer_rating"], after["ticket_id"]) == (0, 1, 0)


def test_input_records_are_not_modified() -> None:
    records = [record(1, ticket_id=" t-1 ", priority="urgent")]
    snapshot = copy.deepcopy(records)

    clean_records(records)

    assert records == snapshot


def test_records_can_come_from_a_one_shot_generator() -> None:
    def generate() -> Iterator[RawRecord]:
        yield from (record(1), record(2, ticket_id="T-2"))

    assert clean_records(generate()).report.cleaned_rows == 2


def test_sample_file_report_matches_hand_counted_values(sample_csv: Path) -> None:
    with open_ticket_csv(sample_csv) as reader:
        result = clean_records(reader)

    report = result.report
    assert (report.source_rows, report.cleaned_rows) == (5, 3)
    assert report.issues_by_record() == {
        2: ["invalid_resolution_time_hours"],
        3: ["missing_ticket_id"],
        4: ["duplicate_ticket_id"],
        5: ["invalid_customer_rating", "invalid_priority"],
    }
    assert [str(ticket) for ticket in result.tickets] == [
        "T-1 [high/billing] resolved",
        "T-2 [medium/technical] open",
        "T-3 [unknown/unknown] unknown",
    ]
