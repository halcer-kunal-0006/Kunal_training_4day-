"""Domain objects: a validated SupportTicket and the cleaning report.

A ``SupportTicket`` cannot exist in an invalid state: ``__post_init__`` checks
every field and ``frozen=True`` blocks later changes. A missing number is
``None``; a missing or unrecognised priority is ``Priority.UNKNOWN``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import (
    CUSTOMER_RATING_RULE,
    RESOLUTION_TIME_RULE,
    RESOLVED_STATUSES,
    UNKNOWN,
    DuplicatePolicy,
    NumericRule,
)
from .errors import InvalidTicketError


class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = UNKNOWN


KNOWN_PRIORITIES: frozenset[str] = frozenset(priority.value for priority in Priority)


@dataclass(frozen=True, slots=True)
class SupportTicket:
    ticket_id: str
    category: str
    priority: Priority
    description: str
    resolution_time_hours: float | None
    customer_rating: float | None
    status: str

    def __post_init__(self) -> None:
        for name in ("ticket_id", "category", "status"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidTicketError(name, f"must be a non-empty string, got {value!r}")
        if not isinstance(self.description, str):
            # The value itself is not shown: descriptions may hold customer data.
            raise InvalidTicketError("description", "must be a string")
        if not isinstance(self.priority, Priority):
            raise InvalidTicketError(
                "priority", f"must be a Priority, got {type(self.priority).__name__}"
            )
        _check_number(self.resolution_time_hours, RESOLUTION_TIME_RULE)
        _check_number(self.customer_rating, CUSTOMER_RATING_RULE)

    @property
    def is_resolved(self) -> bool:
        return self.status in RESOLVED_STATUSES

    def to_row(self) -> dict[str, str]:
        """The ticket as CSV cells, in REQUIRED_COLUMNS order."""
        return {
            "ticket_id": self.ticket_id,
            "category": self.category,
            "priority": self.priority.value,
            "description": self.description,
            "resolution_time_hours": _format_number(self.resolution_time_hours),
            "customer_rating": _format_number(self.customer_rating),
            "status": self.status,
        }

    def __str__(self) -> str:
        # Deliberately excludes the description, so a ticket is safe to log.
        return f"{self.ticket_id} [{self.priority.value}/{self.category}] {self.status}"


def _format_number(value: float | None) -> str:
    """'' for missing, '5' for 5.0, '2.5' for 2.5 (repr keeps full precision)."""
    if value is None:
        return ""
    return str(int(value)) if value.is_integer() else repr(value)


def _check_number(value: object, rule: NumericRule) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, float):
        raise InvalidTicketError(rule.column, f"must be a float or None, got {value!r}")
    if not rule.accepts(value):
        raise InvalidTicketError(rule.column, f"must be {rule.description}, got {value!r}")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One problem found in one source record.

    ``record_number`` counts data rows from 1 (the first row after the header).
    """

    record_number: int
    code: str
    ticket_id: str | None = None


@dataclass(frozen=True)
class CleaningReport:
    """What cleaning did and why, returned as a value instead of stored on an object."""

    source_rows: int
    cleaned_rows: int
    duplicate_policy: DuplicatePolicy
    rows_dropped_missing_ticket_id: int = 0
    duplicate_rows_removed: int = 0
    duplicate_ticket_ids: tuple[str, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()
    missing_values_before_cleaning: dict[str, int] = field(default_factory=dict)
    missing_values_after_cleaning: dict[str, int] = field(default_factory=dict)
    invalid_numeric_values: dict[str, int] = field(default_factory=dict)

    @property
    def invalid_record_count(self) -> int:
        return len({issue.record_number for issue in self.issues})

    def issues_by_record(self) -> dict[int, list[str]]:
        """Record number -> sorted, de-duplicated issue codes, in record order."""
        grouped: dict[int, set[str]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.record_number, set()).add(issue.code)
        return {number: sorted(grouped[number]) for number in sorted(grouped)}

    def issue_counts(self) -> dict[str, int]:
        """Issue code -> number of records with that issue, sorted by code."""
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        return dict(sorted(counts.items()))

    def quality_summary(self) -> dict[str, Any]:
        """The data-quality fields published next to the analytics metrics."""
        return {
            "missing_values_after_cleaning": dict(self.missing_values_after_cleaning),
            "missing_values_before_cleaning": dict(self.missing_values_before_cleaning),
            "invalid_numeric_values": dict(self.invalid_numeric_values),
            "invalid_record_count": self.invalid_record_count,
            "duplicate_ticket_ids": list(self.duplicate_ticket_ids),
            "rows_dropped_missing_ticket_id": self.rows_dropped_missing_ticket_id,
        }
