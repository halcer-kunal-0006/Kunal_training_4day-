"""Support-ticket pipeline (Day 3): testable, diagnosable, standard library only."""

from .analytics import summarise
from .config import DuplicatePolicy, PipelineConfig
from .errors import (
    DuplicateTicketError,
    EmptyDatasetError,
    InvalidPathError,
    InvalidTicketError,
    MalformedFileError,
    OutputWriteError,
    SchemaMismatchError,
    TicketPipelineError,
)
from .logging_config import configure_logging
from .models import CleaningReport, Priority, SupportTicket, ValidationIssue
from .pipeline import PipelineResult, run_pipeline
from .processing.cleaning import CleaningResult, clean_records
from .processing.loader import RawRecord, open_ticket_csv, validate_input_path

__all__ = [
    "CleaningReport",
    "CleaningResult",
    "DuplicatePolicy",
    "DuplicateTicketError",
    "EmptyDatasetError",
    "InvalidPathError",
    "InvalidTicketError",
    "MalformedFileError",
    "OutputWriteError",
    "PipelineConfig",
    "PipelineResult",
    "Priority",
    "RawRecord",
    "SchemaMismatchError",
    "SupportTicket",
    "TicketPipelineError",
    "ValidationIssue",
    "clean_records",
    "configure_logging",
    "open_ticket_csv",
    "run_pipeline",
    "summarise",
    "validate_input_path",
]
