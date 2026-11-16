"""Exception hierarchy for the ticket pipeline.

Every error answers three questions in its message: what failed, where it
failed, and what the user can do about it. The same facts are also stored as
attributes (``path``, ``line``, ``missing`` and so on), so code and tests can
inspect them without parsing text.

Callers can catch the whole family with ``except TicketPipelineError`` and
still let genuine programming bugs (``TypeError``, ``KeyError`` ...) surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class TicketPipelineError(Exception):
    """Base class for every expected, user-fixable failure in this package."""


class InvalidPathError(TicketPipelineError):
    """The input path is missing, is not a file, is not a CSV, or cannot be opened."""

    def __init__(self, path: Path, reason: str, hint: str) -> None:
        self.path = path
        self.reason = reason
        self.hint = hint
        super().__init__(f"Input path '{path}' {reason}. {hint}")


class MalformedFileError(TicketPipelineError):
    """The file exists but its content is not a well-formed ticket CSV."""

    def __init__(self, path: Path, detail: str, hint: str, line: int | None = None) -> None:
        self.path = path
        self.line = line
        self.detail = detail
        self.hint = hint
        location = f"'{path}'" if line is None else f"'{path}' line {line}"
        super().__init__(f"{location}: {detail}. {hint}")


class EmptyDatasetError(MalformedFileError):
    """The file has no header, or a header but no ticket rows."""


class SchemaMismatchError(TicketPipelineError):
    """The header does not provide the columns the pipeline needs."""

    def __init__(
        self,
        path: Path,
        missing: Sequence[str] = (),
        found: Sequence[str] = (),
        duplicated: Sequence[str] = (),
    ) -> None:
        self.path = path
        self.missing = tuple(missing)
        self.found = tuple(found)
        self.duplicated = tuple(duplicated)
        problems = []
        if self.missing:
            problems.append(f"missing required column(s): {', '.join(self.missing)}")
        if self.duplicated:
            problems.append(f"duplicated column(s): {', '.join(self.duplicated)}")
        super().__init__(
            f"'{path}' has a schema mismatch: {'; '.join(problems)}. "
            f"Found columns: {', '.join(self.found) or '(none)'}. "
            "Fix the header row so each required column appears exactly once."
        )


class DuplicateTicketError(TicketPipelineError):
    """A ticket ID appears twice and the duplicate policy is RAISE."""

    def __init__(self, ticket_id: str, first_record: int, duplicate_record: int) -> None:
        self.ticket_id = ticket_id
        self.first_record = first_record
        self.duplicate_record = duplicate_record
        super().__init__(
            f"Ticket ID {ticket_id} appears in record {first_record} and again in record "
            f"{duplicate_record}. Remove or renumber the duplicate, or run with the "
            "keep_first duplicate policy."
        )


class InvalidTicketError(TicketPipelineError):
    """A SupportTicket was built with a value that breaks its rules (a programming error)."""

    def __init__(self, field: str, problem: str) -> None:
        self.field = field
        self.problem = problem
        super().__init__(f"Invalid ticket field '{field}': {problem}")


class OutputWriteError(TicketPipelineError):
    """An output file could not be written, or would overwrite the input."""

    def __init__(self, path: Path, reason: str, hint: str) -> None:
        self.path = path
        self.reason = reason
        self.hint = hint
        super().__init__(f"Cannot write '{path}': {reason}. {hint}")
