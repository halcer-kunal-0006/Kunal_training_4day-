"""Turn raw records into validated SupportTickets in a single streaming pass.

Cleaning rules, in the order they are applied to each record:

1. Trim all text; whitespace-only cells count as missing.
2. A record without a ticket ID cannot be tracked, so it is dropped and reported.
3. A repeated ticket ID is dropped and reported (KEEP_FIRST), or stops the run (RAISE).
4. Invalid numbers are cleared to None and reported; missing numbers stay None.
5. An unrecognised priority becomes UNKNOWN and is reported.
6. Missing category/status become "unknown"; a missing description becomes "".

The function never changes the records it is given.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from ..config import LABEL_COLUMNS, NUMERIC_RULES, REQUIRED_COLUMNS, UNKNOWN, DuplicatePolicy
from ..errors import DuplicateTicketError
from ..logging_config import log_event
from ..models import CleaningReport, SupportTicket, ValidationIssue
from .loader import RawRecord
from .validation import normalise_text, parse_number, parse_priority

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleaningResult:
    tickets: tuple[SupportTicket, ...]
    report: CleaningReport


def clean_records(
    records: Iterable[RawRecord],
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.KEEP_FIRST,
) -> CleaningResult:
    """Apply the cleaning rules to every record and report what was changed and why."""
    tickets: list[SupportTicket] = []
    issues: list[ValidationIssue] = []
    missing_before = dict.fromkeys(REQUIRED_COLUMNS, 0)
    invalid_numeric = {rule.column: 0 for rule in NUMERIC_RULES}
    first_seen: dict[str, int] = {}  # ticket ID -> record number of its first occurrence
    duplicate_ids: set[str] = set()
    source_rows = dropped_missing_id = duplicates_removed = 0

    for record in records:
        source_rows += 1
        text = {column: normalise_text(record.values.get(column)) for column in REQUIRED_COLUMNS}
        for column, value in text.items():
            missing_before[column] += value is None

        raw_id = text["ticket_id"]
        if raw_id is None:
            dropped_missing_id += 1
            issues.append(ValidationIssue(record.record_number, "missing_ticket_id"))
            continue
        ticket_id = raw_id.upper()

        if ticket_id in first_seen:
            if duplicate_policy is DuplicatePolicy.RAISE:
                raise DuplicateTicketError(ticket_id, first_seen[ticket_id], record.record_number)
            duplicates_removed += 1
            duplicate_ids.add(ticket_id)
            issues.append(ValidationIssue(record.record_number, "duplicate_ticket_id", ticket_id))
            continue
        first_seen[ticket_id] = record.record_number

        numbers: dict[str, float | None] = {}
        for rule in NUMERIC_RULES:
            check = parse_number(text[rule.column], rule)
            numbers[rule.column] = check.value
            if check.invalid:
                invalid_numeric[rule.column] += 1
                issues.append(
                    ValidationIssue(record.record_number, f"invalid_{rule.column}", ticket_id)
                )

        priority = parse_priority(text["priority"])
        if priority.invalid:
            issues.append(ValidationIssue(record.record_number, "invalid_priority", ticket_id))

        labels = {column: (text[column] or UNKNOWN).lower() for column in LABEL_COLUMNS}
        tickets.append(
            SupportTicket(
                ticket_id=ticket_id,
                category=labels["category"],
                priority=priority.value,
                description=text["description"] or "",
                resolution_time_hours=numbers["resolution_time_hours"],
                customer_rating=numbers["customer_rating"],
                status=labels["status"],
            )
        )

    report = CleaningReport(
        source_rows=source_rows,
        cleaned_rows=len(tickets),
        duplicate_policy=duplicate_policy,
        rows_dropped_missing_ticket_id=dropped_missing_id,
        duplicate_rows_removed=duplicates_removed,
        duplicate_ticket_ids=tuple(sorted(duplicate_ids)),
        issues=tuple(issues),
        missing_values_before_cleaning=missing_before,
        missing_values_after_cleaning=_missing_after(tickets),
        invalid_numeric_values=invalid_numeric,
    )
    _log_issues(report)
    return CleaningResult(tuple(tickets), report)


def _missing_after(tickets: Iterable[SupportTicket]) -> dict[str, int]:
    """Text fields are always filled by cleaning; only numbers can still be missing."""
    missing = dict.fromkeys(REQUIRED_COLUMNS, 0)
    for ticket in tickets:
        for rule in NUMERIC_RULES:
            missing[rule.column] += getattr(ticket, rule.column) is None
    return missing


def _log_issues(report: CleaningReport) -> None:
    """One WARNING line per issue type; per-record detail only at DEBUG. Never any text values."""
    log_event(
        logger,
        logging.INFO,
        "records_cleaned",
        source_rows=report.source_rows,
        cleaned_rows=report.cleaned_rows,
        invalid_records=report.invalid_record_count,
    )
    if logger.isEnabledFor(logging.WARNING):
        # One pass over the issues, instead of one scan per issue code.
        records_by_code: dict[str, list[int]] = defaultdict(list)
        for issue in report.issues:
            records_by_code[issue.code].append(issue.record_number)
        for code, records in sorted(records_by_code.items()):
            log_event(
                logger,
                logging.WARNING,
                "data_issue",
                code=code,
                count=len(records),
                records=records,
            )
    for issue in report.issues:
        log_event(
            logger,
            logging.DEBUG,
            "record_issue",
            record=issue.record_number,
            ticket_id=issue.ticket_id or "-",
            code=issue.code,
        )
