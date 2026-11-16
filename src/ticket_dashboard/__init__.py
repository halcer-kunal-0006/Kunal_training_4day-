"""Day 4: service layer that connects the Streamlit dashboard to ``ticket_pipeline``."""

from .service import (
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    DashboardResult,
    Preview,
    UploadError,
    build_preview,
    cleaned_tickets_frame,
    issue_counts_frame,
    priority_counts_frame,
    process_upload,
    quality_frame,
    resolution_time_frame,
    validate_upload,
)

__all__ = [
    "MAX_UPLOAD_BYTES",
    "MAX_UPLOAD_MB",
    "DashboardResult",
    "Preview",
    "UploadError",
    "build_preview",
    "cleaned_tickets_frame",
    "issue_counts_frame",
    "priority_counts_frame",
    "process_upload",
    "quality_frame",
    "resolution_time_frame",
    "validate_upload",
]
