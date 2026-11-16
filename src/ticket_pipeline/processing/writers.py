"""Write pipeline outputs. All file output in the package goes through this module.

Each file is written to a temporary sibling first and then moved into place
with ``os.replace``. A failed write therefore never leaves a half-written
output file behind, and the previous version (if any) survives intact.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TextIO

from ..config import REQUIRED_COLUMNS
from ..errors import OutputWriteError
from ..logging_config import log_event
from ..models import CleaningReport, SupportTicket

logger = logging.getLogger(__name__)


def write_cleaned_csv(
    tickets: Iterable[SupportTicket], destination: Path, protected: Iterable[Path] = ()
) -> Path:
    """Save cleaned tickets as CSV, refusing to overwrite any protected file (the raw input)."""

    def write(handle: TextIO) -> None:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(ticket.to_row() for ticket in tickets)

    return _atomic_write(destination, write, protected)


def write_quality_report(
    report: CleaningReport, destination: Path, protected: Iterable[Path] = ()
) -> Path:
    """Save one row per problem record: its record number and its issue codes."""

    def write(handle: TextIO) -> None:
        writer = csv.writer(handle)
        writer.writerow(["source_record_number", "issues"])
        for number, codes in report.issues_by_record().items():
            writer.writerow([number, ";".join(codes)])

    return _atomic_write(destination, write, protected)


def write_json(data: dict[str, Any], destination: Path, protected: Iterable[Path] = ()) -> Path:
    def write(handle: TextIO) -> None:
        json.dump(data, handle, indent=2)
        handle.write("\n")

    return _atomic_write(destination, write, protected)


def _atomic_write(
    destination: Path, write: Callable[[TextIO], None], protected: Iterable[Path]
) -> Path:
    target = destination.resolve()
    if any(target == Path(path).resolve() for path in protected):
        raise OutputWriteError(
            destination,
            "it is the input file",
            "Choose an output directory that does not contain the raw input.",
        )
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            write(handle)
        os.replace(temporary, destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise OutputWriteError(
            destination,
            f"{type(exc).__name__}: {exc.strerror or exc}",
            "Check that the folder is writable and the file is not open in another program.",
        ) from exc
    log_event(logger, logging.INFO, "file_written", path=str(destination))
    return destination
