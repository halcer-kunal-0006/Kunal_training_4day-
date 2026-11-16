"""Service layer between the Streamlit UI and the Day 3 processing pipeline.

The UI hands this module the uploaded file as ``(name, bytes)`` and gets back a
``DashboardResult``. Everything that decides whether data is valid, how it is
cleaned and how metrics are calculated stays in ``ticket_pipeline``; this module
only adapts an in-memory upload to the pipeline's reader and shapes the result
into tables for display. It never imports Streamlit, so it is tested with
plain pytest.

    bytes -> validate_upload -> TicketCsvReader -> clean_records -> summarise
                                                                  + quality_summary
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ticket_pipeline import (
    CleaningReport,
    DuplicatePolicy,
    SupportTicket,
    TicketPipelineError,
    clean_records,
    summarise,
)
from ticket_pipeline.config import REQUIRED_COLUMNS
from ticket_pipeline.processing.loader import ENCODING, TicketCsvReader

MAX_UPLOAD_MB = 5  # keep in step with server.maxUploadSize in .streamlit/config.toml
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
PREVIEW_ROWS = 10
ALLOWED_SUFFIX = ".csv"
_BLANK_BYTES = b" \t\r\n\xef\xbb\xbf"  # whitespace plus the UTF-8 byte-order mark


class UploadError(TicketPipelineError):
    """The upload was rejected before parsing: empty, too large, or not a CSV file."""

    def __init__(self, name: str, reason: str, hint: str) -> None:
        self.name = name
        self.reason = reason
        self.hint = hint
        super().__init__(f"Upload '{name}' {reason}. {hint}")


@dataclass(frozen=True)
class Preview:
    """What the raw upload looks like before cleaning (Task A)."""

    row_count: int
    columns: tuple[str, ...]
    dtypes: pd.DataFrame  # one row per column: column, dtype, non_null
    head: pd.DataFrame  # the first PREVIEW_ROWS rows, unchanged

    @property
    def shape(self) -> tuple[int, int]:
        return self.row_count, len(self.columns)


@dataclass(frozen=True)
class DashboardResult:
    """Everything the dashboard shows for one successfully processed file."""

    file_name: str
    preview: Preview
    tickets: tuple[SupportTicket, ...]
    report: CleaningReport
    analytics: dict[str, Any]  # summarise() metrics + report.quality_summary() fields


def validate_upload(name: str, data: bytes) -> None:
    """Cheap checks on the upload itself, done before any parsing."""
    if Path(name).suffix.lower() != ALLOWED_SUFFIX:
        raise UploadError(
            name,
            f"has the extension '{Path(name).suffix or '(none)'}' instead of '.csv'",
            "Export the ticket data as CSV and upload that file.",
        )
    if not data.strip(_BLANK_BYTES):
        raise UploadError(
            name,
            "is empty (0 bytes)" if not data else "contains only blank lines",
            "Export the data again and re-upload it.",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(
            name,
            f"is {len(data) / 1024 / 1024:.1f} MB, above the {MAX_UPLOAD_MB} MB limit",
            "Split the export into smaller files.",
        )


def process_upload(
    name: str,
    data: bytes,
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.KEEP_FIRST,
) -> DashboardResult:
    """Validate, clean and analyse one uploaded CSV.

    Raises a ``TicketPipelineError`` subclass (with a message and a hint) for any
    problem the user can fix; nothing is written to disk.
    """
    name = Path(name).name  # only ever show the bare file name
    validate_upload(name, data)
    # The same reader the CLI uses, fed from memory instead of a file on disk, so
    # an upload gets exactly the same encoding, schema and field-count checks.
    with io.TextIOWrapper(io.BytesIO(data), encoding=ENCODING, newline="") as handle:
        cleaned = clean_records(TicketCsvReader(handle, Path(name)), duplicate_policy)
    analytics = {**summarise(cleaned.tickets), **cleaned.report.quality_summary()}
    return DashboardResult(
        file_name=name,
        preview=build_preview(name, data),
        tickets=cleaned.tickets,
        report=cleaned.report,
        analytics=analytics,
    )


def build_preview(name: str, data: bytes, rows: int = PREVIEW_ROWS) -> Preview:
    """Raw rows, columns, dimensions and inferred types. Display only: no cleaning."""
    try:
        frame = pd.read_csv(io.BytesIO(data), encoding=ENCODING, skip_blank_lines=True)
    except (ValueError, UnicodeDecodeError) as exc:  # pandas ParserError is a ValueError
        raise UploadError(
            name, f"could not be previewed ({exc})", "Check that the file is valid CSV."
        ) from exc
    dtypes = pd.DataFrame(
        {
            "column": [str(column) for column in frame.columns],
            "dtype": [str(dtype) for dtype in frame.dtypes],
            "non_null": [int(count) for count in frame.notna().sum()],
        }
    )
    return Preview(
        row_count=len(frame),
        columns=tuple(str(column) for column in frame.columns),
        dtypes=dtypes,
        head=frame.head(rows),
    )


# ---- Tables for display. Pure reshaping of pipeline output; no new metrics. ----


def cleaned_tickets_frame(tickets: tuple[SupportTicket, ...]) -> pd.DataFrame:
    """Cleaned tickets as a table, using the pipeline's own CSV representation."""
    return pd.DataFrame([ticket.to_row() for ticket in tickets], columns=list(REQUIRED_COLUMNS))


def priority_counts_frame(analytics: dict[str, Any]) -> pd.DataFrame:
    counts: dict[str, int] = analytics["ticket_count_by_priority"]
    return pd.DataFrame({"priority": list(counts), "tickets": list(counts.values())})


def resolution_time_frame(analytics: dict[str, Any]) -> pd.DataFrame:
    hours: dict[str, float] = analytics["average_resolution_time_hours_by_category"]
    rates: dict[str, float] = analytics["resolution_rate_by_category"]
    categories = sorted(set(hours) | set(rates))
    return pd.DataFrame(
        {
            "category": categories,
            "avg_resolution_time_hours": [hours.get(category) for category in categories],
            "resolution_rate": [rates.get(category) for category in categories],
        }
    )


def quality_frame(report: CleaningReport) -> pd.DataFrame:
    """One row per required column: missing before/after cleaning and invalid numbers."""
    return pd.DataFrame(
        {
            "column": list(REQUIRED_COLUMNS),
            "missing_before": [
                report.missing_values_before_cleaning.get(c, 0) for c in REQUIRED_COLUMNS
            ],
            "missing_after": [
                report.missing_values_after_cleaning.get(c, 0) for c in REQUIRED_COLUMNS
            ],
            "invalid_values": [report.invalid_numeric_values.get(c, 0) for c in REQUIRED_COLUMNS],
        }
    )


def issue_counts_frame(report: CleaningReport) -> pd.DataFrame:
    counts = report.issue_counts()
    return pd.DataFrame({"issue": list(counts), "records": list(counts.values())})
