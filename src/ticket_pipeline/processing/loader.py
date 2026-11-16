"""Open a ticket CSV safely and stream its records one at a time.

``open_ticket_csv`` is a context manager: the file is always closed when the
``with`` block ends, whether it ends normally, through an exception, or because
the caller stopped reading early. Records are produced lazily by a generator,
so the whole file is never held in memory.

Low-level failures (``OSError``, ``UnicodeDecodeError``, ``csv.Error``) are
re-raised as package errors with ``raise ... from exc``, which keeps the
original exception as ``__cause__`` for debugging.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from ..errors import EmptyDatasetError, InvalidPathError, MalformedFileError
from ..logging_config import log_event
from .validation import check_schema

logger = logging.getLogger(__name__)

ENCODING = "utf-8-sig"  # plain UTF-8, plus files saved by Excel with a byte-order mark


@dataclass(frozen=True, slots=True)
class RawRecord:
    """One data row as text, keyed by column name.

    ``record_number`` counts data rows from 1. ``line`` is the physical line in
    the file where the row ends (they differ when the file has blank lines or
    quoted values that span several lines).
    """

    record_number: int
    line: int
    values: dict[str, str]


def validate_input_path(path: str | Path) -> Path:
    """Check that ``path`` names an existing ``.csv`` file before anything opens it."""
    path = Path(path)
    if not path.exists():
        raise InvalidPathError(
            path, "does not exist", "Check the spelling and the working directory."
        )
    if not path.is_file():
        raise InvalidPathError(path, "is not a file", "Pass the path of a .csv file, not a folder.")
    if path.suffix.lower() != ".csv":
        raise InvalidPathError(
            path,
            f"has the extension '{path.suffix}' instead of '.csv'",
            "Export the data as CSV, or rename the file if it already is CSV.",
        )
    return path


class TicketCsvReader:
    """Reads the header on creation and yields RawRecords when iterated."""

    def __init__(self, handle: TextIO, path: Path) -> None:
        self.path = path
        self._handle = handle
        self._reader = csv.reader(handle)
        header = self._next_row()
        if header is None:
            raise EmptyDatasetError(
                path, "the file is empty and has no header row", "Export the data again."
            )
        self.header = tuple(column.strip() for column in header)
        check_schema(self.header, path)

    @property
    def closed(self) -> bool:
        return self._handle.closed

    def __iter__(self) -> Iterator[RawRecord]:
        record_number = 0
        while (row := self._next_row()) is not None:
            if not row:
                continue  # a blank line is not a record
            line = self._reader.line_num
            if len(row) != len(self.header):
                raise MalformedFileError(
                    self.path,
                    f"expected {len(self.header)} fields, found {len(row)}",
                    "Check that values containing commas are wrapped in double quotes.",
                    line=line,
                )
            record_number += 1
            yield RawRecord(record_number, line, dict(zip(self.header, row, strict=True)))
        if record_number == 0:
            raise EmptyDatasetError(
                self.path,
                "the file has a header row but no ticket records",
                "Check that the export included the data rows.",
            )
        log_event(logger, logging.DEBUG, "file_read", path=self.path.name, records=record_number)

    def _next_row(self) -> list[str] | None:
        """Next parsed row (None at end of file); decode and parse errors become package errors."""
        try:
            return next(self._reader, None)
        except UnicodeDecodeError as exc:
            # No line number: text is decoded in blocks, so the reader's position
            # does not identify the line that holds the bad bytes.
            raise MalformedFileError(
                self.path,
                f"the file is not valid UTF-8 text ({exc.reason})",
                "Re-save the file with UTF-8 encoding.",
            ) from exc
        except csv.Error as exc:
            raise MalformedFileError(
                self.path,
                f"CSV parse error: {exc}",
                "Check for unbalanced double quotes.",
                line=self._reader.line_num,
            ) from exc


@contextmanager
def open_ticket_csv(path: str | Path) -> Iterator[TicketCsvReader]:
    """Validate ``path``, open it, check the header, and close it afterwards no matter what."""
    path = validate_input_path(path)
    try:
        handle = path.open(encoding=ENCODING, newline="")
    except OSError as exc:
        raise InvalidPathError(
            path,
            f"cannot be opened ({type(exc).__name__})",
            "Check the file permissions and that no other program has it locked.",
        ) from exc
    with handle:
        log_event(logger, logging.INFO, "file_opened", path=path.name)
        yield TicketCsvReader(handle, path)
